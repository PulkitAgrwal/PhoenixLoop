"""Tests for /api/prompts POST endpoints (manual version + experiment launch)."""

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
    """TestClient backed by a temp on-disk SQLite DB so seed + requests
    share state. Mirrors the fixture in ``test_prompts_api.py``."""
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


def test_create_version_rejects_empty_text(client):
    res = client.post(
        "/api/prompts/support-agent/versions",
        json={"prompt_text": "", "description": "test"},
    )
    body = res.json()
    assert body["ok"] is False
    assert "prompt_text" in str(body.get("error", "")).lower()


def test_create_version_rejects_oversize(client):
    res = client.post(
        "/api/prompts/support-agent/versions",
        json={"prompt_text": "x" * 200_001},
    )
    body = res.json()
    assert body["ok"] is False


def test_create_version_succeeds_with_valid_text(client):
    res = client.post(
        "/api/prompts/support-agent/versions",
        json={
            "prompt_text": "You are a helpful agent.\n\nFollow the rules.",
            "description": "tightened wording",
        },
    )
    body = res.json()
    assert body["ok"] is True, body
    assert "prompt_version_id" in body["data"]
    assert body["data"]["source"] == "manual"
    assert body["data"]["version_tag"].startswith("manual-")


def test_create_version_rejects_unknown_prompt(client):
    res = client.post(
        "/api/prompts/does-not-exist/versions",
        json={"prompt_text": "anything"},
    )
    body = res.json()
    assert body["ok"] is False
    assert "not found" in body["error"].lower()


def test_create_version_rejects_duplicate_tag(client):
    payload = {
        "prompt_text": "First version body.",
        "version_tag": "explicit-tag-1",
    }
    first = client.post(
        "/api/prompts/support-agent/versions", json=payload
    ).json()
    assert first["ok"] is True
    second = client.post(
        "/api/prompts/support-agent/versions", json=payload
    ).json()
    assert second["ok"] is False
    assert "already exists" in second["error"].lower()


def test_launch_experiment_from_version(client):
    create_res = client.post(
        "/api/prompts/support-agent/versions",
        json={"prompt_text": "You are a different agent."},
    ).json()
    assert create_res["ok"] is True, create_res
    vid = create_res["data"]["prompt_version_id"]

    exp_res = client.post(
        f"/api/prompts/support-agent/versions/{vid}/actions/experiment"
    ).json()
    assert exp_res["ok"] is True, exp_res
    assert "experiment_id" in exp_res["data"]


def test_launch_experiment_for_unknown_version(client):
    exp_res = client.post(
        "/api/prompts/support-agent/versions/no-such-id/actions/experiment"
    ).json()
    assert exp_res["ok"] is False
