"""Request ID middleware and global exception handlers."""

import logging
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from src.exceptions import (
    AgentRunError,
    ConfigurationError,
    DatabaseError,
    ExperimentError,
    IdempotencyConflictError,
    MCPConnectionError,
    PhoenixLoopError,
    ReleaseGateError,
)

logger = logging.getLogger(__name__)
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Inject and propagate a request ID on every request/response cycle."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or str(uuid.uuid4())
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response


def _error_response(status: int, error: str, request_id: str) -> JSONResponse:
    """Build a standard error envelope as a JSONResponse."""
    return JSONResponse(
        status_code=status,
        content={
            "ok": False,
            "data": None,
            "error": error,
            "request_id": request_id,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register domain-specific and fallback exception handlers on the app."""

    @app.exception_handler(RequestValidationError)
    async def handle_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        # Surface the first field/message pair so callers get a focused error
        # rather than the full pydantic dump. The full detail still hits logs.
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []) if p != "body")
        msg = first.get("msg", "validation error")
        summary = f"{loc}: {msg}" if loc else msg
        logger.warning("Validation error: %s", exc.errors())
        return _error_response(400, summary, rid)

    @app.exception_handler(IdempotencyConflictError)
    async def handle_idempotency(
        request: Request, exc: IdempotencyConflictError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        return _error_response(409, str(exc), rid)

    @app.exception_handler(AgentRunError)
    async def handle_agent_run(
        request: Request, exc: AgentRunError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Agent run error: %s", exc, exc_info=True)
        return _error_response(502, str(exc), rid)

    @app.exception_handler(MCPConnectionError)
    async def handle_mcp(
        request: Request, exc: MCPConnectionError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        return _error_response(503, str(exc), rid)

    @app.exception_handler(ConfigurationError)
    async def handle_config(
        request: Request, exc: ConfigurationError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Configuration error: %s", exc, exc_info=True)
        return _error_response(500, str(exc), rid)

    @app.exception_handler(ExperimentError)
    async def handle_experiment(
        request: Request, exc: ExperimentError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Experiment error: %s", exc, exc_info=True)
        return _error_response(500, str(exc), rid)

    @app.exception_handler(ReleaseGateError)
    async def handle_release_gate(
        request: Request, exc: ReleaseGateError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Release gate error: %s", exc, exc_info=True)
        return _error_response(500, str(exc), rid)

    @app.exception_handler(DatabaseError)
    async def handle_db(
        request: Request, exc: DatabaseError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Database error: %s", exc, exc_info=True)
        return _error_response(500, str(exc), rid)

    @app.exception_handler(PhoenixLoopError)
    async def handle_domain(
        request: Request, exc: PhoenixLoopError
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Domain error: %s", exc, exc_info=True)
        return _error_response(500, str(exc), rid)

    @app.exception_handler(Exception)
    async def handle_unhandled(
        request: Request, exc: Exception
    ) -> JSONResponse:
        rid = request_id_var.get("")
        logger.error("Unhandled error: %s", exc, exc_info=True)
        return _error_response(500, "Internal server error", rid)
