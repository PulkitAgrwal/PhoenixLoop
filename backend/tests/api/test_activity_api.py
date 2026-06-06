"""Tests for /api/activity."""

import asyncio
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from src.api.dependencies import get_db_session
from src.db import get_db, init_db
from src.main import app


@pytest.fixture
def client():
    """A TestClient with a temp-file SQLite DB so events seeded in tests are visible."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    asyncio.run(init_db(path))

    async def override_get_db_session():
        async with get_db(path) as conn:
            yield conn

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        for p in (path, path + "-wal", path + "-shm"):
            try:
                os.unlink(p)
            except FileNotFoundError:
                continue


def test_activity_returns_envelope(client):
    res = client.get("/api/activity?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert isinstance(body["data"], list)


def test_activity_items_have_required_fields(client):
    res = client.get("/api/activity?limit=5")
    body = res.json()
    items = body["data"]
    for item in items:
        assert "event_id" in item
        assert "kind" in item
        assert "title" in item
        assert "timestamp" in item


def test_activity_limit_caps_at_50(client):
    res = client.get("/api/activity?limit=500")
    # The global RequestValidationError handler maps validation failures to
    # 400 (bad request) so they fit the standard ApiResponse envelope.
    assert res.status_code == 400
    body = res.json()
    assert body["ok"] is False
    assert "limit" in (body.get("error") or "").lower()


def test_activity_limit_50_is_allowed(client):
    res = client.get("/api/activity?limit=50")
    assert res.status_code == 200
    body = res.json()
    assert len(body["data"]) <= 50
