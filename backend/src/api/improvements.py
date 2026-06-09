"""Improvement trigger API routes."""

import logging
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.models import (
    ApiResponse,
    ChangeClass,
    ImprovementTrigger,
    PaginatedData,
    TriggerReason,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["improvements"])


# ---------------------------------------------------------------------------
# Request body models
# ---------------------------------------------------------------------------


class CreateImprovementRequest(BaseModel):
    """Request body for manually creating an improvement trigger."""

    failure_key: str
    trigger_reason: TriggerReason = TriggerReason.MANUAL_DEMO_TRIGGER
    occurrence_count: int = 1
    example_run_ids: list[str] = []


class PatchImprovementRequest(BaseModel):
    """Request body for partially updating an improvement trigger."""

    status: str | None = None
    diagnosis_json: dict | None = None
    patch_proposal_json: dict | None = None


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/improvements")
async def list_improvements(
    status: str | None = None,
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List improvement triggers with optional status filter and pagination."""
    from src.db import list_improvement_triggers

    items, total = await list_improvement_triggers(
        db, status, pagination.page, pagination.page_size
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


@router.get("/improvements/{trigger_id}")
async def get_improvement(
    trigger_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get an improvement trigger with diagnosis and patch details.

    Surfaces ``change_class`` / ``change_class_label`` / ``is_high_risk``
    pulled from the prompt_version linked to this trigger. ``is_high_risk``
    is True iff change_class == ``eval_definition``; the frontend renders
    a warning badge when set.
    """
    from src.db import (
        get_improvement_trigger,
        get_prompt_version,
        get_regression_examples_for_trigger,
        list_prompt_versions,
    )

    trigger = await get_improvement_trigger(db, trigger_id)
    if not trigger:
        return ApiResponse(
            ok=False, error="Improvement trigger not found", request_id=request_id
        )

    regression_examples = await get_regression_examples_for_trigger(db, trigger_id)
    change_class_info = await _resolve_change_class_for_trigger(
        trigger, db, get_prompt_version, list_prompt_versions
    )

    return ApiResponse(
        ok=True,
        data={
            "trigger": trigger.model_dump(),
            "regression_examples": [ex.model_dump() for ex in regression_examples],
            "change_class": change_class_info["change_class"],
            "change_class_label": change_class_info["change_class_label"],
            "is_high_risk": change_class_info["is_high_risk"],
        },
        request_id=request_id,
    )


_CHANGE_CLASS_LABELS: dict[ChangeClass, str] = {
    ChangeClass.PROMPT_ADDITION: "Prompt addition",
    ChangeClass.TOOL_POLICY: "Tool policy",
    ChangeClass.ROUTING: "Routing",
    ChangeClass.DATA_SOURCE: "Data source",
    ChangeClass.EVAL_DEFINITION: "Eval definition (high-risk)",
    ChangeClass.MANUAL_EDIT: "Manual edit",
    ChangeClass.SEED: "Seed",
}


async def _resolve_change_class_for_trigger(
    trigger: ImprovementTrigger,
    db: aiosqlite.Connection,
    get_prompt_version,
    list_prompt_versions,
) -> dict[str, object]:
    """Look up the change_class for the prompt_version linked to a trigger.

    Resolution order:
      1. ``trigger.patch_proposal_json['local_prompt_version_id']`` →
         direct PromptVersion lookup (the post-spec-0 happy path).
      2. Fallback: scan recent ``support-agent`` versions and find one
         whose ``improvement_trigger_id`` matches.

    Returns a dict with ``change_class`` (raw enum value or None),
    ``change_class_label`` (human-readable), and ``is_high_risk`` (bool).
    """
    version_id = None
    if trigger.patch_proposal_json:
        version_id = trigger.patch_proposal_json.get("local_prompt_version_id")

    version = None
    if version_id:
        version = await get_prompt_version(db, str(version_id))
    if version is None:
        # Fallback: scan recent versions and filter on trigger linkage.
        versions = await list_prompt_versions(db, "support-agent", limit=200)
        for v in versions:
            if v.improvement_trigger_id == trigger.improvement_trigger_id:
                version = v
                break

    if version is None or version.change_class is None:
        return {
            "change_class": None,
            "change_class_label": "Unknown",
            "is_high_risk": False,
        }

    cls = version.change_class
    return {
        "change_class": cls.value,
        "change_class_label": _CHANGE_CLASS_LABELS.get(
            cls, cls.value.replace("_", " ").title()
        ),
        "is_high_risk": cls == ChangeClass.EVAL_DEFINITION,
    }


@router.post("/improvements", status_code=201)
async def create_improvement(
    body: CreateImprovementRequest,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Manually create an improvement trigger (for demo trigger)."""
    from src.db import insert_improvement_trigger

    now = datetime.now(timezone.utc).isoformat()
    trigger = ImprovementTrigger(
        improvement_trigger_id=str(uuid.uuid4()),
        failure_key=body.failure_key,
        trigger_reason=body.trigger_reason,
        occurrence_count=body.occurrence_count,
        example_run_ids_json=body.example_run_ids,
        status="pending",
        created_at=now,
        updated_at=now,
    )
    await insert_improvement_trigger(db, trigger)

    logger.info(
        "Improvement trigger created manually: %s (failure_key=%s)",
        trigger.improvement_trigger_id,
        body.failure_key,
    )

    return ApiResponse(ok=True, data=trigger, request_id=request_id)


@router.post("/improvements/{trigger_id}/actions/analyze")
async def analyze_improvement(
    trigger_id: str,
    request: Request,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Diagnose a recurring failure cluster and synthesize a candidate patch.

    Diagnosis is delegated to an ADK sub-agent whose toolbelt is Phoenix
    MCP (see ``backend/src/agent/diagnosis_agent.py``). The agent fetches
    failing spans + their eval annotations via MCP and emits a structured
    diagnosis. When the MCP toolset isn't available (no PHOENIX_API_KEY,
    or the agent path errors), we fall back to the deterministic
    service-side ``diagnose()`` so the endpoint still produces a useful
    result.

    Patch synthesis stays on ``generate_proposal()`` — one Gemini call
    tagged ``patch_synthesis``, separate from the diagnosis_agent turns
    so the per-purpose token accounting is grep-friendly.
    """
    from src.agent.diagnosis_agent import run_diagnosis_agent
    from src.agent.prompts import get_production_prompt
    from src.db import get_improvement_trigger, update_improvement_trigger
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.diagnosis.proposal_generator import generate_proposal
    from src.diagnosis.root_cause import diagnose

    trigger = await get_improvement_trigger(db, trigger_id)
    if not trigger:
        return ApiResponse(
            ok=False, error="Improvement trigger not found", request_id=request_id
        )

    mcp_toolset = getattr(request.app.state, "phoenix_mcp_toolset", None)
    diagnosis_mcp_toolset = getattr(request.app.state, "diagnosis_mcp_toolset", None)
    current_prompt_text, _ = await get_production_prompt(db)

    from src.db import resolve_trace_ids
    example_trace_ids = await resolve_trace_ids(db, trigger.example_run_ids_json)

    diagnosis: dict
    if mcp_toolset is not None:
        diagnosis = await run_diagnosis_agent(
            trigger,
            diagnosis_mcp_toolset or mcp_toolset,
            phoenixloop_cycle_id=trigger.improvement_trigger_id,
            example_trace_ids=example_trace_ids,
            db=db,
        )
        # ``mcp_status == "agent_fallback"`` means the agent path ran but
        # didn't produce usable structured output — drop to the legacy
        # path so the endpoint still returns something credible.
        if diagnosis.get("mcp_status") == "agent_fallback":
            logger.warning(
                "Diagnosis agent fell back for trigger %s — running service-side diagnose()",
                trigger_id,
            )
            mcp_client = PhoenixMCPClient()
            diagnosis = await diagnose(
                trigger, mcp_client, current_prompt=current_prompt_text
            )
    else:
        logger.info(
            "No Phoenix MCP toolset on app.state — using service-side diagnose()"
        )
        mcp_client = PhoenixMCPClient()
        diagnosis = await diagnose(
            trigger, mcp_client, current_prompt=current_prompt_text
        )

    trigger.diagnosis_json = diagnosis
    trigger.status = "diagnosed"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()

    proposal_mcp_client = PhoenixMCPClient()
    proposal = await generate_proposal(
        trigger,
        diagnosis,
        proposal_mcp_client,
        current_prompt=current_prompt_text,
        db=db,
    )
    trigger.patch_proposal_json = proposal
    trigger.status = "proposal_ready"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()

    await update_improvement_trigger(db, trigger)

    logger.info(
        "Analysis complete for trigger %s: diagnosis confidence=%.2f via %s",
        trigger_id,
        diagnosis.get("confidence", 0.0),
        "agent" if diagnosis.get("mcp_status") == "completed" else "service",
    )

    return ApiResponse(
        ok=True,
        data={
            "trigger": trigger.model_dump(),
            "diagnosis": diagnosis,
            "proposal": proposal,
        },
        request_id=request_id,
    )


@router.post("/improvements/{trigger_id}/actions/generate-regressions")
async def generate_regressions(
    trigger_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Generate regression test cases for an improvement trigger."""
    from src.db import (
        get_improvement_trigger,
        insert_regression_example,
        update_improvement_trigger,
    )
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient
    from src.diagnosis.proposal_generator import generate_regression_examples

    trigger = await get_improvement_trigger(db, trigger_id)
    if not trigger:
        return ApiResponse(
            ok=False, error="Improvement trigger not found", request_id=request_id
        )

    if not trigger.diagnosis_json:
        return ApiResponse(
            ok=False,
            error="Trigger must be diagnosed before generating regressions",
            request_id=request_id,
        )

    mcp_client = PhoenixMCPClient()
    examples = await generate_regression_examples(
        trigger, trigger.diagnosis_json, mcp_client
    )

    for example in examples:
        await insert_regression_example(db, example)

    # Update trigger with regression info
    trigger.regression_examples_json = [ex.model_dump() for ex in examples]
    trigger.status = "regressions_ready"
    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    await update_improvement_trigger(db, trigger)

    logger.info(
        "Generated %d regression examples for trigger %s",
        len(examples),
        trigger_id,
    )

    return ApiResponse(
        ok=True,
        data=[ex.model_dump() for ex in examples],
        request_id=request_id,
    )


@router.post("/improvements/{trigger_id}/actions/auto-promote-failures")
async def auto_promote_failures(
    trigger_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Promote a trigger's example_run_ids to regression_examples on demand.

    Idempotent — re-running on a trigger that already has regression rows
    is a no-op (returns ``promoted=0``). Used for triggers that pre-date
    the auto-promote-on-threshold-trip pipeline, or to manually backfill
    a trigger after a failed promotion attempt.

    Returns ``{"promoted": int}`` indicating how many new regression rows
    were inserted by this call.
    """
    from src.db import get_improvement_trigger
    from src.diagnosis.failure_aggregator import (
        auto_promote_trigger_to_regression_examples,
    )

    trigger = await get_improvement_trigger(db, trigger_id)
    if not trigger:
        return ApiResponse(
            ok=False, error="Improvement trigger not found", request_id=request_id
        )

    promoted = await auto_promote_trigger_to_regression_examples(trigger, db)
    logger.info(
        "Manual auto-promote on trigger %s: promoted %d examples",
        trigger_id,
        promoted,
    )
    return ApiResponse(
        ok=True, data={"promoted": promoted}, request_id=request_id
    )


@router.patch("/improvements/{trigger_id}")
async def patch_improvement(
    trigger_id: str,
    body: PatchImprovementRequest,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Partially update an improvement trigger."""
    from src.db import get_improvement_trigger, update_improvement_trigger

    trigger = await get_improvement_trigger(db, trigger_id)
    if not trigger:
        return ApiResponse(
            ok=False, error="Improvement trigger not found", request_id=request_id
        )

    if body.status is not None:
        trigger.status = body.status
    if body.diagnosis_json is not None:
        trigger.diagnosis_json = body.diagnosis_json
    if body.patch_proposal_json is not None:
        trigger.patch_proposal_json = body.patch_proposal_json

    trigger.updated_at = datetime.now(timezone.utc).isoformat()
    await update_improvement_trigger(db, trigger)

    logger.info("Improvement trigger %s updated", trigger_id)

    return ApiResponse(ok=True, data=trigger, request_id=request_id)
