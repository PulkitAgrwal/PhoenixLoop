"""Auto-seed: populate the DB so the app is alive on first boot.

Two paths:

1. **Fixture path** (``LIGHTWEIGHT_DEMO=true``) — read pre-recorded JSON
   from ``backend/tests/fixtures/seed/`` and insert verbatim. Zero Gemini
   calls. Used for pure-UI iteration so the token budget is preserved.

2. **Live path** (default) — run the actual healing loop: 4 successful
   tickets + 2 fail-twin tickets through the agent, evaluate, aggregate,
   run the diagnosis sub-agent on the trigger, synthesize a candidate
   patch, run one experiment, compute the release-gate verdict. Budget:
   ~25 Gemini calls (within the seed-phase ≤30 cap).

Both paths are idempotent: a second call observes a populated ``agent_runs``
table and exits with a single ``seed_skipped`` log line.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from src.config import get_settings
from src.models import (
    AgentRun,
    ConversationSession,
    EvalResult,
    ExperimentRecord,
    FailureAggregate,
    ImprovementTrigger,
    PromptVersion,
    RegressionExample,
    ReleaseGateDecision,
    SupportTicket,
)

logger = logging.getLogger(__name__)

# Resolve fixture dir relative to this file:
# backend/src/api/seed.py -> backend/tests/fixtures/seed
_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures" / "seed"
)


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


async def full_loop_seed(
    db: aiosqlite.Connection,
    *,
    mcp_toolset: Any | None = None,
) -> dict:
    """Idempotent auto-seed. Returns a small summary dict for logging.

    Skips entirely when ``agent_runs`` already has rows. Routes to the
    fixture loader when ``settings.lightweight_demo`` is true; otherwise
    runs the live pipeline.
    """
    if await _agent_runs_count(db) > 0:
        logger.info("seed_skipped: agent_runs already populated")
        return {"skipped": True, "reason": "agent_runs already populated"}

    settings = get_settings()
    if settings.lightweight_demo:
        logger.info("auto-seed: LIGHTWEIGHT_DEMO=true — loading fixtures")
        summary = await _seed_from_fixtures(db)
        summary["mode"] = "lightweight"
        return summary

    logger.info("auto-seed: live mode — running the full healing loop")
    summary = await _seed_live(db, mcp_toolset=mcp_toolset)
    summary["mode"] = "live"
    return summary


async def _agent_runs_count(db: aiosqlite.Connection) -> int:
    cur = await db.execute("SELECT COUNT(*) FROM agent_runs")
    row = await cur.fetchone()
    return int(row[0]) if row else 0


# ---------------------------------------------------------------------------
# Fixture path — LIGHTWEIGHT_DEMO=true
# ---------------------------------------------------------------------------


def _load_fixture(name: str) -> Any:
    """Read a JSON fixture file by basename (without extension)."""
    path = _FIXTURES_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"Seed fixture missing: {path}. "
            "Run `python scripts/capture_fixtures.py --from-last-seed` after a "
            "live run, or restore the file from git."
        )
    return json.loads(path.read_text(encoding="utf-8"))


async def _seed_from_fixtures(db: aiosqlite.Connection) -> dict:
    from src.db import (
        get_prompt,
        get_prompt_version,
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
        insert_experiment,
        insert_improvement_trigger,
        insert_prompt_version,
        insert_regression_example,
        insert_release_gate_decision,
        insert_ticket,
        upsert_failure_aggregate,
    )

    tickets = _load_fixture("tickets")
    agent_runs = _load_fixture("agent_runs")
    eval_results = _load_fixture("eval_results")
    failure_aggregate = _load_fixture("failure_aggregate")
    trigger_raw = _load_fixture("improvement_trigger")
    diagnosis = _load_fixture("diagnosis")
    patch_proposal = _load_fixture("patch_proposal")
    regression_examples = _load_fixture("regression_examples")
    candidate_pv = _load_fixture("prompt_version_candidate")
    experiment_raw = _load_fixture("experiment")
    release_gate_raw = _load_fixture("release_gate")

    # 1. Tickets.
    for t in tickets:
        await insert_ticket(db, SupportTicket(**t))

    # 2. Conversation sessions + agent runs.
    seen_session_ids: set[str] = set()
    for ar in agent_runs:
        sess_id = ar["conversation_session_id"]
        if sess_id not in seen_session_ids:
            await insert_conversation_session(
                db,
                ConversationSession(
                    conversation_session_id=sess_id,
                    ticket_id=ar["ticket_id"],
                    phoenix_session_id=ar.get("phoenix_session_id"),
                    started_at=ar["created_at"],
                    turn_count=1,
                ),
            )
            seen_session_ids.add(sess_id)
        await insert_agent_run(db, AgentRun(**ar))

    # 3. Eval results.
    for er in eval_results:
        await insert_eval_result(db, EvalResult(**er))

    # 4. Failure aggregate.
    await upsert_failure_aggregate(db, FailureAggregate(**failure_aggregate))

    # 5. Improvement trigger (with diagnosis + proposal embedded).
    # MUST come before the prompt version (FK from prompt_versions.improvement_trigger_id)
    # AND before regression_examples (same FK).
    trigger_raw["diagnosis_json"] = diagnosis
    trigger_raw["patch_proposal_json"] = patch_proposal
    trigger_raw["regression_examples_json"] = regression_examples
    await insert_improvement_trigger(db, ImprovementTrigger(**trigger_raw))

    # 6. Candidate prompt version — compose the full prompt text from the
    # active production prompt + the patch's proposed insertion. The
    # fixture has the diff (not the full prompt) so we don't have to
    # version a 5000-line JSON file every time the prompt changes.
    active_prompt = await get_prompt(db, "support-agent")
    active_version_text = ""
    if active_prompt and active_prompt.active_version_id:
        active_version = await get_prompt_version(
            db, active_prompt.active_version_id
        )
        if active_version:
            active_version_text = active_version.prompt_text

    candidate_pv["prompt_text"] = _compose_candidate_text(
        baseline_text=active_version_text,
        patch_proposed=patch_proposal.get("proposed_change", ""),
    )
    await insert_prompt_version(db, PromptVersion(**candidate_pv))

    # 7. Regression examples (FK on improvement_trigger_id).
    for ex in regression_examples:
        await insert_regression_example(db, RegressionExample(**ex))

    # 8. Experiment (FKs to improvement_trigger + prompt_versions).
    await insert_experiment(db, ExperimentRecord(**experiment_raw))

    # 9. Release gate (FK to experiment).
    await insert_release_gate_decision(
        db, ReleaseGateDecision(**release_gate_raw)
    )

    return {
        "tickets": len(tickets),
        "agent_runs": len(agent_runs),
        "eval_results": len(eval_results),
        "improvement_triggers": 1,
        "experiments": 1,
        "release_gate_decisions": 1,
    }


def _compose_candidate_text(*, baseline_text: str, patch_proposed: str) -> str:
    """Glue the patch onto the baseline prompt to form the candidate text.

    The fixture stores only the diff so we don't lock in a stale snapshot
    of the full production prompt. Appending the patch after the baseline
    is good enough for the LIGHTWEIGHT_DEMO scoreboard — the candidate
    text never runs through the agent in this mode.
    """
    if not baseline_text:
        return patch_proposed or ""
    if not patch_proposed:
        return baseline_text
    sep = "\n\n[Candidate patch — appended by LIGHTWEIGHT_DEMO seed]\n"
    return f"{baseline_text}{sep}{patch_proposed}"


# ---------------------------------------------------------------------------
# Live path — default mode
# ---------------------------------------------------------------------------


# The 6 tickets the live seed orchestrates: 4 expected to succeed
# (one per category) + 2 fail-twins designed to under-cite policies.
_LIVE_TICKETS: list[dict] = [
    {
        "ticket_id": "HEL-2847",
        "customer_id": "cus_5WvnX4nq",
        "category": "refund",
        "subject": "Pro plan refund — canceled but still charged",
        "body": (
            "Hey, I canceled my Pro seat on May 28 but the June 1 charge of "
            "$29 still hit my card. Can you reverse it? Account is "
            "jane.doe@example.com."
        ),
    },
    {
        "ticket_id": "HEL-2848",
        "customer_id": "cus_XIEADwIa",
        "category": "refund",
        "subject": "Refund the remaining months on our Enterprise contract",
        "body": (
            "We're migrating off Helios at the end of Q3 and would like a "
            "partial refund for the rest of our annual Enterprise contract — "
            "renewed Jan 10 2026. Let me know what you need from us. – Marcus"
        ),
    },
    {
        "ticket_id": "HEL-2849",
        "customer_id": "cus_Jmvq4zyy",
        "category": "admin_access",
        "subject": "Adding a second admin to our workspace",
        "body": (
            "Hi — I'm the workspace owner on Business. I'd like to make my "
            "co-founder (sam@designco.com) a second admin. Is there a cap on "
            "admins on Business?"
        ),
    },
    {
        "ticket_id": "HEL-2850",
        "customer_id": "cus_MAMb9OM3",
        "category": "billing",
        "subject": "What's actually included in Free?",
        "body": (
            "Just signed up on the Free tier and I'm trying to figure out "
            "where the cap is vs Pro. The pricing page is a bit ambiguous — "
            "is there a hard limit on number of projects on Free, or just on "
            "collaborators?"
        ),
    },
    {
        "ticket_id": "HEL-2851",
        "customer_id": "cus_Nh3rZUr7",
        "category": "refund",
        "subject": "How do refunds work on monthly Pro?",
        "body": (
            "Quick question — if I cancel mid-cycle on Pro, how does the "
            "refund work? Just want the high-level rules in plain English, "
            "no need to look anything up. Thanks."
        ),
    },
    {
        "ticket_id": "HEL-2852",
        "customer_id": "cus_CbaPTAUZ",
        "category": "refund",
        "subject": "How long does a refund take to land?",
        "body": (
            "Heard back that my refund was approved last week. Roughly how "
            "many business days until it actually shows up on the card? Just "
            "trying to plan around it."
        ),
    },
]


async def _seed_live(
    db: aiosqlite.Connection,
    mcp_toolset: Any | None,
) -> dict:
    """Run the full healing loop end-to-end. Tolerant of partial failures."""
    from src.agent.diagnosis_agent import run_diagnosis_agent
    from src.agent.support_agent import run_agent
    from src.db import (
        get_active_failure_aggregates,
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
        insert_experiment,
        insert_release_gate_decision,
        insert_ticket,
        update_improvement_trigger,
    )
    from src.diagnosis.failure_aggregator import (
        check_thresholds,
        update_aggregates,
    )
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.diagnosis.proposal_generator import generate_proposal
    from src.evaluation.runner import run_all_evals
    from src.experiments.orchestrator import run_experiment
    from src.experiments.release_gate import check_promotion_rules
    from src.models import TicketCategory, TriggerReason
    from src.tracing.phoenix_client import get_phoenix_client

    phoenix = get_phoenix_client()
    now_iso = datetime.now(timezone.utc).isoformat()

    summary: dict[str, Any] = {
        "tickets_seeded": 0,
        "agent_runs": 0,
        "eval_results": 0,
        "triggers_created": 0,
        "diagnosis": None,
        "patch_proposal": None,
        "experiment_id": None,
        "release_gate_decision": None,
        "errors": [],
    }

    # 1. Insert tickets, run the agent on each, run evals, persist.
    all_eval_results: list[EvalResult] = []
    for raw in _LIVE_TICKETS:
        ticket = SupportTicket(
            ticket_id=raw["ticket_id"],
            customer_id=raw["customer_id"],
            category=TicketCategory(raw["category"]),
            subject=raw["subject"],
            body=raw["body"],
            metadata_json={"seeded_via": "live_full_loop"},
            created_at=now_iso,
            updated_at=now_iso,
        )
        await insert_ticket(db, ticket)
        summary["tickets_seeded"] += 1

        session_id = str(uuid.uuid4())
        await insert_conversation_session(
            db,
            ConversationSession(
                conversation_session_id=session_id,
                ticket_id=ticket.ticket_id,
                started_at=now_iso,
                turn_count=1,
            ),
        )

        try:
            agent_run = await run_agent(
                ticket,
                session_id,
                db,
                phoenix_client=phoenix,
                mcp_toolset=mcp_toolset,
            )
        except Exception as exc:
            logger.warning(
                "Live seed: agent failed on %s: %s", ticket.ticket_id, exc
            )
            summary["errors"].append(
                {"stage": "agent", "ticket_id": ticket.ticket_id, "error": str(exc)}
            )
            continue
        await insert_agent_run(db, agent_run)
        summary["agent_runs"] += 1

        try:
            eval_results = await run_all_evals(agent_run, ticket, phoenix)
        except Exception as exc:
            logger.warning(
                "Live seed: evals failed on %s: %s", ticket.ticket_id, exc
            )
            summary["errors"].append(
                {"stage": "evals", "ticket_id": ticket.ticket_id, "error": str(exc)}
            )
            eval_results = []

        for r in eval_results:
            await insert_eval_result(db, r)
        summary["eval_results"] += len(eval_results)
        all_eval_results.extend(eval_results)

    # 2. Aggregate failures and check whether any cluster crosses threshold.
    try:
        await update_aggregates(all_eval_results, db)
        triggers = await check_thresholds(db, all_eval_results)
    except Exception as exc:
        logger.warning("Live seed: aggregation failed: %s", exc)
        triggers = []

    # If no natural cluster formed (e.g. the agent cited policies on both
    # fail-twins, which we can't deterministically force on Flash), fall
    # back to constructing a manual trigger so the rest of the loop has
    # something to chew on. The trigger is still anchored to real failing
    # spans if any exist, otherwise it's a manual demo trigger.
    if not triggers:
        triggers = await _ensure_demo_trigger(
            db, all_eval_results, now_iso
        )
    summary["triggers_created"] = len(triggers)
    if not triggers:
        logger.warning(
            "Live seed: no improvement trigger could be created — "
            "stopping after agent runs"
        )
        return summary

    trigger = triggers[0]

    # 3. Diagnose via the ADK sub-agent (Phoenix MCP toolbelt).
    try:
        diagnosis = await run_diagnosis_agent(trigger, mcp_toolset)
    except Exception as exc:
        logger.warning("Live seed: diagnosis_agent failed: %s", exc)
        diagnosis = {
            "failure_pattern": trigger.failure_key,
            "root_cause": f"diagnosis_agent error: {exc.__class__.__name__}",
            "evidence_summary": "(none)",
            "evidence": [],
            "confidence": 0.0,
            "suggested_fix": "Manual review required",
            "mcp_tools_used": [],
            "mcp_status": "agent_fallback",
        }
    trigger.diagnosis_json = diagnosis
    trigger.status = "diagnosed"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    summary["diagnosis"] = {
        "confidence": diagnosis.get("confidence"),
        "mcp_status": diagnosis.get("mcp_status"),
    }

    # 4. Synthesize the candidate prompt patch.
    mcp_client = PhoenixMCPClient()
    try:
        proposal = await generate_proposal(
            trigger, diagnosis, mcp_client, db=db
        )
    except Exception as exc:
        logger.warning("Live seed: proposal generation failed: %s", exc)
        proposal = {"error": str(exc), "patch_type": "prompt_constraint"}
    trigger.patch_proposal_json = proposal
    trigger.status = "proposal_ready"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    await update_improvement_trigger(db, trigger)
    summary["patch_proposal"] = {
        "patch_type": proposal.get("patch_type"),
        "candidate_prompt_version": proposal.get("candidate_prompt_version"),
    }

    # 5. Run the experiment (baseline vs candidate on up to 5 tickets).
    try:
        experiment = await run_experiment(trigger, phoenix, mcp_client, db=db)
    except Exception as exc:
        logger.warning("Live seed: experiment failed: %s", exc)
        summary["errors"].append({"stage": "experiment", "error": str(exc)})
        return summary
    await insert_experiment(db, experiment)
    summary["experiment_id"] = experiment.experiment_id

    # 6. Release-gate decision.
    try:
        gate_decision = check_promotion_rules(experiment)
        from src.config import get_settings
        if get_settings().demo_force_pending_review:
            from src.experiments.release_gate import coerce_to_pending_review
            gate_decision = coerce_to_pending_review(gate_decision)
        await insert_release_gate_decision(db, gate_decision)
        summary["release_gate_decision"] = gate_decision.decision.value
        trigger.status = "experiment_complete"
        trigger.updated_at = datetime.now(timezone.utc).isoformat()
        await update_improvement_trigger(db, trigger)
    except Exception as exc:
        logger.warning("Live seed: release gate failed: %s", exc)
        summary["errors"].append({"stage": "release_gate", "error": str(exc)})

    _ = get_active_failure_aggregates  # imported for FK-debugging support
    _ = TriggerReason  # used for the manual-trigger helper
    return summary


async def _ensure_demo_trigger(
    db: aiosqlite.Connection,
    eval_results: list[EvalResult],
    now_iso: str,
) -> list[ImprovementTrigger]:
    """Last-resort trigger construction when natural aggregation didn't fire.

    Picks any failing eval as the cluster anchor; if there are none, returns
    an empty list (the seed will still have populated agent runs and evals,
    which is itself a useful demo state).
    """
    from src.db import insert_improvement_trigger
    from src.models import TriggerReason

    failing = [r for r in eval_results if r.outcome == "fail" and r.failure_key]
    if not failing:
        return []

    anchor = failing[0]
    failure_key = anchor.failure_key
    example_run_ids = [
        r.agent_run_id for r in failing if r.failure_key == failure_key
    ]
    trigger = ImprovementTrigger(
        improvement_trigger_id=str(uuid.uuid4()),
        failure_key=failure_key or "demo_failure",
        trigger_reason=TriggerReason.MANUAL_DEMO_TRIGGER,
        occurrence_count=len(example_run_ids),
        example_run_ids_json=example_run_ids,
        status="pending",
        created_at=now_iso,
        updated_at=now_iso,
    )
    await insert_improvement_trigger(db, trigger)
    logger.info(
        "Live seed: manual trigger created (%s, %d examples)",
        failure_key,
        len(example_run_ids),
    )
    return [trigger]
