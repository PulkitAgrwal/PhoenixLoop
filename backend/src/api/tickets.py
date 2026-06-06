"""Ticket API routes."""

import logging
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.models import ApiResponse, ConversationSession, PaginatedData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tickets"])


@router.get("/tickets")
async def list_tickets(
    category: str | None = None,
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List support tickets with optional category filter and pagination."""
    from src.db import list_tickets as db_list_tickets

    items, total = await db_list_tickets(
        db, category, pagination.page, pagination.page_size
    )
    return ApiResponse(
        ok=True,
        data=PaginatedData(
            items=items,
            total_count=total,
            page=pagination.page,
            page_size=pagination.page_size,
            has_next=(pagination.page * pagination.page_size) < total,
        ),
        request_id=request_id,
    )


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get a single ticket by ID."""
    from src.db import get_ticket as db_get_ticket

    ticket = await db_get_ticket(db, ticket_id)
    if not ticket:
        return ApiResponse(ok=False, error="Ticket not found", request_id=request_id)
    return ApiResponse(ok=True, data=ticket, request_id=request_id)


@router.post("/tickets/{ticket_id}/run")
async def run_ticket(
    ticket_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Run agent on a ticket, run evals, update aggregates."""
    from src.agent.support_agent import run_agent
    from src.db import (
        get_ticket as db_get_ticket,
    )
    from src.db import (
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
    )
    from src.diagnosis.failure_aggregator import check_thresholds, update_aggregates
    from src.evaluation.runner import run_all_evals
    from src.tracing.phoenix_client import get_phoenix_client

    ticket = await db_get_ticket(db, ticket_id)
    if not ticket:
        return ApiResponse(ok=False, error="Ticket not found", request_id=request_id)

    phoenix = get_phoenix_client()
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Create conversation session
    session = ConversationSession(
        conversation_session_id=session_id,
        ticket_id=ticket_id,
        started_at=now,
        turn_count=1,
    )
    await insert_conversation_session(db, session)

    # Run agent
    agent_run = await run_agent(ticket, session_id, db, phoenix)
    await insert_agent_run(db, agent_run)

    # Run evals
    eval_results = await run_all_evals(agent_run, ticket, phoenix)
    for result in eval_results:
        await insert_eval_result(db, result)

    # Update failure aggregates
    await update_aggregates(eval_results, db)
    triggers = await check_thresholds(db, eval_results)

    logger.info(
        "Ticket %s processed: run=%s, evals=%d, triggers=%d",
        ticket_id,
        agent_run.agent_run_id,
        len(eval_results),
        len(triggers),
    )

    return ApiResponse(
        ok=True,
        data={
            "agent_run": agent_run.model_dump(),
            "eval_results": [r.model_dump() for r in eval_results],
            "triggers_created": len(triggers),
        },
        request_id=request_id,
    )
