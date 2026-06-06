"""Tests for /api/prompts GET endpoints."""

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
    """A TestClient with a temp-file SQLite DB seeded by init_db.

    The default settings point at ``sqlite:///:memory:`` which gives every
    new connection its own empty database — the lifespan-seeded prompt would
    not be visible from request handlers. We replace ``get_db_session`` with
    one that yields from a shared on-disk DB so seed and requests see the
    same tables.
    """
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


def test_list_prompts_returns_seeded(client):
    res = client.get("/api/prompts")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    items = body["data"]["items"]
    assert len(items) >= 1
    sa = next(
        (p for p in items if p["prompt_identifier"] == "support-agent"), None
    )
    assert sa is not None
    assert sa["active_version_id"] is not None


def test_get_prompt_returns_envelope_error_for_missing(client):
    res = client.get("/api/prompts/non-existent-prompt")
    assert res.status_code == 200  # envelope-style errors, not HTTP 404
    body = res.json()
    assert body["ok"] is False
    assert "not found" in body["error"].lower()


def test_list_versions_returns_seed_version(client):
    res = client.get("/api/prompts/support-agent/versions")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    items = body["data"]["items"]
    assert len(items) == 1
    assert items[0]["source"] == "seed"
    assert items[0]["version_tag"] == "v1.0.0"
    assert len(items[0]["prompt_text"]) > 100


def test_get_version_by_id(client):
    list_res = client.get("/api/prompts/support-agent/versions").json()
    vid = list_res["data"]["items"][0]["prompt_version_id"]
    res = client.get(f"/api/prompts/support-agent/versions/{vid}")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["data"]["prompt_version_id"] == vid
