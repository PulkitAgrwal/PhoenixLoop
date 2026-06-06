"""Tests for /api/config."""

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
    """A TestClient with a temp-file SQLite DB seeded by init_db."""
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


def test_config_redacts_secrets(client):
    res = client.get("/api/config")
    body = res.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["google_api_key"] in ("<configured>", "<missing>")
    assert data["phoenix_api_key"] in ("<configured>", "<missing>")
    # Real values must NEVER leak
    assert not data["google_api_key"].startswith("AQ")
    assert not data["phoenix_api_key"].startswith("eyJ")


def test_config_includes_active_prompt(client):
    res = client.get("/api/config")
    body = res.json()
    assert "active_prompt_version" in body["data"]


def test_config_includes_thresholds(client):
    res = client.get("/api/config")
    data = res.json()["data"]
    assert "repeated_failure_count" in data
    assert "release_score_threshold" in data
    assert "latency_budget_ms" in data
