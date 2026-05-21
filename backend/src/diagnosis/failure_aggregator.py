"""Failure aggregation pipeline — counts failure patterns and triggers improvements."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import aiosqlite

from src.config import get_settings
from src.models import (
    EvalResult,
    FailureAggregate,
    FailureType,
    ImprovementTrigger,
    TriggerReason,
)

logger = logging.getLogger(__name__)

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

    return updated_keys


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
            await insert_improvement_trigger(db, trigger)
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
            await insert_improvement_trigger(db, trigger)
            triggers.append(trigger)
            logger.info(
                "Threshold trigger created: %s (count=%d)",
                agg.failure_key,
                agg.occurrence_count,
            )

    return triggers


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
