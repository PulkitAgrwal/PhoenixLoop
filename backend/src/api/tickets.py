"""Ticket API routes."""

import json
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, Request
from starlette.responses import StreamingResponse

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
    request: Request,
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

    # Run agent (re-using the lifespan-managed Phoenix MCP toolset when present)
    mcp_toolset = getattr(request.app.state, "phoenix_mcp_toolset", None)
    agent_run = await run_agent(
        ticket, session_id, db, phoenix, mcp_toolset=mcp_toolset
    )
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


def _sse_pack(payload: dict) -> str:
    """Serialize a payload as an SSE ``data:`` frame."""
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.post("/tickets/{ticket_id}/run/stream")
async def run_ticket_stream(ticket_id: str, request: Request) -> StreamingResponse:
    """Stream the agent run as SSE events.

    Emits ``agent_start``, ``tool_call_started``, ``tool_call_completed``,
    ``text_chunk``, ``agent_done``, ``eval_result``, and ``done`` events
    so the UI can render progress incrementally instead of waiting on the
    full ~20s round trip.

    The DB connection is opened inside the generator because the response
    body is consumed after the handler returns — FastAPI dependency cleanup
    closes any ``Depends(get_db_session)`` connection before the first
    ``yield`` runs.
    """
    from src.agent.support_agent import run_agent_events
    from src.config import get_settings
    from src.db import (
        get_db,
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
    )
    from src.db import (
        get_ticket as db_get_ticket,
    )
    from src.diagnosis.failure_aggregator import check_thresholds, update_aggregates
    from src.evaluation.runner import run_all_evals_streaming
    from src.models import AgentRun, EvalResult
    from src.tracing.phoenix_client import get_phoenix_client

    db_path = get_settings().database_url.replace("sqlite:///", "")
    mcp_toolset = getattr(request.app.state, "phoenix_mcp_toolset", None)

    async def event_stream() -> AsyncIterator[str]:
        async with get_db(db_path) as db:
            ticket = await db_get_ticket(db, ticket_id)
            if ticket is None:
                yield _sse_pack({"type": "error", "error": "Ticket not found"})
                return

            session_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            await insert_conversation_session(
                db,
                ConversationSession(
                    conversation_session_id=session_id,
                    ticket_id=ticket_id,
                    started_at=now,
                    turn_count=1,
                ),
            )

            phoenix = get_phoenix_client()
            agent_run: AgentRun | None = None

            try:
                async for event in run_agent_events(
                    ticket, session_id, db, phoenix, mcp_toolset=mcp_toolset
                ):
                    if event["type"] == "agent_done":
                        agent_run = event["agent_run"]
                        yield _sse_pack(
                            {
                                "type": "agent_done",
                                "agent_run": agent_run.model_dump(mode="json"),
                            }
                        )
                    else:
                        yield _sse_pack(event)
            except Exception as exc:
                logger.exception("Agent stream failed for ticket %s", ticket_id)
                yield _sse_pack({"type": "error", "error": str(exc)})
                return

            if agent_run is None:
                yield _sse_pack({"type": "error", "error": "agent did not complete"})
                return

            await insert_agent_run(db, agent_run)

            eval_results: list[EvalResult] = []
            try:
                async for ev in run_all_evals_streaming(agent_run, ticket, phoenix):
                    if ev["type"] == "eval_result":
                        result: EvalResult = ev["result"]
                        eval_results.append(result)
                        await insert_eval_result(db, result)
                        yield _sse_pack(
                            {
                                "type": "eval_result",
                                "result": result.model_dump(mode="json"),
                            }
                        )
            except Exception as exc:
                logger.exception(
                    "Eval stream failed for run %s", agent_run.agent_run_id
                )
                yield _sse_pack({"type": "error", "error": str(exc)})
                return

            await update_aggregates(eval_results, db)
            triggers = await check_thresholds(db, eval_results)

            logger.info(
                "Streamed ticket %s: run=%s, evals=%d, triggers=%d",
                ticket_id,
                agent_run.agent_run_id,
                len(eval_results),
                len(triggers),
            )

            yield _sse_pack({"type": "done", "triggers_created": len(triggers)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
