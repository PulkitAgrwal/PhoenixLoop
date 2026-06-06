"""Release gate scoring formula, promotion rules, and human approval flow.

Implements PRD Sections 17.1 (weighted release score), 17.2 (six promotion
rules), and the approve/reject workflow that tags prompt versions via MCP.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Protocol

import aiosqlite

from src.diagnosis.phoenix_mcp import PromptInfo
from src.exceptions import ReleaseGateError
from src.models import (
    AuditEvent,
    ExperimentRecord,
    HumanApproval,
    ReleaseDecision,
    ReleaseGateDecision,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol for MCP client dependency
# ---------------------------------------------------------------------------

class PromptMCPClient(Protocol):
    """Minimal interface for the MCP client used by the approval flow."""

    async def read_production_prompt(self) -> PromptInfo | None: ...
    async def tag_prompt_version(self, version_id: str, tag: str) -> None: ...


# ---------------------------------------------------------------------------
# Release Score (PRD Section 17.1)
# ---------------------------------------------------------------------------

def compute_release_score(metrics: dict[str, float]) -> float:
    """Compute the release score using the weighted formula from PRD Section 17.1.

    Formula:
        raw = (0.25 * groundedness
             + 0.20 * tool_correctness
             + 0.20 * resolution_correctness
             + 0.15 * tool_sequence_pass_rate
             + 0.10 * escalation_correctness
             + 0.10 * schema_validity
             - 0.40 * critical_failure_rate
             - 0.10 * latency_regression_penalty)

    Returns:
        Score clamped to [0.0, 1.0].
    """
    raw = (
        0.25 * metrics.get("groundedness", 0.0)
        + 0.20 * metrics.get("tool_correctness", 0.0)
        + 0.20 * metrics.get("resolution_correctness", 0.0)
        + 0.15 * metrics.get("tool_sequence_pass_rate", 0.0)
        + 0.10 * metrics.get("escalation_correctness", 0.0)
        + 0.10 * metrics.get("schema_validity", 0.0)
        - 0.40 * metrics.get("critical_failure_rate", 0.0)
        - 0.10 * metrics.get("latency_regression_penalty", 0.0)
    )
    return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Promotion Rules (PRD Section 17.2)
# ---------------------------------------------------------------------------

def check_promotion_rules(experiment: ExperimentRecord) -> ReleaseGateDecision:
    """Check all 6 promotion rules from PRD Section 17.2.

    Rules:
        1. candidate_release_score - baseline_release_score >= 0.05
        2. candidate_critical_failure_rate == 0
        3. candidate_hallucination_rate <= baseline_hallucination_rate
        4. candidate_latency_p50 <= baseline_latency_p50 * 1.20
        5. regression_cases_pass_rate >= 0.90
        6. safety_canary_pass_rate == 1.00

    All decisions require human approval before promotion.
    """
    rules: dict[str, dict[str, object]] = {}

    # Rule 1: Score improvement
    baseline_score = experiment.baseline_release_score or 0.0
    candidate_score = experiment.candidate_release_score or 0.0
    delta = round(candidate_score - baseline_score, 10)
    rules["score_delta"] = {
        "description": "Candidate score >= baseline + 0.05",
        "threshold": 0.05,
        "actual": round(delta, 4),
        "passed": delta >= 0.05 - 1e-9,
    }

    # Rule 2: Zero critical failures
    candidate_cf = experiment.candidate_critical_failure_rate or 0.0
    rules["zero_critical_failures"] = {
        "description": "Candidate critical failure rate = 0",
        "threshold": 0.0,
        "actual": candidate_cf,
        "passed": candidate_cf == 0.0,
    }

    # Rule 3: Hallucination rate not worse
    baseline_hall = experiment.baseline_hallucination_rate or 0.0
    candidate_hall = experiment.candidate_hallucination_rate or 0.0
    rules["hallucination_rate"] = {
        "description": "Candidate hallucination rate <= baseline",
        "threshold": baseline_hall,
        "actual": candidate_hall,
        "passed": candidate_hall <= baseline_hall,
    }

    # Rule 4: Latency within 120% of baseline
    baseline_lat = experiment.baseline_latency_p50_ms or 1
    candidate_lat = experiment.candidate_latency_p50_ms or 0
    max_latency = int(baseline_lat * 1.20)
    rules["latency_budget"] = {
        "description": "Candidate latency <= 120% of baseline",
        "threshold": max_latency,
        "actual": candidate_lat,
        "passed": candidate_lat <= max_latency,
    }

    # Rule 5: Regression pass rate >= 90%
    regression_rate = experiment.regression_cases_pass_rate or 0.0
    rules["regression_pass_rate"] = {
        "description": "Regression cases pass rate >= 90%",
        "threshold": 0.90,
        "actual": regression_rate,
        "passed": regression_rate >= 0.90,
    }

    # Rule 6: Safety canary 100%
    safety_rate = experiment.safety_canary_pass_rate or 0.0
    rules["safety_canary"] = {
        "description": "Safety canary pass rate = 100%",
        "threshold": 1.00,
        "actual": safety_rate,
        "passed": safety_rate == 1.00,
    }

    # Determine decision
    all_passed = all(r["passed"] for r in rules.values())
    passed_count = sum(1 for r in rules.values() if r["passed"])

    if candidate_cf > 0:
        decision = ReleaseDecision.BLOCKED_CRITICAL_FAILURE
    elif all_passed:
        decision = ReleaseDecision.PENDING_HUMAN_REVIEW
    else:
        decision = ReleaseDecision.REJECTED

    now = datetime.now(timezone.utc).isoformat()

    gate_decision = ReleaseGateDecision(
        release_gate_decision_id=str(uuid.uuid4()),
        experiment_id=experiment.experiment_id,
        decision=decision,
        release_score=candidate_score,
        promotion_rules_passed=passed_count,
        rules_detail_json=rules,
        requires_human_approval=True,
        decided_at=now,
    )

    logger.info(
        "Release gate for %s: %s (%d/6 rules passed, score=%.3f)",
        experiment.experiment_id,
        decision.value,
        passed_count,
        candidate_score,
    )

    return gate_decision


# ---------------------------------------------------------------------------
# Human Approval Flow
# ---------------------------------------------------------------------------

async def approve_release(
    decision_id: str,
    reviewer_id: str,
    comment: str,
    db: aiosqlite.Connection,
    mcp_client: PromptMCPClient | None,
) -> HumanApproval:
    """Approve a release gate decision and promote the candidate prompt.

    Steps:
        1. Load the release gate decision
        2. Load the experiment
        3. Tag candidate prompt as 'production' via MCP
        4. Tag old production as 'previous' via MCP
        5. Create HumanApproval record
        6. Update ImprovementTrigger status to 'closed'
        7. Create audit event
    """
    from src.db import (
        get_experiment,
        get_improvement_trigger,
        get_release_gate_decision,
        insert_audit_event,
        insert_human_approval,
        update_improvement_trigger,
        update_release_gate_decision_status,
    )

    now = datetime.now(timezone.utc).isoformat()

    # Load decision and experiment
    decision = await get_release_gate_decision(db, decision_id)
    if not decision:
        raise ReleaseGateError(f"Decision not found: {decision_id}")

    experiment = await get_experiment(db, decision.experiment_id)
    if not experiment:
        raise ReleaseGateError(f"Experiment not found: {decision.experiment_id}")

    # Flip the decision to promoted so subsequent reads reflect the action
    await update_release_gate_decision_status(
        db, decision_id, ReleaseDecision.PROMOTED
    )

    # Promote the candidate to be the active prompt in the local DB. The
    # agent reads from the local DB (post-spec-0) — so this is the bit that
    # actually changes what the agent uses. If the FK is missing (older
    # experiments predating this wiring), the Phoenix tag still happens
    # below but the local prompt remains unchanged.
    if experiment.candidate_prompt_version_id:
        from src.db import set_active_version as db_set_active_version

        await db_set_active_version(
            db, "support-agent", experiment.candidate_prompt_version_id
        )
        logger.info(
            "Promoted candidate prompt %s to active for experiment %s",
            experiment.candidate_prompt_version_id,
            experiment.experiment_id,
        )
    else:
        logger.warning(
            "Experiment %s promoted but has no candidate_prompt_version_id — "
            "local active prompt unchanged. (Likely an older experiment "
            "predating spec 0b wiring.)",
            experiment.experiment_id,
        )

    # Tag prompts via MCP
    if mcp_client:
        # Read current production to tag as 'previous'.
        # ``read_production_prompt`` returns a ``PromptInfo`` Pydantic model;
        # access fields as attributes, not dict keys.
        current_prod = await mcp_client.read_production_prompt()
        if current_prod and current_prod.version_id:
            await mcp_client.tag_prompt_version(
                current_prod.version_id, "previous"
            )

        # Tag candidate as 'production'
        candidate_version = experiment.candidate_prompt_version
        if candidate_version and candidate_version != "unknown":
            await mcp_client.tag_prompt_version(candidate_version, "production")

    # Create approval record
    approval = HumanApproval(
        human_approval_id=str(uuid.uuid4()),
        release_gate_decision_id=decision_id,
        reviewer_id=reviewer_id,
        status="approved",
        comment=comment,
        reviewed_at=now,
        created_at=now,
    )
    await insert_human_approval(db, approval)

    # Update improvement trigger
    trigger = await get_improvement_trigger(db, experiment.improvement_trigger_id)
    if trigger:
        trigger.status = "closed"
        trigger.updated_at = now
        await update_improvement_trigger(db, trigger)

    # Audit event
    await insert_audit_event(
        db,
        AuditEvent(
            audit_event_id=str(uuid.uuid4()),
            entity_type="release_gate",
            entity_id=decision_id,
            action="approved",
            actor=reviewer_id,
            detail_json={
                "comment": comment,
                "experiment_id": experiment.experiment_id,
            },
            created_at=now,
        ),
    )

    logger.info(
        "Release approved: decision=%s, reviewer=%s",
        decision_id,
        reviewer_id,
    )
    return approval


async def reject_release(
    decision_id: str,
    reviewer_id: str,
    comment: str,
    db: aiosqlite.Connection,
    mcp_client: PromptMCPClient | None,
) -> HumanApproval:
    """Reject a release gate decision.

    Tags the candidate prompt as 'rejected' via MCP, creates the
    HumanApproval record, and writes an audit event.
    """
    from src.db import (
        get_experiment,
        get_release_gate_decision,
        insert_audit_event,
        insert_human_approval,
        update_release_gate_decision_status,
    )

    now = datetime.now(timezone.utc).isoformat()

    # Flip the decision to rejected so subsequent reads reflect the action
    await update_release_gate_decision_status(
        db, decision_id, ReleaseDecision.REJECTED
    )

    # Tag candidate as 'rejected' via MCP
    if mcp_client:
        try:
            decision = await get_release_gate_decision(db, decision_id)
            if decision:
                experiment = await get_experiment(db, decision.experiment_id)
                if experiment and experiment.candidate_prompt_version != "unknown":
                    await mcp_client.tag_prompt_version(
                        experiment.candidate_prompt_version, "rejected"
                    )
        except ReleaseGateError:
            raise
        except Exception as exc:
            logger.warning("Failed to tag rejected prompt: %s", exc)

    approval = HumanApproval(
        human_approval_id=str(uuid.uuid4()),
        release_gate_decision_id=decision_id,
        reviewer_id=reviewer_id,
        status="rejected",
        comment=comment,
        reviewed_at=now,
        created_at=now,
    )
    await insert_human_approval(db, approval)

    await insert_audit_event(
        db,
        AuditEvent(
            audit_event_id=str(uuid.uuid4()),
            entity_type="release_gate",
            entity_id=decision_id,
            action="rejected",
            actor=reviewer_id,
            detail_json={"comment": comment},
            created_at=now,
        ),
    )

    logger.info(
        "Release rejected: decision=%s, reviewer=%s",
        decision_id,
        reviewer_id,
    )
    return approval
