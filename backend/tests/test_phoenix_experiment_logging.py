"""Verifies the orchestrator pushes per-example results to Phoenix experiments."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from src.evaluation import EvalOutput
from src.experiments.orchestrator import _build_phoenix_payload
from src.models import AgentRun, SupportTicket, TicketCategory


def _ticket(idx: int) -> SupportTicket:
    return SupportTicket(
        ticket_id=f"t-{idx}",
        customer_id="cust-x",
        category=TicketCategory.REFUND,
        subject=f"s-{idx}",
        body="b",
        metadata_json={"experiment_example_id": f"ex-{idx}"},
        created_at="2026-06-07T00:00:00Z",
        updated_at="2026-06-07T00:00:00Z",
    )


def _run(idx: int) -> AgentRun:
    return AgentRun(
        agent_run_id=f"r-{idx}",
        conversation_session_id="s-1",
        ticket_id=f"t-{idx}",
        agent_name="support-agent",
        agent_version="1.0.0",
        prompt_version="production",
        trace_id=None,
        root_span_id=None,
        phoenix_session_id=None,
        response_json={"answer": f"ans-{idx}", "citations": []},
        tool_calls_json=[],
        status="success",
        latency_ms=120 + idx,
        token_count_input=None,
        token_count_output=None,
        prompt_version_id=None,
        created_at="2026-06-07T00:00:00Z",
    )


def _eval_output(idx: int, name: str, outcome: str) -> EvalOutput:
    return EvalOutput(
        evaluator_name=name,
        eval_type="code",
        outcome=outcome,
        score=1.0 if outcome == "pass" else 0.0,
        explanation=f"e-{idx}-{name}",
        failure_key=None,
        failure_summary=None,
        annotation_level="span",
    )


def test_build_phoenix_payload_shape():
    pairs = [(_ticket(0), _run(0)), (_ticket(1), _run(1))]
    per_eval = {
        "citation_presence": [_eval_output(0, "citation_presence", "pass"),
                              _eval_output(1, "citation_presence", "fail")],
        "schema_validity": [_eval_output(0, "schema_validity", "pass"),
                            _eval_output(1, "schema_validity", "pass")],
    }
    rows = _build_phoenix_payload(pairs=pairs, per_eval=per_eval)
    assert len(rows) == 2
    assert rows[0]["example_id"] == "ex-0"
    assert rows[0]["input"]["ticket_id"] == "t-0"
    assert rows[0]["output"]["answer"] == "ans-0"
    assert rows[0]["latency_ms"] == 120
    names = {e["name"] for e in rows[0]["evaluations"]}
    assert names == {"citation_presence", "schema_validity"}
    assert rows[1]["evaluations"][0]["label"] in {"pass", "fail"}


def test_build_phoenix_payload_falls_back_to_ticket_id_when_no_example_id():
    ticket = SupportTicket(
        ticket_id="t-fallback",
        customer_id="c",
        category=TicketCategory.BILLING,
        subject="s", body="b",
        metadata_json=None,
        created_at="2026-06-07T00:00:00Z",
        updated_at="2026-06-07T00:00:00Z",
    )
    rows = _build_phoenix_payload(pairs=[(ticket, _run(0))], per_eval={})
    assert rows[0]["example_id"] == "t-fallback"
    assert rows[0]["evaluations"] == []


@pytest.mark.asyncio
async def test_log_experiment_runs_swallows_sdk_failure(monkeypatch):
    """Phoenix SDK errors must NOT bubble out of the orchestrator."""
    from src.diagnosis.phoenix_mcp import PhoenixMCPClient

    client = MagicMock()
    client.experiments.resume_experiment.side_effect = RuntimeError("boom")
    mcp = PhoenixMCPClient(phoenix_client=client)
    ok = await mcp.log_experiment_runs(
        phoenix_experiment_id="exp-123",
        per_example=[{
            "example_id": "ex-1",
            "input": {"ticket_id": "t-1"}, "output": {},
            "evaluations": [], "latency_ms": 100,
        }],
    )
    assert ok is False


def _trigger_with_failure_key(failure_key: str, trigger_id: str = "IT-1"):
    from src.models import ImprovementTrigger, TriggerReason

    return ImprovementTrigger(
        improvement_trigger_id=trigger_id,
        failure_key=failure_key,
        trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
        occurrence_count=3,
        created_at="2026-06-07T00:00:00Z",
        updated_at="2026-06-07T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_mint_phoenix_experiment_ids_uses_provided_dataset_id():
    """Phoenix server slugifies dataset names containing ``::``, so a
    name-based lookup like ``regression-citation_presence::demo-cluster``
    silently returns nothing and the helper used to fall back to
    ``local-*`` stubs — which then suppressed ``log_experiment_runs``.
    The fix: caller passes the dataset_id we captured at creation time;
    the helper skips ``datasets.get_dataset`` and creates experiments
    straight from the ID.
    """
    from src.experiments.orchestrator import _mint_phoenix_experiment_ids

    client = MagicMock()
    baseline_resp = {"id": "EXP-baseline"}
    candidate_resp = {"id": "EXP-candidate"}
    client.experiments.create.side_effect = [baseline_resp, candidate_resp]

    trigger = _trigger_with_failure_key("citation_presence::demo-synthetic-cluster")

    baseline_id, candidate_id = await _mint_phoenix_experiment_ids(
        phoenix_client=client,
        trigger=trigger,
        experiment_id="exp-test-12345678",
        phoenix_dataset_id="RGF0YXNldDo4",
        baseline_label="v1",
        candidate_label="v2",
    )

    assert baseline_id == "EXP-baseline"
    assert candidate_id == "EXP-candidate"
    assert not client.datasets.get_dataset.called, (
        "must not look up by name — names with '::' get slugified"
    )
    create_calls = client.experiments.create.call_args_list
    assert len(create_calls) == 2
    for call in create_calls:
        assert call.kwargs["dataset_id"] == "RGF0YXNldDo4"


@pytest.mark.asyncio
async def test_mint_phoenix_experiment_ids_falls_back_when_no_dataset_id():
    """When no dataset_id is available (e.g. regression examples weren't
    promoted to Phoenix), fall back to local-* stub IDs without making
    any SDK call."""
    from src.experiments.orchestrator import _mint_phoenix_experiment_ids

    client = MagicMock()
    trigger = _trigger_with_failure_key("any::thing", trigger_id="IT-2")

    baseline_id, candidate_id = await _mint_phoenix_experiment_ids(
        phoenix_client=client,
        trigger=trigger,
        experiment_id="exp-test-87654321",
        phoenix_dataset_id=None,
        baseline_label="v1",
        candidate_label="v2",
    )

    assert baseline_id.startswith("local-baseline-")
    assert candidate_id.startswith("local-candidate-")
    assert not client.experiments.create.called
    assert not client.datasets.get_dataset.called


@pytest.mark.asyncio
async def test_load_dataset_examples_prefers_local_regression_examples():
    """Same root cause as the experiment-id bug: Phoenix slugifies dataset
    names with ``::``, so ``mcp_client.get_dataset("regression-{failure_key}")``
    silently returns nothing for a trigger like
    ``citation_presence::demo-synthetic-cluster``. Before the fix, the
    experiment fell through to recent generic tickets — i.e. it stopped
    actually testing the failure mode. After the fix, the experiment
    loads its synthesized regression tickets from the local DB directly.
    """
    import aiosqlite
    from src.db import (
        _CREATE_TABLES_SQL,
        insert_improvement_trigger,
        insert_regression_example,
    )
    from src.experiments.orchestrator import _load_dataset_examples
    from src.models import (
        ImprovementTrigger,
        RegressionExample,
        TriggerReason,
    )

    conn = await aiosqlite.connect(":memory:")
    try:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys = ON")
        await conn.executescript(_CREATE_TABLES_SQL)
        await conn.commit()

        trigger = ImprovementTrigger(
            improvement_trigger_id="IT-load-1",
            failure_key="citation_presence::demo-synthetic-cluster",
            trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
            occurrence_count=3,
            created_at="2026-06-07T00:00:00Z",
            updated_at="2026-06-07T00:00:00Z",
        )
        await insert_improvement_trigger(conn, trigger)

        for i in range(3):
            ex = RegressionExample(
                regression_example_id=f"REX-{i}",
                improvement_trigger_id="IT-load-1",
                input_ticket_json={
                    "body": f"synthetic ticket body {i}",
                    "category": "refund",
                },
                expected_behavior=f"behavior {i}",
                failure_mode_targeted="citation_presence",
                phoenix_dataset_id="RGF0YXNldDo4",
                created_at="2026-06-07T00:00:00Z",
            )
            await insert_regression_example(conn, ex)

        mcp = MagicMock()
        mcp.get_dataset = AsyncMock(return_value=[])

        tickets = await _load_dataset_examples(trigger, mcp, conn)

        assert len(tickets) == 3, f"expected 3 regression tickets, got {len(tickets)}"
        assert {t.body for t in tickets} == {
            "synthetic ticket body 0",
            "synthetic ticket body 1",
            "synthetic ticket body 2",
        }
        for t in tickets:
            assert t.category == TicketCategory.REFUND
    finally:
        await conn.close()
