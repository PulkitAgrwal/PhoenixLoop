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


@router.post("/evals/canary/load")
async def load_canary(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Idempotently load canary_labels.json into the canary_labels table.

    A second call inserts 0 rows. Returns ``{"loaded": int}`` with the
    count of newly inserted labels.
    """
    from src.evaluation.canary import load_canary_fixtures

    try:
        inserted = await load_canary_fixtures(db)
    except FileNotFoundError as exc:
        logger.error("canary fixtures missing: %s", exc)
        return ApiResponse(ok=False, error=str(exc), request_id=request_id)

    return ApiResponse(
        ok=True, data={"loaded": inserted}, request_id=request_id
    )


@router.post("/evals/canary/run")
async def run_canary_endpoint(
    judge_name: str | None = None,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Run the 4 LLM judges against every canary fixture.

    Slow — ~one Gemini call per fixture (the 4 judges share each call).
    Optional ``judge_name`` query param scopes the persisted CanaryRun
    rows to a single judge (the Gemini call is still batched).
    """
    from src.evaluation.canary import run_canary

    summary = await run_canary(db, judge_name=judge_name)
    return ApiResponse(ok=True, data=summary, request_id=request_id)


@router.get("/evals/canary/kappa")
async def get_canary_kappa(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Return Cohen's kappa per judge over the latest canary runs."""
    from datetime import datetime, timezone

    from src.evaluation.canary import compute_kappa_all_judges

    judges = await compute_kappa_all_judges(db)
    return ApiResponse(
        ok=True,
        data={
            "judges": judges,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        },
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
