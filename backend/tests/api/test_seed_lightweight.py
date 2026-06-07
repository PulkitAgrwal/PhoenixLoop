"""Tests for the LIGHTWEIGHT_DEMO fixture-loader seed path.

These exercise the actual fixture files checked into
``backend/tests/fixtures/seed/`` — if a maintainer breaks the schema by
editing those files badly, the suite turns red.
"""

import pytest
from src.api.seed import _agent_runs_count, full_loop_seed
from src.db import (
    get_active_failure_aggregates,
    get_db,
    get_improvement_trigger,
    get_release_gate_for_experiment,
    init_db,
    list_experiments,
    list_improvement_triggers,
    list_tickets,
)


@pytest.fixture
async def lightweight_db(tmp_path, monkeypatch):
    """Fresh DB + LIGHTWEIGHT_DEMO=true."""
    db_path = tmp_path / "lightweight.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("LIGHTWEIGHT_DEMO", "true")
    from src.config import get_settings

    get_settings.cache_clear()
    await init_db(str(db_path))
    yield db_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_lightweight_seed_populates_full_loop(lightweight_db):
    async with get_db(str(lightweight_db)) as db:
        summary = await full_loop_seed(db)

    assert summary["mode"] == "lightweight"
    assert summary["tickets"] == 6
    assert summary["agent_runs"] == 6
    assert summary["eval_results"] >= 6
    assert summary["improvement_triggers"] == 1
    assert summary["experiments"] == 1
    assert summary["release_gate_decisions"] == 1

    async with get_db(str(lightweight_db)) as db:
        tickets, _ = await list_tickets(db, category=None, page=1, page_size=100)
        assert len(tickets) == 6

        triggers, _ = await list_improvement_triggers(
            db, status=None, page=1, page_size=10
        )
        assert len(triggers) == 1
        assert triggers[0].diagnosis_json is not None
        assert triggers[0].patch_proposal_json is not None

        # The fixture marks the trigger as 'diagnosed' (matching what the
        # full live pipeline would emit when the experiment completes).
        assert triggers[0].status == "diagnosed"

        experiments, _ = await list_experiments(db, page=1, page_size=10)
        assert len(experiments) == 1
        exp = experiments[0]
        assert exp.baseline_release_score is not None
        assert exp.candidate_release_score is not None
        # Baseline + candidate must be DIFFERENT and non-zero so the UI
        # scoreboard has a visible delta. Without this guarantee the
        # whole point of LIGHTWEIGHT_DEMO is gone.
        assert exp.baseline_release_score != exp.candidate_release_score
        assert exp.candidate_release_score > exp.baseline_release_score

        gate = await get_release_gate_for_experiment(db, exp.experiment_id)
        assert gate is not None
        assert gate.release_score > 0.0
        assert gate.promotion_rules_passed >= 1

        aggregates = await get_active_failure_aggregates(db)
        assert len(aggregates) == 1
        assert aggregates[0].occurrence_count == 2


@pytest.mark.asyncio
async def test_lightweight_seed_is_idempotent(lightweight_db):
    """A second seed call exits with skipped=True and does NOT re-insert."""
    async with get_db(str(lightweight_db)) as db:
        first = await full_loop_seed(db)
        assert first.get("skipped") is not True

        second = await full_loop_seed(db)
        assert second.get("skipped") is True
        assert "agent_runs" in second.get("reason", "")

    async with get_db(str(lightweight_db)) as db:
        assert await _agent_runs_count(db) == 6


@pytest.mark.asyncio
async def test_lightweight_seed_links_failure_to_trigger(lightweight_db):
    """The failure_key on the aggregate must match the trigger's failure_key."""
    async with get_db(str(lightweight_db)) as db:
        await full_loop_seed(db)
        aggregates = await get_active_failure_aggregates(db)
        triggers, _ = await list_improvement_triggers(
            db, status=None, page=1, page_size=10
        )
        assert aggregates[0].failure_key == triggers[0].failure_key


@pytest.mark.asyncio
async def test_lightweight_seed_writes_proposal_with_candidate_text(lightweight_db):
    async with get_db(str(lightweight_db)) as db:
        await full_loop_seed(db)
        triggers, _ = await list_improvement_triggers(
            db, status=None, page=1, page_size=10
        )
        trigger = await get_improvement_trigger(
            db, triggers[0].improvement_trigger_id
        )
        assert trigger is not None
        proposal = trigger.patch_proposal_json or {}
        assert proposal.get("local_prompt_version_id")
        assert proposal.get("patch_type")
        assert "POL-REFUND" in proposal.get("proposed_change", "")
