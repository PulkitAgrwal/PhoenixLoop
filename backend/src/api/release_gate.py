"""Release gate API routes."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.models import ApiResponse, PaginatedData

logger = logging.getLogger(__name__)

router = APIRouter(tags=["release-gate"])


# ---------------------------------------------------------------------------
# Request body models
# ---------------------------------------------------------------------------


class ApprovalRequest(BaseModel):
    """Request body for approving or rejecting a release gate decision."""

    reviewer_id: str
    comment: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/release-gate")
async def list_release_gate_decisions(
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List all release gate decisions with pagination."""
    from src.db import list_release_gate_decisions as db_list_decisions

    items, total = await db_list_decisions(
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


@router.get("/release-gate/{decision_id}")
async def get_release_gate_decision(
    decision_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get a release gate decision with its associated experiment."""
    from src.db import (
        get_experiment,
        get_human_approval_for_decision,
    )
    from src.db import (
        get_release_gate_decision as db_get_decision,
    )

    decision = await db_get_decision(db, decision_id)
    if not decision:
        return ApiResponse(
            ok=False,
            error="Release gate decision not found",
            request_id=request_id,
        )

    experiment = await get_experiment(db, decision.experiment_id)
    approval = await get_human_approval_for_decision(db, decision_id)

    return ApiResponse(
        ok=True,
        data={
            "decision": decision.model_dump(),
            "experiment": experiment.model_dump() if experiment else None,
            "human_approval": approval.model_dump() if approval else None,
        },
        request_id=request_id,
    )


@router.post("/release-gate/{decision_id}/actions/approve")
async def approve_decision(
    decision_id: str,
    body: ApprovalRequest,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Approve a release gate decision and promote the candidate prompt."""
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.experiments.release_gate import approve_release

    mcp_client = PhoenixMCPClient()

    approval = await approve_release(
        decision_id=decision_id,
        reviewer_id=body.reviewer_id,
        comment=body.comment,
        db=db,
        mcp_client=mcp_client,
    )

    logger.info(
        "Release gate %s approved by %s", decision_id, body.reviewer_id
    )

    return ApiResponse(ok=True, data=approval, request_id=request_id)


@router.post("/release-gate/{decision_id}/actions/reject")
async def reject_decision(
    decision_id: str,
    body: ApprovalRequest,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Reject a release gate decision."""
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.experiments.release_gate import reject_release

    mcp_client = PhoenixMCPClient()

    approval = await reject_release(
        decision_id=decision_id,
        reviewer_id=body.reviewer_id,
        comment=body.comment,
        db=db,
        mcp_client=mcp_client,
    )

    logger.info(
        "Release gate %s rejected by %s", decision_id, body.reviewer_id
    )

    return ApiResponse(ok=True, data=approval, request_id=request_id)
