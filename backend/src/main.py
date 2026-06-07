"""PhoenixLoop FastAPI application."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.activity import router as activity_router
from src.api.config_api import router as config_router
from src.api.conversations import router as conversations_router
from src.api.demo import router as demo_router
from src.api.evals import router as evals_router
from src.api.experiments import router as experiments_router
from src.api.healing import router as healing_router
from src.api.improvements import router as improvements_router
from src.api.middleware import RequestIdMiddleware, register_exception_handlers
from src.api.prompts import router as prompts_router
from src.api.release_gate import router as release_gate_router
from src.api.stats import router as stats_router
from src.api.tickets import router as tickets_router
from src.config import get_settings
from src.db import init_db
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: init DB, instrumentation, and annotation configs."""
    settings = get_settings()
    setup_logging(settings.app_env)
    logger.info("PhoenixLoop starting up...")

    # Google ADK / google-genai read GOOGLE_API_KEY directly from os.environ,
    # so we forward the value loaded by pydantic-settings here.
    if settings.google_api_key:
        os.environ.setdefault("GOOGLE_API_KEY", settings.google_api_key)
    if settings.google_genai_use_vertexai:
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")

    db_path = settings.database_url.replace("sqlite:///", "")
    await init_db(db_path)
    logger.info("Database initialized")

    try:
        from src.tracing.instrumentor import setup_instrumentation

        setup_instrumentation()
        logger.info("OpenInference instrumentation configured")
    except Exception as exc:
        logger.warning("Instrumentation setup failed (non-fatal): %s", exc)

    try:
        from src.tracing.annotations import register_annotation_configs
        from src.tracing.phoenix_client import get_phoenix_client

        phoenix = get_phoenix_client()
        if phoenix:
            register_annotation_configs(phoenix)
            logger.info("Annotation configs registered")
    except Exception as exc:
        logger.warning("Annotation config registration failed (non-fatal): %s", exc)

    # Build the Phoenix MCP toolset once at startup so its stdio session
    # outlives any single request. ADK's MCPSessionManager caches the
    # session per-toolset; per-request agents share the warm connection.
    app.state.phoenix_mcp_toolset = None
    try:
        from src.agent.mcp_tools import build_phoenix_mcp_toolset

        toolset = build_phoenix_mcp_toolset()
        if toolset is not None:
            # Pre-warm: forces the stdio_client to spawn `npx`, the MCP
            # handshake to complete, and the tools list to be cached. Pays
            # the ~60s cold start now instead of on the first user request.
            tools = await toolset.get_tools()
            app.state.phoenix_mcp_toolset = toolset
            logger.info(
                "Phoenix MCP toolset warmed at startup (tool count=%d)",
                len(tools),
            )
    except Exception as exc:
        logger.warning(
            "Phoenix MCP toolset warm-up failed (non-fatal): %s", exc
        )
        app.state.phoenix_mcp_toolset = None

    # Auto-seed runs in the background so the API is reachable immediately.
    # Live mode takes 60-90s (real Gemini calls + diagnosis + experiment);
    # blocking the lifespan on it forces docker-compose health-checks to
    # fail before the seed finishes. Idempotent — full_loop_seed short-
    # circuits when agent_runs is non-empty.
    db_path = settings.database_url.replace("sqlite:///", "")
    mcp_toolset = app.state.phoenix_mcp_toolset

    async def _seed_in_background() -> None:
        try:
            from src.api.seed import full_loop_seed
            from src.db import get_db

            async with get_db(db_path) as db:
                summary = await full_loop_seed(db, mcp_toolset=mcp_toolset)
            if not summary.get("skipped"):
                logger.info("auto-seed complete: %s", summary)
            else:
                logger.info("auto-seed skipped (already populated)")
        except Exception as exc:
            logger.warning(
                "auto-seed failed (non-fatal): %s", exc, exc_info=True
            )

    if settings.skip_autoseed:
        app.state.seed_task = None
        logger.info("PhoenixLoop ready (auto-seed disabled via SKIP_AUTOSEED)")
    else:
        app.state.seed_task = asyncio.create_task(_seed_in_background())
        logger.info("PhoenixLoop ready (auto-seed running in background)")
    yield
    logger.info("PhoenixLoop shutting down")

    # Cancel the background seed if still running, so shutdown doesn't hang.
    seed_task = getattr(app.state, "seed_task", None)
    if seed_task is not None and not seed_task.done():
        seed_task.cancel()
        try:
            await seed_task
        except (asyncio.CancelledError, Exception):
            pass

    toolset = getattr(app.state, "phoenix_mcp_toolset", None)
    if toolset is not None:
        try:
            await toolset.close()
        except Exception as exc:
            logger.warning(
                "Phoenix MCP toolset close failed (non-fatal): %s", exc
            )


app = FastAPI(title="PhoenixLoop API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdMiddleware)
register_exception_handlers(app)

app.include_router(tickets_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(evals_router, prefix="/api")
app.include_router(improvements_router, prefix="/api")
app.include_router(experiments_router, prefix="/api")
app.include_router(release_gate_router, prefix="/api")
app.include_router(prompts_router, prefix="/api")
app.include_router(activity_router, prefix="/api")
app.include_router(config_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(demo_router, prefix="/api")
app.include_router(healing_router, prefix="/api")
