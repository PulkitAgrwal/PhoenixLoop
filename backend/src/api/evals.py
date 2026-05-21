"""Evaluation API routes."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.models import ApiResponse, PaginatedData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["evals"])


@router.get("/evals/{agent_run_id}")
async def get_eval_results(
    agent_run_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get eval results for a specific agent run."""
    from src.db import get_agent_run, get_eval_results_for_run

    run = await get_agent_run(db, agent_run_id)
    if not run:
        return ApiResponse(
            ok=False, error="Agent run not found", request_id=request_id
        )

    results = await get_eval_results_for_run(db, agent_run_id)
    return ApiResponse(ok=True, data=results, request_id=request_id)


@router.get("/failures")
async def get_failure_aggregates(
    active_only: bool = True,
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get failure aggregates with optional active filter and pagination."""
    from src.db import list_failure_aggregates

    items, total = await list_failure_aggregates(
        db, active_only, pagination.page, pagination.page_size
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


@router.post("/evals/{agent_run_id}/run")
async def rerun_evals(
    agent_run_id: str,
    force: bool = False,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Re-run evals for a specific agent run.

    Use ?force=true to re-run even if results already exist.
    """
    from src.db import (
        get_agent_run,
        get_eval_results_for_run,
        insert_eval_result,
    )
    from src.db import (
        get_ticket as db_get_ticket,
    )
    from src.evaluation.runner import run_all_evals
    from src.tracing.phoenix_client import get_phoenix_client

    run = await get_agent_run(db, agent_run_id)
    if not run:
        return ApiResponse(
            ok=False, error="Agent run not found", request_id=request_id
        )

    # Check for existing results if not forcing
    if not force:
        existing = await get_eval_results_for_run(db, agent_run_id)
        if existing:
            return ApiResponse(
                ok=False,
                error="Eval results already exist. Use ?force=true to re-run.",
                request_id=request_id,
            )

    ticket = await db_get_ticket(db, run.ticket_id)
    if not ticket:
        return ApiResponse(
            ok=False, error="Ticket not found for agent run", request_id=request_id
        )

    phoenix = get_phoenix_client()
    eval_results = await run_all_evals(run, ticket, phoenix)
    for result in eval_results:
        await insert_eval_result(db, result)

    logger.info(
        "Re-ran evals for run %s: %d results", agent_run_id, len(eval_results)
    )

    return ApiResponse(
        ok=True,
        data=[r.model_dump() for r in eval_results],
        request_id=request_id,
    )
