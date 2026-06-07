"""Smoke tests for /api/healing/cycles/{failure_key}."""

import asyncio
import os
import tempfile
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from src.api.dependencies import get_db_session
from src.db import (
    get_db,
    init_db,
    insert_experiment,
    insert_improvement_trigger,
    upsert_failure_aggregate,
)
from src.main import app
from src.models import (
    ExperimentRecord,
    ExperimentStatus,
    FailureAggregate,
    ImprovementTrigger,
    TriggerReason,
)


@pytest.fixture
def client():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    asyncio.run(init_db(path))

    async def override_get_db_session():
        async with get_db(path) as conn:
            yield conn

    app.dependency_overrides[get_db_session] = override_get_db_session
    try:
        with TestClient(app) as tc:
            yield tc, path
    finally:
        app.dependency_overrides.pop(get_db_session, None)
        for p in (path, path + "-wal", path + "-shm"):
            try:
                os.unlink(p)
            except FileNotFoundError:
                continue


async def _seed_cycle(db_path: str, failure_key: str) -> str:
    """Insert one aggregate + trigger + experiment for the failure_key."""
    now = datetime.now(timezone.utc).isoformat()
    async with get_db(db_path) as db:
        await upsert_failure_aggregate(
            db,
            FailureAggregate(
                failure_key=failure_key,
                failure_summary="test failure summary",
                evaluator_name="tool_sequence_evaluator",
                occurrence_count=3,
                first_seen_at=now,
                last_seen_at=now,
                example_run_ids_json=[],
                is_active=True,
                computed_at=now,
            ),
        )
        trigger = ImprovementTrigger(
            improvement_trigger_id=str(uuid.uuid4()),
            failure_key=failure_key,
            trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
            occurrence_count=3,
            example_run_ids_json=[],
            status="experiment_complete",
            created_at=now,
            updated_at=now,
        )
        await insert_improvement_trigger(db, trigger)
        await insert_experiment(
            db,
            ExperimentRecord(
                experiment_id=str(uuid.uuid4()),
                improvement_trigger_id=trigger.improvement_trigger_id,
                baseline_prompt_version="v1",
                candidate_prompt_version="v2",
                dataset_id=f"regression-{failure_key}",
                status=ExperimentStatus.COMPLETED,
                baseline_release_score=0.7,
                candidate_release_score=0.9,
                created_at=now,
            ),
        )
        return trigger.improvement_trigger_id


def test_unknown_failure_key_returns_ok_with_empty_data(client):
    tc, _ = client
    res = tc.get("/api/healing/cycles/no-such-key")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["data"]["failure_key"] == "no-such-key"
    assert body["data"]["latest_trigger"] is None
    assert body["data"]["experiments"] == []


def test_known_failure_key_returns_populated_cycle(client):
    tc, path = client
    fk = "citation_presence::test"
    asyncio.run(_seed_cycle(path, fk))
    res = tc.get(f"/api/healing/cycles/{fk}")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["failure_key"] == fk
    assert len(data["failure_aggregates"]) == 1
    assert len(data["triggers"]) == 1
    assert data["latest_trigger"]["failure_key"] == fk
    assert len(data["experiments"]) == 1
    assert data["experiments"][0]["candidate_release_score"] == 0.9
