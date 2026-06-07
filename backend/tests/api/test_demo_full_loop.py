"""Tests for POST /api/demo/full-loop."""

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
    """TestClient with a temp-file SQLite DB so seeded data persists across calls."""
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


def test_full_loop_returns_seeded_failure_summary(client):
    """The endpoint synthesizes 5 failure-cluster runs and reports their status."""
    client.post("/api/demo/seed")
    response = client.post("/api/demo/full-loop")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["synthesized_runs"] == 5
    assert "failure_key" in data
    assert "trigger_created" in data
