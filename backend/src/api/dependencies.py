"""Shared FastAPI dependencies."""

import uuid
from typing import Optional

from fastapi import Header

from src.config import get_settings
from src.db import get_db


async def get_db_session():
    """Yield a database connection from the configured database path."""
    settings = get_settings()
    # Extract path from sqlite:///path format
    db_path = settings.database_url.replace("sqlite:///", "")
    async with get_db(db_path) as db:
        yield db


async def get_request_id(x_request_id: Optional[str] = Header(None)) -> str:
    """Extract or generate a request ID for tracing."""
    return x_request_id or str(uuid.uuid4())


async def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None),
) -> Optional[str]:
    """Extract the optional idempotency key from request headers."""
    return idempotency_key


class PaginationParams:
    """Reusable pagination parameters with validation."""

    def __init__(self, page: int = 1, page_size: int = 20):
        self.page = max(1, page)
        self.page_size = min(100, max(1, page_size))
        self.offset = (self.page - 1) * self.page_size
