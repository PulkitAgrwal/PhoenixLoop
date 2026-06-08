"""SSE event generator for the live healing-cycle seed.

Mirrors the behavior of ``src.api.seed._seed_live`` but yields progress
events between stages so the UI can render a live timeline.

Each yielded value is ``(event_name, payload)`` — the caller is
responsible for serializing to ``data: {...}\\n\\n`` SSE framing.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

import aiosqlite

from src.models import (
    ConversationSession,
    EvalResult,
    SupportTicket,
)

logger = logging.getLogger(__name__)


async def stream_full_loop(
    db: aiosqlite.Connection,
    *,
    mcp_toolset: Any | None = None,
    diagnosis_mcp_toolset: Any | None = None,
) -> AsyncIterator[tuple[str, dict]]:
    """Run the live healing loop and yield progress events at each stage."""
    from src.agent.diagnosis_agent import run_diagnosis_agent
    from src.agent.support_agent import run_agent
    from src.api.seed import _LIVE_TICKETS, _ensure_demo_trigger
    from src.config import get_settings
    from src.db import (
        get_ticket,
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
        insert_experiment,
        insert_regression_example,
        insert_release_gate_decision,
        insert_ticket,
        update_improvement_trigger,
    )
    from src.diagnosis.failure_aggregator import (
        check_thresholds,
        update_aggregates,
    )
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.diagnosis.proposal_generator import (
        generate_proposal,
        generate_regression_examples,
    )
    from src.evaluation.runner import run_all_evals
    from src.experiments.orchestrator import run_experiment
    from src.experiments.release_gate import check_promotion_rules
    from src.models import TicketCategory
    from src.tracing.phoenix_client import get_phoenix_client

    phoenix = get_phoenix_client()
    settings = get_settings()
    now_iso = datetime.now(timezone.utc).isoformat()

    cycle_id = str(uuid.uuid4())
    yield "cycle_started", {
        "cycle_id": cycle_id,
        "ticket_count": len(_LIVE_TICKETS),
        "started_at": now_iso,
    }
    yield "seed_started", {"ticket_count": len(_LIVE_TICKETS)}

    all_eval_results: list[EvalResult] = []
    for idx, raw in enumerate(_LIVE_TICKETS):
        ticket = SupportTicket(
            ticket_id=raw["ticket_id"],
            customer_id=raw["customer_id"],
            category=TicketCategory(raw["category"]),
            subject=raw["subject"],
            body=raw["body"],
            metadata_json={"seeded_via": "stream_full_loop"},
            created_at=now_iso,
            updated_at=now_iso,
        )
        existing = await get_ticket(db, ticket.ticket_id)
        if existing is None:
            await insert_ticket(db, ticket)
        yield "ticket_created", {
            "ticket_id": ticket.ticket_id,
            "reused": existing is not None,
        }

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
                ticket, session_id, db,
                phoenix_client=phoenix, mcp_toolset=mcp_toolset,
                phoenixloop_cycle_id=cycle_id,
            )
        except Exception as exc:
            logger.warning("stream: agent failed on %s: %s", ticket.ticket_id, exc)
            yield "agent_failed", {"ticket_id": ticket.ticket_id, "error": str(exc)}
            continue

        # Demo-only deterministic failure: strip citations from tickets at
        # indices 1 and 3 so the citation_presence evaluator fails twice and
        # the cluster crosses threshold. The agent's Gemini call + Phoenix
        # span are untouched; only the post-agent response shape is mutated
        # before persisting the AgentRun row and running evals.
        if settings.demo_force_failure and idx in (1, 3):
            if isinstance(agent_run.response_json, dict):
                agent_run.response_json = {
                    **agent_run.response_json,
                    "citations": [],
                }
                logger.info(
                    "demo_force_failure: stripped citations from ticket %s (idx=%d)",
                    ticket.ticket_id, idx,
                )

        await insert_agent_run(db, agent_run)
        yield "agent_run_completed", {
            "ticket_id": ticket.ticket_id,
            "agent_run_id": agent_run.agent_run_id,
            "latency_ms": agent_run.latency_ms,
        }

        try:
            eval_results = await run_all_evals(agent_run, ticket, phoenix)
        except Exception as exc:
            logger.warning("stream: evals failed on %s: %s", ticket.ticket_id, exc)
            yield "evals_failed", {"ticket_id": ticket.ticket_id, "error": str(exc)}
            eval_results = []
        for r in eval_results:
            await insert_eval_result(db, r)
        all_eval_results.extend(eval_results)
        yield "evals_completed", {
            "ticket_id": ticket.ticket_id,
            "eval_count": len(eval_results),
        }

    try:
        await update_aggregates(all_eval_results, db)
        triggers = await check_thresholds(db, all_eval_results)
    except Exception as exc:
        logger.warning("stream: aggregation failed: %s", exc)
        yield "aggregation_failed", {"error": str(exc)}
        triggers = []

    if not triggers:
        triggers = await _ensure_demo_trigger(db, all_eval_results, now_iso)
    if not triggers:
        yield "no_trigger", {}
        return

    trigger = triggers[0]
    yield "trigger_fired", {
        "improvement_trigger_id": trigger.improvement_trigger_id,
        "failure_key": trigger.failure_key,
    }

    yield "diagnosis_started", {"improvement_trigger_id": trigger.improvement_trigger_id}
    from src.db import resolve_trace_ids
    example_trace_ids = await resolve_trace_ids(db, trigger.example_run_ids_json)
    try:
        diagnosis = await run_diagnosis_agent(
            trigger,
            diagnosis_mcp_toolset or mcp_toolset,
            phoenixloop_cycle_id=cycle_id,
            example_trace_ids=example_trace_ids,
        )
    except Exception as exc:
        logger.warning("stream: diagnosis_agent failed: %s", exc)
        diagnosis = {
            "failure_pattern": trigger.failure_key,
            "root_cause": f"diagnosis_agent error: {exc.__class__.__name__}",
            "confidence": 0.0,
            "suggested_fix": "Manual review required",
            "mcp_tools_used": [],
            "mcp_status": "agent_fallback",
        }
    trigger.diagnosis_json = diagnosis
    trigger.status = "diagnosed"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    yield "diagnosis_completed", {
        "root_cause": diagnosis.get("root_cause"),
        "confidence": diagnosis.get("confidence"),
    }

    # Pre-resolve the local production prompt so the patch synthesizer reads
    # the clean Helios seed text rather than whatever (potentially polluted)
    # template Phoenix's `production` tag points at. Avoids the prompt-text
    # repr-nesting bug whereby each cycle compounds escape characters.
    from src.agent.prompts import get_production_prompt
    local_prompt_text, _ = await get_production_prompt(db)

    mcp_client = PhoenixMCPClient()
    try:
        proposal = await generate_proposal(
            trigger,
            diagnosis,
            mcp_client,
            current_prompt=local_prompt_text,
            db=db,
        )
    except Exception as exc:
        logger.warning("stream: proposal generation failed: %s", exc)
        proposal = {"error": str(exc), "patch_type": "prompt_constraint"}
    trigger.patch_proposal_json = proposal
    trigger.status = "proposal_ready"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    await update_improvement_trigger(db, trigger)
    yield "patch_generated", {
        "patch_type": proposal.get("patch_type"),
        "candidate_prompt_version": proposal.get("candidate_prompt_version"),
    }

    # Synthesize regression examples and persist them. This populates the
    # ``phoenix_dataset_id`` column that the experiment orchestrator reads
    # to mint real Phoenix experiments (instead of local-* stubs).
    try:
        regression_examples = await generate_regression_examples(
            trigger, diagnosis, mcp_client
        )
    except Exception as exc:
        logger.warning("stream: regression generation failed: %s", exc)
        regression_examples = []
    captured_dataset_id: str | None = None
    for example in regression_examples:
        await insert_regression_example(db, example)
        if captured_dataset_id is None and example.phoenix_dataset_id:
            captured_dataset_id = example.phoenix_dataset_id
    if regression_examples:
        trigger.regression_examples_json = [
            ex.model_dump() for ex in regression_examples
        ]
        trigger.updated_at = datetime.now(timezone.utc).isoformat()
        await update_improvement_trigger(db, trigger)
    yield "regressions_generated", {
        "count": len(regression_examples),
        "phoenix_dataset_id": captured_dataset_id,
    }

    yield "experiment_started", {"improvement_trigger_id": trigger.improvement_trigger_id}
    try:
        experiment = await run_experiment(
            trigger, phoenix, mcp_client, db=db,
            phoenixloop_cycle_id=cycle_id,
        )
    except Exception as exc:
        logger.warning("stream: experiment failed: %s", exc)
        yield "experiment_failed", {"error": str(exc)}
        return
    await insert_experiment(db, experiment)
    yield "experiment_completed", {
        "experiment_id": experiment.experiment_id,
        "baseline_score": experiment.baseline_release_score,
        "candidate_score": experiment.candidate_release_score,
        "delta": (experiment.candidate_release_score or 0.0)
                 - (experiment.baseline_release_score or 0.0),
    }

    try:
        gate_decision = check_promotion_rules(experiment)
        from src.config import get_settings
        if get_settings().demo_force_pending_review:
            from src.experiments.release_gate import coerce_to_pending_review
            gate_decision = coerce_to_pending_review(gate_decision)
        await insert_release_gate_decision(db, gate_decision)
        trigger.status = "experiment_complete"
        trigger.updated_at = datetime.now(timezone.utc).isoformat()
        await update_improvement_trigger(db, trigger)
        yield "release_gate_decided", {
            "decision": gate_decision.decision.value,
            "release_score": gate_decision.release_score,
            "rules_passed": gate_decision.promotion_rules_passed,
            "decision_id": gate_decision.release_gate_decision_id,
            "failure_key": trigger.failure_key,
        }
    except Exception as exc:
        logger.warning("stream: release gate failed: %s", exc)
        yield "release_gate_failed", {"error": str(exc)}
