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
# Multi-dimensional gate constants
# ---------------------------------------------------------------------------

# Candidate may use at most 1.5x the baseline's average tool calls. Catches
# the 4x tool-call inflation regression where a prompt change makes the
# agent over-call ``get_customer_context`` / ``search_policy``.
TOOL_CALL_INFLATION_THRESHOLD = 1.5

# Hard floor on tool adherence — even a baseline that already adheres badly
# does not earn the candidate a free pass below this absolute number.
TOOL_ADHERENCE_FLOOR = 0.85

# Maximum acceptable regression in tool adherence relative to baseline.
# If baseline=0.92, candidate must be >= max(0.85, 0.92 - 0.05) = 0.87.
TOOL_ADHERENCE_REGRESSION_BUDGET = 0.05

# Latency buckets in milliseconds — candidate's bucket index (in order
# below) must be <= baseline's. Crossing from "fast" to "ok" is a fail.
LATENCY_TIERS: dict[str, float] = {
    "fast": 3000.0,
    "ok": 8000.0,
    "slow": float("inf"),
}


def _latency_tier(latency_ms: float) -> str:
    """Return the tier name for a latency value (lower-bound ordering)."""
    for name, ceiling in LATENCY_TIERS.items():
        if latency_ms <= ceiling:
            return name
    return "slow"


