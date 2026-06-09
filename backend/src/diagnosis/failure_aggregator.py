"""Failure aggregation pipeline — counts failure patterns and triggers improvements."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite
import pandas as pd

from src.config import get_settings
from src.diagnosis.phoenix_mcp import PhoenixMCPClient
from src.models import (
    EvalResult,
    FailureAggregate,
    FailureType,
    ImprovementTrigger,
    RegressionExample,
    TriggerReason,
)

logger = logging.getLogger(__name__)


def get_phoenix_mcp_client() -> PhoenixMCPClient:
    """Factory wrapper so tests can monkeypatch the client."""
    return PhoenixMCPClient()

# Critical failure types that trigger immediately (from PRD Section 7.4)
CRITICAL_FAILURE_TYPES = {
    FailureType.PRIVACY_LEAK,
    FailureType.WRONG_ESCALATION,
    FailureType.UNSUPPORTED_CLAIM,
    FailureType.MALFORMED_OUTPUT,
    FailureType.MISSING_REQUIRED_TOOL,
    FailureType.INCORRECT_RESOLUTION,
    FailureType.TOOL_ERROR,
}

# Mapping from evaluator names to failure types (for critical failure detection)
EVALUATOR_FAILURE_MAP: dict[str, FailureType] = {
    "privacy_guard": FailureType.PRIVACY_LEAK,
    "escalation_guard": FailureType.WRONG_ESCALATION,
    "groundedness": FailureType.UNSUPPORTED_CLAIM,
    "schema_validity": FailureType.MALFORMED_OUTPUT,
    "tool_sequence": FailureType.MISSING_REQUIRED_TOOL,
    "resolution_correctness": FailureType.INCORRECT_RESOLUTION,
    "tool_selection": FailureType.TOOL_ERROR,
    "tool_invocation": FailureType.TOOL_ERROR,
    "tool_response_handling": FailureType.TOOL_ERROR,
    "refund_guard": FailureType.INCORRECT_RESOLUTION,
    "citation_presence": FailureType.RETRIEVAL_MISS,
    "latency_budget": FailureType.LATENCY_REGRESSION,
    "policy_compliance": FailureType.INCORRECT_RESOLUTION,
    "safety_privacy": FailureType.PRIVACY_LEAK,
}


def is_critical_failure(eval_result: EvalResult) -> bool:
    """Check if an eval failure maps to a critical failure type."""
    failure_type = EVALUATOR_FAILURE_MAP.get(eval_result.evaluator_name)
    if failure_type is None:
        return False
    return failure_type in CRITICAL_FAILURE_TYPES


async def update_aggregates(
    eval_results: list[EvalResult],
    db: aiosqlite.Connection,
) -> list[str]:
    """Update failure aggregates for failing eval results.

    For each failing eval, upsert the failure_aggregates table:
    - Increment occurrence_count
    - Update last_seen_at
    - Append run_id to example_run_ids

    Args:
        eval_results: List of eval results from a single run.
        db: Database connection.

    Returns:
        List of failure_keys that were updated.
    """
    from src.db import get_failure_aggregate, upsert_failure_aggregate

    settings = get_settings()
    updated_keys: list[str] = []
    now = datetime.now(timezone.utc).isoformat()

    for result in eval_results:
        if result.outcome != "fail" or result.failure_key is None:
            continue

        existing = await get_failure_aggregate(db, result.failure_key)

        if existing:
            # Update existing aggregate
            example_ids = existing.example_run_ids_json.copy()
            if result.agent_run_id not in example_ids:
                example_ids.append(result.agent_run_id)

            updated = FailureAggregate(
                failure_key=result.failure_key,
                failure_summary=result.failure_summary or "",
                evaluator_name=result.evaluator_name,
                occurrence_count=existing.occurrence_count + 1,
                first_seen_at=existing.first_seen_at,
                last_seen_at=now,
                example_run_ids_json=example_ids,
                is_active=True,
                computed_at=now,
            )
        else:
            # Create new aggregate
            updated = FailureAggregate(
                failure_key=result.failure_key,
                failure_summary=result.failure_summary or "",
                evaluator_name=result.evaluator_name,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                example_run_ids_json=[result.agent_run_id],
                is_active=True,
                computed_at=now,
            )

        await upsert_failure_aggregate(db, updated)
        updated_keys.append(result.failure_key)
        logger.debug(
            "Updated failure aggregate: %s (count=%d)",
            result.failure_key,
            updated.occurrence_count,
        )

        # Auto-promote to Phoenix dataset when threshold reached.
        if updated.occurrence_count >= settings.repeated_failure_count:
            await _promote_to_phoenix_dataset(updated, result, db)

    return updated_keys


MAX_PROMOTION_EXAMPLES = 5


async def _promote_to_phoenix_dataset(
    aggregate: FailureAggregate,
    result: EvalResult,
    db: aiosqlite.Connection,
) -> None:
    """Push the last N failing examples for this cluster to Phoenix.

    Pulls up to MAX_PROMOTION_EXAMPLES agent_runs matching this failure_key
    (deduplicated by agent_run_id), then pushes them as a single multi-row
    DataFrame. This grows the regression dataset to a useful size per
    threshold trip instead of one example per trip.

    Best-effort: any failure in MCP/Phoenix calls is logged but does NOT
    block the aggregation pipeline.
    """
    from src.db import get_agent_run

    try:
        candidate_ids = list(aggregate.example_run_ids_json or [])
        if result.agent_run_id and result.agent_run_id not in candidate_ids:
            candidate_ids.append(result.agent_run_id)

        seen: set[str] = set()
        recent_ids: list[str] = []
        for run_id in reversed(candidate_ids):
            if run_id in seen:
                continue
            seen.add(run_id)
            recent_ids.append(run_id)
            if len(recent_ids) >= MAX_PROMOTION_EXAMPLES:
                break

        rows: list[dict] = []
        for run_id in recent_ids:
            agent_run = await get_agent_run(db, run_id)
            if agent_run is None:
                logger.debug(
                    "Skipping missing agent_run %s during promotion", run_id
                )
                continue
            rows.append(
                {
                    "input": agent_run.response_json or {},
                    "expected_output": {
                        "failure_summary": aggregate.failure_summary,
                        "failure_key": aggregate.failure_key,
                    },
                }
            )

        if not rows:
            logger.warning(
                "Cannot promote: no agent_runs resolved for failure %s",
                aggregate.failure_key,
            )
            return

        examples_df = pd.DataFrame(rows)

        client = get_phoenix_mcp_client()
        dataset_name = f"recurrent-failures-{aggregate.evaluator_name}"
        await client.add_dataset_examples(
            dataset_name=dataset_name,
            examples_df=examples_df,
            input_keys=["input"],
            output_keys=["expected_output"],
        )
        logger.info(
            "Promoted failure %s to dataset '%s' (rows=%d)",
            aggregate.failure_key,
            dataset_name,
            len(rows),
        )
    except Exception as exc:
        logger.warning(
            "Failed to promote failure %s to Phoenix dataset: %s",
            aggregate.failure_key,
            exc,
        )


async def check_thresholds(
    db: aiosqlite.Connection,
    eval_results: list[EvalResult] | None = None,
) -> list[ImprovementTrigger]:
    """Check if any failure aggregates have crossed thresholds.

    For each active failure aggregate:
    - If occurrence_count >= repeated_failure_count -> trigger
    - If critical failure AND critical_failure_immediate -> trigger immediately
    - Respect cooldown_minutes (don't re-trigger within cooldown)

    Args:
        db: Database connection.
        eval_results: Optional list of eval results to check for critical failures.

    Returns:
        List of newly created ImprovementTrigger objects.
    """
    from src.db import (
        get_active_failure_aggregates,
        insert_improvement_trigger,
        list_improvement_triggers,
    )

    settings = get_settings()
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    triggers: list[ImprovementTrigger] = []

    # Get existing triggers to check cooldown
    existing_triggers, _ = await list_improvement_triggers(
        db, status=None, page=1, page_size=1000
    )
    trigger_map: dict[str, ImprovementTrigger] = {
        t.failure_key: t for t in existing_triggers
    }

    # Check for critical failures first (immediate trigger)
    if eval_results and settings.critical_failure_immediate:
        for result in eval_results:
            if result.outcome != "fail" or result.failure_key is None:
                continue
            if not is_critical_failure(result):
                continue

            # Check cooldown
            existing = trigger_map.get(result.failure_key)
            if existing and _within_cooldown(
                existing.created_at, settings.cooldown_minutes
            ):
                logger.debug(
                    "Critical failure %s within cooldown, skipping",
                    result.failure_key,
                )
                continue

            trigger = ImprovementTrigger(
                improvement_trigger_id=str(uuid.uuid4()),
                failure_key=result.failure_key,
                trigger_reason=TriggerReason.CRITICAL_FAILURE,
                occurrence_count=1,
                example_run_ids_json=[result.agent_run_id],
                status="pending",
                created_at=now_iso,
                updated_at=now_iso,
            )
            try:
                await insert_improvement_trigger(db, trigger)
                await auto_promote_trigger_to_regression_examples(
                    trigger, db, evaluator_name=result.evaluator_name
                )
            except Exception as exc:
                # SQLite auto-rolls back the in-flight statement on
                # exception; we propagate so the caller knows the trigger
                # didn't commit cleanly. Logged loudly before re-raising.
                logger.error(
                    "Critical-failure trigger insert+promote failed for %s: %s",
                    result.failure_key,
                    exc,
                    exc_info=True,
                )
                raise
            triggers.append(trigger)
            trigger_map[result.failure_key] = trigger
            logger.info("Critical failure trigger created: %s", result.failure_key)

    # Check repeated failure thresholds
    aggregates = await get_active_failure_aggregates(db)
    for agg in aggregates:
        if agg.failure_key in trigger_map:
            existing = trigger_map[agg.failure_key]
            if existing.status != "closed" and _within_cooldown(
                existing.created_at, settings.cooldown_minutes
            ):
                continue

        if agg.occurrence_count >= settings.repeated_failure_count:
            trigger = ImprovementTrigger(
                improvement_trigger_id=str(uuid.uuid4()),
                failure_key=agg.failure_key,
                trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
                occurrence_count=agg.occurrence_count,
                example_run_ids_json=agg.example_run_ids_json,
                status="pending",
                created_at=now_iso,
                updated_at=now_iso,
            )
            try:
                await insert_improvement_trigger(db, trigger)
                await auto_promote_trigger_to_regression_examples(
                    trigger, db, evaluator_name=agg.evaluator_name
                )
            except Exception as exc:
                logger.error(
                    "Threshold trigger insert+promote failed for %s: %s",
                    agg.failure_key,
                    exc,
                    exc_info=True,
                )
                raise
            triggers.append(trigger)
            logger.info(
                "Threshold trigger created: %s (count=%d)",
                agg.failure_key,
                agg.occurrence_count,
            )

    return triggers


async def auto_promote_trigger_to_regression_examples(
    trigger: ImprovementTrigger,
    db: aiosqlite.Connection,
    *,
    evaluator_name: str | None = None,
) -> int:
    """Promote each example_run_id under a trigger to a regression_example.

    Used by ``check_thresholds`` when a failure cluster first crosses the
    repeated-failure threshold, and exposed directly via
    ``/api/improvements/{id}/actions/auto-promote-failures`` so an
    operator can re-run the promotion for any existing trigger.

    Idempotent: if ``count_regression_examples_for_trigger`` already
    reports >0 rows for this trigger we exit early and return 0. Resolves
    each agent_run to its underlying support_ticket via the repository
    layer; runs whose tickets cannot be resolved are skipped (logged at
    DEBUG).

    Args:
        trigger: The improvement trigger whose example_run_ids should
            populate the regression set.
        db: aiosqlite connection (used both for reads and for the writes
            that wrap the insert in the existing transaction context).
        evaluator_name: Optional evaluator name to embed in
            ``expected_behavior``. When None the trigger's failure_key is
            used as the human-readable hint instead.

    Returns:
        Number of new regression rows inserted.
    """
    from src.db import (
        count_regression_examples_for_trigger,
        get_agent_run,
        get_ticket,
        insert_regression_example,
    )

    existing = await count_regression_examples_for_trigger(
        db, trigger.improvement_trigger_id
    )
    if existing > 0:
        logger.debug(
            "auto-promote skipped: trigger %s already has %d regression examples",
            trigger.improvement_trigger_id,
            existing,
        )
        return 0

    now = datetime.now(timezone.utc).isoformat()
    expected_text = (
        f"must pass {evaluator_name} eval"
        if evaluator_name
        else f"must not regress on {trigger.failure_key}"
    )

    promoted = 0
    for run_id in trigger.example_run_ids_json or []:
        run = await get_agent_run(db, run_id)
        if run is None:
            logger.debug(
                "auto-promote: agent_run %s not found, skipping",
                run_id,
            )
            continue
        ticket = await get_ticket(db, run.ticket_id)
        if ticket is None:
            logger.debug(
                "auto-promote: ticket %s for run %s not found, skipping",
                run.ticket_id,
                run_id,
            )
            continue

        input_ticket = {
            "ticket_id": ticket.ticket_id,
            "customer_id": ticket.customer_id,
            "category": ticket.category.value,
            "subject": ticket.subject,
            "body": ticket.body,
            "metadata": ticket.metadata_json or {},
        }

        example = RegressionExample(
            regression_example_id=str(uuid.uuid4()),
            improvement_trigger_id=trigger.improvement_trigger_id,
            input_ticket_json=input_ticket,
            expected_behavior=expected_text,
            failure_mode_targeted=trigger.failure_key,
            created_at=now,
            source_agent_run_id=run_id,
            auto_promoted=True,
        )
        await insert_regression_example(db, example)
        promoted += 1

    if promoted:
        logger.info(
            "Auto-promoted %d failing runs to regression_examples for trigger %s",
            promoted,
            trigger.improvement_trigger_id,
        )
    return promoted


def _within_cooldown(created_at: str, cooldown_minutes: int) -> bool:
    """Check if a trigger is within the cooldown period."""
    try:
        created = datetime.fromisoformat(created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - created) < timedelta(minutes=cooldown_minutes)
    except (ValueError, TypeError):
        return False
