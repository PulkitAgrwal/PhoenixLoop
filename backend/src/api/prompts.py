"""Prompts API routes — version history, active-version lookup, manual editing."""

import logging
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.db import (
    get_prompt as db_get_prompt,
)
from src.db import (
    get_prompt_version as db_get_version,
)
from src.db import (
    insert_prompt_version,
)
from src.db import (
    list_prompt_versions as db_list_versions,
)
from src.db import (
    list_prompts as db_list_prompts,
)
from src.experiments.runner import (
    PromptVersionNotFoundError,
    create_experiment_from_versions,
)
from src.models import (
    ApiResponse,
    CreatePromptVersionRequest,
    PaginatedData,
    PromptSource,
    PromptVersion,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["prompts"])


@router.get("/prompts")
async def list_prompts(
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List all prompts. Single-page; the table is expected to stay tiny."""
    items = await db_list_prompts(db)
    return ApiResponse(
        ok=True,
        data=PaginatedData(
            items=items,
            total_count=len(items),
            page=pagination.page,
            page_size=pagination.page_size,
            has_next=False,
        ),
        request_id=request_id,
    )


@router.get("/prompts/{identifier}")
async def get_prompt_by_id(
    identifier: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get a single prompt by identifier."""
    prompt = await db_get_prompt(db, identifier)
    if prompt is None:
        return ApiResponse(ok=False, error="Prompt not found", request_id=request_id)
    return ApiResponse(ok=True, data=prompt, request_id=request_id)


@router.get("/prompts/{identifier}/versions")
async def list_versions(
    identifier: str,
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """List versions for a prompt, newest first, with pagination."""
    prompt = await db_get_prompt(db, identifier)
    if prompt is None:
        return ApiResponse(ok=False, error="Prompt not found", request_id=request_id)

    offset = (pagination.page - 1) * pagination.page_size
    versions = await db_list_versions(
        db, identifier, pagination.page_size, offset
    )
    return ApiResponse(
        ok=True,
        data=PaginatedData(
            items=versions,
            total_count=len(versions),
            page=pagination.page,
            page_size=pagination.page_size,
            has_next=len(versions) == pagination.page_size,
        ),
        request_id=request_id,
    )


@router.get("/prompts/{identifier}/versions/{version_id}")
async def get_version_by_id(
    identifier: str,
    version_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Get a single prompt version, scoped to the parent identifier."""
    version = await db_get_version(db, version_id)
    if version is None or version.prompt_identifier != identifier:
        return ApiResponse(
            ok=False, error="Version not found", request_id=request_id
        )
    return ApiResponse(ok=True, data=version, request_id=request_id)


def _auto_version_tag(existing_count: int) -> str:
    """Generate a deterministic ``manual-YYYY-MM-DD-NNN`` tag."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"manual-{today}-{existing_count + 1:03d}"


@router.post("/prompts/{identifier}/versions")
async def create_version(
    identifier: str,
    body: CreatePromptVersionRequest,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Create a new manual prompt version.

    Does NOT change ``prompts.active_version_id`` — promotion happens through
    the experiment + release-gate flow only.
    """
    prompt = await db_get_prompt(db, identifier)
    if prompt is None:
        return ApiResponse(
            ok=False, error="Prompt not found", request_id=request_id
        )

    # Best-effort uniqueness check on version_tag. The number of existing
    # versions for any one prompt is small, so a full scan is acceptable.
    existing = await db_list_versions(db, identifier, limit=10_000)
    version_tag = body.version_tag or _auto_version_tag(len(existing))
    if any(v.version_tag == version_tag for v in existing):
        return ApiResponse(
            ok=False,
            error=f"Version tag '{version_tag}' already exists",
            request_id=request_id,
        )

    metadata = {"description": body.description} if body.description else {}
    new_version = PromptVersion(
        prompt_version_id=str(uuid.uuid4()),
        prompt_identifier=identifier,
        version_tag=version_tag,
        prompt_text=body.prompt_text,
        parent_version_id=prompt.active_version_id,
        source=PromptSource.MANUAL,
        improvement_trigger_id=None,
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata_json=metadata,
    )
    await insert_prompt_version(db, new_version)
    logger.info(
        "Created manual prompt version %s (tag=%s, %d chars)",
        new_version.prompt_version_id,
        version_tag,
        len(body.prompt_text),
    )
    return ApiResponse(ok=True, data=new_version, request_id=request_id)


@router.post("/prompts/{identifier}/versions/{version_id}/actions/experiment")
async def launch_experiment(
    identifier: str,
    version_id: str,
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Launch an A/B experiment with this version as candidate."""
    prompt = await db_get_prompt(db, identifier)
    if prompt is None or prompt.active_version_id is None:
        return ApiResponse(
            ok=False,
            error="Cannot launch experiment: prompt has no active version",
            request_id=request_id,
        )

    candidate = await db_get_version(db, version_id)
    if candidate is None or candidate.prompt_identifier != identifier:
        return ApiResponse(
            ok=False, error="Version not found", request_id=request_id
        )

    try:
        experiment = await create_experiment_from_versions(
            db=db,
            baseline_version_id=prompt.active_version_id,
            candidate_version_id=version_id,
        )
    except PromptVersionNotFoundError as e:
        return ApiResponse(ok=False, error=str(e), request_id=request_id)

    logger.info(
        "Launched experiment %s from manual version %s",
        experiment.experiment_id,
        version_id,
    )
    return ApiResponse(
        ok=True,
        data={"experiment_id": experiment.experiment_id},
        request_id=request_id,
    )