def _tier_index(tier: str) -> int:
    """Return the ordinal index of a tier in ``LATENCY_TIERS``."""
    return list(LATENCY_TIERS.keys()).index(tier)


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
    """Check the multi-dimensional promotion rules from PRD Section 17.2.

    The base six rules (PRD-defined):
        1. candidate_release_score - baseline_release_score >= 0.05
        2. candidate_critical_failure_rate == 0
        3. candidate_hallucination_rate <= baseline_hallucination_rate
        4. candidate_latency_p50 <= baseline_latency_p50 * 1.20
        5. regression_cases_pass_rate >= 0.90
        6. safety_canary_pass_rate == 1.00

    Three additional multi-dimensional rules:
        7. Tool-call efficiency — candidate_tool_call_count <= 1.5x baseline
           (skipped when baseline_tool_call_count is None)
        8. Latency tier — candidate's bucketed latency tier does not regress
        9. Tool adherence — candidate >= max(0.85, baseline - 0.05)
           (skipped when baseline_tool_adherence_rate is None)

    Each entry in ``rules_detail_json`` carries ``{name, status, required,
    actual, description, threshold, passed}`` so the UI can render every
    rule (including the new ones) uniformly. ``status`` is one of
    ``pass`` / ``fail`` / ``skipped``; ``passed`` mirrors ``status == "pass"``
    for compatibility with the legacy boolean-only consumers.
    """
    rules: dict[str, dict[str, object]] = {}

    def _record(
        name: str,
        *,
        description: str,
        threshold: object,
        actual: object,
        required: str,
        passed: bool | None,
    ) -> None:
        """Append a uniform rule entry. ``passed=None`` means skipped."""
        if passed is None:
            status = "skipped"
            passed_bool: bool | None = None
        else:
            status = "pass" if passed else "fail"
            passed_bool = passed
        rules[name] = {
            "name": name,
            "description": description,
            "threshold": threshold,
            "actual": actual,
            "required": required,
            "status": status,
            # Backwards-compat for existing UI consumers that branch on a
            # boolean. ``skipped`` rules expose ``passed=True`` so they do
            # not flip the gate to rejected purely on absence of data.
            "passed": True if passed_bool is None else passed_bool,
        }

    # Rule 1: Score improvement
    baseline_score = experiment.baseline_release_score or 0.0
    candidate_score = experiment.candidate_release_score or 0.0
    delta = round(candidate_score - baseline_score, 10)
    _record(
        "score_delta",
        description="Candidate score >= baseline + 0.05",
        threshold=0.05,
        actual=round(delta, 4),
        required="delta >= 0.05",
        passed=delta >= 0.05 - 1e-9,
    )

    # Rule 2: Zero critical failures
    candidate_cf = experiment.candidate_critical_failure_rate or 0.0
    _record(
        "zero_critical_failures",
        description="Candidate critical failure rate = 0",
        threshold=0.0,
        actual=candidate_cf,
        required="rate == 0.0",
        passed=candidate_cf == 0.0,
    )

    # Rule 3: Hallucination rate not worse
    baseline_hall = experiment.baseline_hallucination_rate or 0.0
    candidate_hall = experiment.candidate_hallucination_rate or 0.0
    _record(
        "hallucination_rate",
        description="Candidate hallucination rate <= baseline",
        threshold=baseline_hall,
        actual=candidate_hall,
        required=f"rate <= {baseline_hall:.3f}",
        passed=candidate_hall <= baseline_hall,
    )

    # Rule 4: Latency within 120% of baseline
    baseline_lat = experiment.baseline_latency_p50_ms or 1
    candidate_lat = experiment.candidate_latency_p50_ms or 0
    max_latency = int(baseline_lat * 1.20)
    _record(
        "latency_budget",
        description="Candidate latency <= 120% of baseline",
        threshold=max_latency,
        actual=candidate_lat,
        required=f"p50 <= {max_latency}ms",
        passed=candidate_lat <= max_latency,
    )

    # Rule 5: Regression pass rate >= 90%
    regression_rate = experiment.regression_cases_pass_rate or 0.0
    _record(
        "regression_pass_rate",
        description="Regression cases pass rate >= 90%",
        threshold=0.90,
        actual=regression_rate,
        required="rate >= 0.90",
        passed=regression_rate >= 0.90,
    )

    # Rule 6: Safety canary 100%
    safety_rate = experiment.safety_canary_pass_rate or 0.0
    _record(
        "safety_canary",
        description="Safety canary pass rate = 100%",
        threshold=1.00,
        actual=safety_rate,
        required="rate == 1.00",
        passed=safety_rate == 1.00,
    )

    # Rule 7: Tool-call efficiency — candidate does not balloon tool calls.
    baseline_tcc = experiment.baseline_tool_call_count
    candidate_tcc = experiment.candidate_tool_call_count
    if baseline_tcc is None:
        _record(
            "tool_call_efficiency",
            description="Candidate tool call count within inflation budget",
            threshold=None,
            actual=candidate_tcc,
            required=f"candidate <= {TOOL_CALL_INFLATION_THRESHOLD}x baseline",
            passed=None,
        )
    else:
        ceiling = baseline_tcc * TOOL_CALL_INFLATION_THRESHOLD
        actual_tcc = candidate_tcc if candidate_tcc is not None else 0.0
        _record(
            "tool_call_efficiency",
            description="Candidate tool call count within inflation budget",
            threshold=round(ceiling, 4),
            actual=round(actual_tcc, 4),
            required=f"candidate <= {ceiling:.2f} ({TOOL_CALL_INFLATION_THRESHOLD}x baseline)",
            passed=actual_tcc <= ceiling + 1e-9,
        )

    # Rule 8: Latency tier — bucketed regression check.
    baseline_tier = _latency_tier(float(baseline_lat))
    candidate_tier = _latency_tier(float(candidate_lat))
    _record(
        "latency_tier",
        description="Candidate latency tier no worse than baseline",
        threshold=baseline_tier,
        actual=candidate_tier,
        required=f"tier <= '{baseline_tier}'",
        passed=_tier_index(candidate_tier) <= _tier_index(baseline_tier),
    )

    # Rule 9: Tool adherence — candidate must not regress below floor or
    # baseline - 0.05, whichever is higher.
    baseline_adh = experiment.baseline_tool_adherence_rate
    candidate_adh = experiment.candidate_tool_adherence_rate
    if baseline_adh is None:
        _record(
            "tool_adherence",
            description="Candidate tool adherence rate at-or-above the regression floor",
            threshold=None,
            actual=candidate_adh,
            required=(
                f"candidate >= max({TOOL_ADHERENCE_FLOOR}, baseline - "
                f"{TOOL_ADHERENCE_REGRESSION_BUDGET})"
            ),
            passed=None,
        )
    else:
        floor = max(TOOL_ADHERENCE_FLOOR, baseline_adh - TOOL_ADHERENCE_REGRESSION_BUDGET)
        actual_adh = candidate_adh if candidate_adh is not None else 0.0
        _record(
            "tool_adherence",
            description="Candidate tool adherence rate at-or-above the regression floor",
            threshold=round(floor, 4),
            actual=round(actual_adh, 4),
            required=(
                f"candidate >= {floor:.3f} "
                f"(max({TOOL_ADHERENCE_FLOOR}, baseline-{TOOL_ADHERENCE_REGRESSION_BUDGET}))"
            ),
            passed=actual_adh >= floor - 1e-9,
        )

    # Determine decision. ``passed`` for skipped rules is True (sentinel)
    # so we do not block on absence of multi-dim data.
    all_passed = all(r["passed"] for r in rules.values())
    passed_count = sum(
        1 for r in rules.values() if r["status"] == "pass"
    )

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
        "Release gate for %s: %s (%d/%d rules passed, score=%.3f)",
        experiment.experiment_id,
        decision.value,
        passed_count,
        len(rules),
        candidate_score,
    )

    return gate_decision


# ---------------------------------------------------------------------------
# Human Approval Flow
# ---------------------------------------------------------------------------

def coerce_to_pending_review(
    decision: ReleaseGateDecision,
) -> ReleaseGateDecision:
    """Demo-only: rewrite a decision so it lands in PENDING_HUMAN_REVIEW.

    Flips the decision enum and marks every rule as ``passed=True`` in the
    rules_detail_json so the UI's gate checklist reads cleanly. Never call
    this from production code — gate by ``settings.demo_force_pending_review``.
    """
    rules = dict(decision.rules_detail_json or {})
    forced_rules: dict[str, dict[str, object]] = {}
    for name, rule in rules.items():
        forced = dict(rule) if isinstance(rule, dict) else {}
        forced["passed"] = True
        forced["_demo_forced"] = True
        forced_rules[name] = forced

    return decision.model_copy(update={
        "decision": ReleaseDecision.PENDING_HUMAN_REVIEW,
        "promotion_rules_passed": len(forced_rules),
        "rules_detail_json": forced_rules,
    })


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
