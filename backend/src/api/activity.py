"""Activity feed — fused timeline of recent events across the system."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_db_session, get_request_id
from src.models import ActivityEvent, ActivityEventKind, ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["activity"])


@router.get("/activity")
async def list_activity(
    limit: int = Query(default=5, ge=1, le=50),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Return up to ``limit`` most recent events across all event-bearing tables."""
    rows: list[ActivityEvent] = []

    # Agent runs
    cursor = await db.execute(
        """SELECT agent_run_id AS sid, ticket_id, status, created_at
           FROM agent_runs ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )
    for r in await cursor.fetchall():
        rows.append(
            ActivityEvent(
                event_id=f"agent_run-{r['sid']}",
                kind=ActivityEventKind.AGENT_RUN,
                title=f"Agent run on {r['ticket_id']}",
                subtitle=r["status"],
                timestamp=r["created_at"],
                target_route="/activity/runs",
            )
        )

    # Failures
    cursor = await db.execute(
        """SELECT failure_key, failure_summary, evaluator_name, last_seen_at
           FROM failure_aggregates WHERE is_active = 1
           ORDER BY last_seen_at DESC LIMIT ?""",
        (limit,),
    )
    for r in await cursor.fetchall():
        rows.append(
            ActivityEvent(
                event_id=f"failure-{r['failure_key']}",
                kind=ActivityEventKind.FAILURE,
                title=r["failure_summary"] or "Failure aggregated",
                subtitle=r["evaluator_name"],
                timestamp=r["last_seen_at"],
                target_route="/activity/failures",
            )
        )

    # Improvement triggers
    cursor = await db.execute(
        """SELECT improvement_trigger_id AS sid, failure_key, trigger_reason, created_at
           FROM improvement_triggers ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )
    for r in await cursor.fetchall():
        rows.append(
            ActivityEvent(
                event_id=f"improvement_trigger-{r['sid']}",
                kind=ActivityEventKind.IMPROVEMENT_TRIGGER,
                title=f"Improvement trigger: {r['failure_key']}",
                subtitle=r["trigger_reason"],
                timestamp=r["created_at"],
                target_route="/healing/improvements",
            )
        )

    # Experiments
    cursor = await db.execute(
        """SELECT experiment_id AS sid, status, baseline_prompt_version, created_at
           FROM experiments ORDER BY created_at DESC LIMIT ?""",
        (limit,),
    )
    for r in await cursor.fetchall():
        rows.append(
            ActivityEvent(
                event_id=f"experiment-{r['sid']}",
                kind=ActivityEventKind.EXPERIMENT,
                title=f"Experiment {r['sid'][:8]}…",
                subtitle=f"status={r['status']}, baseline={r['baseline_prompt_version']}",
                timestamp=r["created_at"],
                target_route="/healing/experiments",
            )
        )

    # Release decisions
    cursor = await db.execute(
        """SELECT release_gate_decision_id AS sid, decision, experiment_id, decided_at
           FROM release_gate_decisions ORDER BY decided_at DESC LIMIT ?""",
        (limit,),
    )
    for r in await cursor.fetchall():
        rows.append(
            ActivityEvent(
                event_id=f"release_decision-{r['sid']}",
                kind=ActivityEventKind.RELEASE_DECISION,
                title=f"Release gate: {r['decision']}",
                subtitle=f"experiment {r['experiment_id'][:8]}…",
                timestamp=r["decided_at"],
                target_route="/healing/release-gate",
            )
        )

    # Sort by timestamp desc and trim
    rows.sort(key=lambda e: e.timestamp, reverse=True)
    rows = rows[:limit]

    logger.debug("activity feed returning %d events (limit=%d)", len(rows), limit)
    return ApiResponse(ok=True, data=rows, request_id=request_id)
