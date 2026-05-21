"""PhoenixLoop FastAPI application."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.conversations import router as conversations_router
from src.api.demo import router as demo_router
from src.api.evals import router as evals_router
from src.api.experiments import router as experiments_router
from src.api.improvements import router as improvements_router
from src.api.middleware import RequestIdMiddleware, register_exception_handlers
from src.api.release_gate import router as release_gate_router
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

    logger.info("PhoenixLoop ready")
    yield
    logger.info("PhoenixLoop shutting down")


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
app.include_router(demo_router, prefix="/api")
