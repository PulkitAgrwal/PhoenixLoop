"""Tests for the GET /api/stats endpoint."""

import json
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from src.db import (
    init_db,
    insert_agent_run,
    insert_conversation_session,
    insert_release_gate_decision,
    insert_ticket,
)
from src.main import app
from src.models import (
    AgentRun,
    ConversationSession,
    ReleaseDecision,
    ReleaseGateDecision,
    SupportTicket,
    TicketCategory,
    ToolCallRecord,
)


@pytest.fixture
async def temp_db(tmp_path, monkeypatch):
    """Point the DB session at a fresh per-test SQLite file."""
    db_path = tmp_path / "stats.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    # Clear the lru_cache on get_settings so the override takes effect
    from src.config import get_settings

    get_settings.cache_clear()
    await init_db(str(db_path))
    yield db_path
    get_settings.cache_clear()


def _make_ticket(ticket_id: str = "TKT-S1") -> SupportTicket:
    now = datetime.now(timezone.utc).isoformat()
    return SupportTicket(
        ticket_id=ticket_id,
        customer_id="cus_5WvnX4nq",
        category=TicketCategory.REFUND,
        subject="s",
        body="b",
        metadata_json={},
        created_at=now,
        updated_at=now,
    )


def _make_agent_run(
    run_id: str,
    *,
    trace_id: str | None,
    session_id: str = "sess-1",
    tool_calls: list[dict] | None = None,
) -> AgentRun:
    now = datetime.now(timezone.utc).isoformat()
    return AgentRun(
        agent_run_id=run_id,
        conversation_session_id=session_id,
        ticket_id="TKT-S1",
        prompt_version="production",
        trace_id=trace_id,
        root_span_id="root" if trace_id else None,
        response_json={"answer": "ok"},
        tool_calls_json=[
            ToolCallRecord(
                tool_name=tc["tool_name"],
                input=tc.get("input") or {},
                output=tc.get("output") or {},
                status="success",
            )
            for tc in (tool_calls or [])
        ],
        status="success",
        latency_ms=100,
        created_at=now,
    )


def _make_session(session_id: str) -> ConversationSession:
    now = datetime.now(timezone.utc).isoformat()
    return ConversationSession(
        conversation_session_id=session_id,
        ticket_id="TKT-S1",
        started_at=now,
    )


@pytest.mark.asyncio
async def test_stats_returns_zeros_on_empty_db(temp_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        res = await ac.get("/api/stats")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    data = body["data"]
    assert data["agent_runs_traced"] == 0
    assert data["evaluators_wired"] == 14
    assert data["mcp_tool_calls_per_run_avg"] == 0.0
    assert data["prompts_auto_promoted"] == 0


@pytest.mark.asyncio
async def test_stats_counts_traced_runs_only(temp_db):
    from src.db import get_db

    async with get_db(str(temp_db)) as db:
        await insert_ticket(db, _make_ticket())
        await insert_conversation_session(db, _make_session("sess-1"))
        await insert_conversation_session(db, _make_session("sess-2"))
        await insert_agent_run(
            db,
            _make_agent_run("run-traced-1", trace_id="abc123", session_id="sess-1"),
        )
        await insert_agent_run(
            db, _make_agent_run("run-untraced-1", trace_id=None, session_id="sess-2")
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        res = await ac.get("/api/stats")
    data = res.json()["data"]
    assert data["agent_runs_traced"] == 1


@pytest.mark.asyncio
async def test_stats_avg_mcp_calls_per_run(temp_db):
    """MCP tool calls average across the most-recent runs."""
    from src.db import get_db

    async with get_db(str(temp_db)) as db:
        await insert_ticket(db, _make_ticket())
        await insert_conversation_session(db, _make_session("sess-1"))
        await insert_conversation_session(db, _make_session("sess-2"))
        await insert_agent_run(
            db,
            _make_agent_run(
                "run-mcp-1",
                trace_id="t1",
                session_id="sess-1",
                tool_calls=[
                    {"tool_name": "search_policy"},
                    {"tool_name": "phoenix-mcp:get-spans"},
                    {"tool_name": "get-dataset-examples"},
                ],
            ),
        )
        await insert_agent_run(
            db,
            _make_agent_run(
                "run-mcp-2",
                trace_id="t2",
                session_id="sess-2",
                tool_calls=[{"tool_name": "get_customer_context"}],
            ),
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        res = await ac.get("/api/stats")
    data = res.json()["data"]
    # run 1 has 2 MCP-ish tools (phoenix-mcp:get-spans, get-dataset-examples),
    # run 2 has 0 → avg = 1.0
    assert data["mcp_tool_calls_per_run_avg"] == 1.0


@pytest.mark.asyncio
async def test_stats_counts_promoted_decisions(temp_db):
    from src.db import (
        get_db,
        insert_experiment,
        insert_improvement_trigger,
    )
    from src.models import (
        ExperimentRecord,
        ExperimentStatus,
        ImprovementTrigger,
        TriggerReason,
    )

    async with get_db(str(temp_db)) as db:
        now = datetime.now(timezone.utc).isoformat()
        await insert_ticket(db, _make_ticket())
        trigger = ImprovementTrigger(
            improvement_trigger_id="trig-1",
            failure_key="fk",
            trigger_reason=TriggerReason.MANUAL_DEMO_TRIGGER,
            occurrence_count=1,
            example_run_ids_json=[],
            status="closed",
            created_at=now,
            updated_at=now,
        )
        await insert_improvement_trigger(db, trigger)
        experiment = ExperimentRecord(
            experiment_id="exp-1",
            improvement_trigger_id="trig-1",
            baseline_prompt_version="v1",
            candidate_prompt_version="v2",
            dataset_id="d",
            status=ExperimentStatus.COMPLETED,
            created_at=now,
        )
        await insert_experiment(db, experiment)
        await insert_release_gate_decision(
            db,
            ReleaseGateDecision(
                release_gate_decision_id=str(uuid.uuid4()),
                experiment_id="exp-1",
                decision=ReleaseDecision.PROMOTED,
                release_score=0.9,
                promotion_rules_passed=6,
                requires_human_approval=False,
                decided_at=now,
            ),
        )
        await insert_release_gate_decision(
            db,
            ReleaseGateDecision(
                release_gate_decision_id=str(uuid.uuid4()),
                experiment_id="exp-1",
                decision=ReleaseDecision.REJECTED,
                release_score=0.4,
                promotion_rules_passed=2,
                requires_human_approval=False,
                decided_at=now,
            ),
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as ac:
        res = await ac.get("/api/stats")
    data = res.json()["data"]
    assert data["prompts_auto_promoted"] == 1


# Removed unused import warning helper
_ = json  # imported but only used implicitly via httpx response.json()
