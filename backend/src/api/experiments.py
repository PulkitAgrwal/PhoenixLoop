"""Experiment API routes."""

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

import aiosqlite

from src.api.dependencies import get_db_session, get_request_id, PaginationParams
from src.models import ApiResponse, PaginatedData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["experiments"])


# ---------------------------------------------------------------------------
# Request body models
# ---------------------------------------------------------------------------


class CreateExperimentRequest(BaseModel):
    """Request body for creating and running an experiment."""

    improvement_trigger_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/experiments")
async def list_experiments(
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List experiments with pagination."""
    from src.db import list_experiments as db_list_experiments

    items, total = await db_list_experiments(
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


@router.get("/experiments/{experiment_id}")
async def get_experiment(
    experiment_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get an experiment with its release gate decision."""
    from src.db import (
        get_experiment as db_get_experiment,
        get_release_gate_for_experiment,
    )

    experiment = await db_get_experiment(db, experiment_id)
    if not experiment:
        return ApiResponse(
            ok=False, error="Experiment not found", request_id=request_id
        )

    gate_decision = await get_release_gate_for_experiment(db, experiment_id)

    return ApiResponse(
        ok=True,
        data={
            "experiment": experiment.model_dump(),
            "release_gate_decision": (
                gate_decision.model_dump() if gate_decision else None
            ),
        },
        request_id=request_id,
    )


@router.post("/experiments", status_code=201)
async def create_experiment(
    body: CreateExperimentRequest,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Create and run an experiment for an improvement trigger.

    This runs the full experiment pipeline: baseline vs candidate comparison,
    metric extraction, and release gate evaluation.
    """
    from src.db import (
        get_improvement_trigger,
        insert_experiment,
        insert_release_gate_decision,
        update_improvement_trigger,
    )
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.experiments.orchestrator import run_experiment
    from src.experiments.release_gate import check_promotion_rules
    from src.tracing.phoenix_client import get_phoenix_client

    trigger = await get_improvement_trigger(db, body.improvement_trigger_id)
    if not trigger:
        return ApiResponse(
            ok=False, error="Improvement trigger not found", request_id=request_id
        )

    phoenix = get_phoenix_client()
    mcp_client = PhoenixMCPClient()

    # Run the experiment
    experiment = await run_experiment(trigger, phoenix, mcp_client)
    await insert_experiment(db, experiment)

    # Evaluate release gate
    gate_decision = check_promotion_rules(experiment)
    await insert_release_gate_decision(db, gate_decision)

    # Update trigger status
    trigger.status = "experiment_complete"
    from datetime import datetime, timezone

    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    await update_improvement_trigger(db, trigger)

    logger.info(
        "Experiment %s created for trigger %s: decision=%s",
        experiment.experiment_id,
        body.improvement_trigger_id,
        gate_decision.decision.value,
    )

    return ApiResponse(
        ok=True,
        data={
            "experiment": experiment.model_dump(),
            "release_gate_decision": gate_decision.model_dump(),
        },
        request_id=request_id,
    )
