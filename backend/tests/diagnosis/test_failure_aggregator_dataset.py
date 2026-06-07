"""Tests that update_aggregates promotes to a Phoenix dataset on threshold."""

from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pandas as pd
import pytest
from src.diagnosis.failure_aggregator import update_aggregates
from src.models import (
    AgentRun,
    AnnotationLevel,
    ConversationSession,
    EvalResult,
    EvalType,
    SupportTicket,
    TicketCategory,
)


@pytest.mark.asyncio
async def test_threshold_crossing_promotes_to_phoenix_dataset(monkeypatch, tmp_path):
    """When a failure_key's occurrence_count reaches the threshold, promote to dataset."""
    db_path = tmp_path / "test.db"

    fake_client = MagicMock()
    fake_client.add_dataset_examples = AsyncMock(return_value=None)

    monkeypatch.setattr(
        "src.diagnosis.failure_aggregator.get_phoenix_mcp_client",
        lambda: fake_client,
    )

    from src.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()
    monkeypatch.setattr(settings, "repeated_failure_count", 1, raising=False)

    from src.db import (
        init_db,
        insert_agent_run,
        insert_conversation_session,
        insert_ticket,
    )

    await init_db(str(db_path))

    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")

        ticket_id = "ticket-test"
        await insert_ticket(
            db,
            SupportTicket(
                ticket_id=ticket_id,
                customer_id="cust-1",
                category=TicketCategory.BILLING,
                subject="test",
                body="test body",
                metadata_json={},
                created_at="2026-06-06T00:00:00Z",
                updated_at="2026-06-06T00:00:00Z",
            ),
        )

        # Seed a conversation session + agent run so promotion can look up the run.
        session_id = "sess-test-promote"
        run_id = "run-1"
        await insert_conversation_session(
            db,
            ConversationSession(
                conversation_session_id=session_id,
                ticket_id=ticket_id,
                started_at="2026-06-06T00:00:00Z",
                turn_count=1,
            ),
        )
        agent_run = AgentRun(
            agent_run_id=run_id,
            conversation_session_id=session_id,
            ticket_id=ticket_id,
            agent_name="helios_support_agent",
            agent_version="1.0.0",
            prompt_version="production",
            trace_id=None,
            root_span_id=None,
            phoenix_session_id=None,
            response_json={"answer": "demo"},
            tool_calls_json=[],
            status="success",
            latency_ms=120,
            token_count_input=None,
            token_count_output=None,
            prompt_version_id=None,
            created_at="2026-06-06T00:00:00Z",
        )
        await insert_agent_run(db, agent_run)

        eval_result = EvalResult(
            eval_result_id="er-1",
            agent_run_id=run_id,
            evaluator_name="citation_presence",
            eval_type=EvalType.CODE,
            outcome="fail",
            score=0.0,
            explanation="Missing citation",
            failure_key="citation_presence::missing",
            failure_summary="Citation missing on policy answer",
            annotation_level=AnnotationLevel.SPAN,
            created_at="2026-06-06T00:00:00Z",
        )

        await update_aggregates([eval_result], db)

    fake_client.add_dataset_examples.assert_awaited_once()
    call = fake_client.add_dataset_examples.await_args
    assert call.kwargs.get("dataset_name", "").startswith("recurrent-failures"), (
        "dataset name should be prefixed 'recurrent-failures'"
    )
    df = call.kwargs.get("examples_df")
    assert isinstance(df, pd.DataFrame)
    assert len(df) >= 1
