"""Read-only config dump (secrets redacted) for the Settings page."""

import logging

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import get_db_session, get_request_id
from src.models import ApiResponse, ConfigResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["config"])


def _redact(value: str | None) -> str:
    """Return a redaction marker, never the raw value."""
    return "<configured>" if value else "<missing>"


@router.get("/config")
async def get_config(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Return the sanitized application settings for display on the Settings page."""
    from src.agent.support_agent import AGENT_NAME, AGENT_VERSION
    from src.config import get_settings
    from src.db import get_prompt, get_prompt_version

    s = get_settings()

    # Resolve active prompt version tag
    active_tag: str | None = None
    prompt = await get_prompt(db, "support-agent")
    if prompt and prompt.active_version_id:
        version = await get_prompt_version(db, prompt.active_version_id)
        if version:
            active_tag = version.version_tag

    cfg = ConfigResponse(
        app_env=s.app_env,
        database_url=s.database_url,
        gemini_model=s.gemini_model,
        google_api_key=_redact(s.google_api_key),
        phoenix_base_url=s.phoenix_base_url,
        phoenix_api_key=_redact(s.phoenix_api_key),
        phoenix_project_name=s.phoenix_project_name,
        repeated_failure_count=s.repeated_failure_count,
        repeated_failure_rate=s.repeated_failure_rate,
        critical_failure_immediate=s.critical_failure_immediate,
        cooldown_minutes=s.cooldown_minutes,
        release_score_threshold=s.release_score_threshold,
        latency_budget_ms=s.latency_budget_ms,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        active_prompt_version=active_tag,
    )
    logger.debug("config endpoint served (request_id=%s)", request_id)
    return ApiResponse(ok=True, data=cfg, request_id=request_id)
