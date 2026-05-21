"""Conversation API routes."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.models import ApiResponse, PaginatedData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List conversation sessions with pagination."""
    from src.db import list_conversation_sessions

    items, total = await list_conversation_sessions(
        db, pagination.page, pagination.page_size
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


@router.get("/conversations/{session_id}")
async def get_conversation(
    session_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get a conversation session with its agent runs and eval results."""
    from src.db import (
        get_agent_runs_for_session,
        get_conversation_session,
        get_eval_results_for_run,
    )

    session = await get_conversation_session(db, session_id)
    if not session:
        return ApiResponse(
            ok=False, error="Conversation not found", request_id=request_id
        )

    runs = await get_agent_runs_for_session(db, session_id)
    runs_with_evals = []
    for run in runs:
        evals = await get_eval_results_for_run(db, run.agent_run_id)
        runs_with_evals.append(
            {
                "agent_run": run.model_dump(),
                "eval_results": [e.model_dump() for e in evals],
            }
        )

    return ApiResponse(
        ok=True,
        data={
            "session": session.model_dump(),
            "runs": runs_with_evals,
        },
        request_id=request_id,
    )
