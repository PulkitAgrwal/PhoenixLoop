"""Healing-cycle API — joins the 7 stages for one failure_key."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import get_db_session, get_request_id
from src.models import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["healing"])


@router.get("/healing/cycles/{failure_key}")
async def get_healing_cycle(
    failure_key: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Return everything tied to one failure_key as a single response."""
    from src.db import (
        get_failure_aggregates_by_key,
        get_human_approval_for_decision,
        get_release_gate_for_experiment,
        list_experiments_for_trigger,
        list_improvement_triggers_for_key,
    )

    aggregates = await get_failure_aggregates_by_key(db, failure_key)
    triggers = await list_improvement_triggers_for_key(db, failure_key)

    latest_trigger = triggers[0] if triggers else None
    experiments = []
    decision = None
    approval = None

    if latest_trigger:
        experiments = await list_experiments_for_trigger(
            db, latest_trigger.improvement_trigger_id
        )
        if experiments:
            decision = await get_release_gate_for_experiment(
                db, experiments[-1].experiment_id
            )
            if decision:
                approval = await get_human_approval_for_decision(
                    db, decision.release_gate_decision_id
                )

    return ApiResponse(
        ok=True,
        data={
            "failure_key": failure_key,
            "failure_aggregates": [a.model_dump() for a in aggregates],
            "triggers": [t.model_dump() for t in triggers],
            "latest_trigger": latest_trigger.model_dump() if latest_trigger else None,
            "experiments": [e.model_dump() for e in experiments],
            "release_gate_decision": decision.model_dump() if decision else None,
            "human_approval": approval.model_dump() if approval else None,
        },
        request_id=request_id,
    )
