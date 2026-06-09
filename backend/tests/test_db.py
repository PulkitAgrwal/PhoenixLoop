"""Tests for the async SQLite database layer."""

import aiosqlite
import pytest
from src.db import (
    get_active_failure_aggregates,
    get_agent_run,
    get_agent_runs_for_session,
    get_conversation_session,
    get_eval_results_for_run,
    get_experiment,
    get_failure_aggregate,
    get_human_approval_for_decision,
    get_improvement_trigger,
    get_regression_examples_for_trigger,
    get_release_gate_decision,
    get_release_gate_for_experiment,
    get_ticket,
    init_db,
    insert_agent_run,
    insert_audit_event,
    insert_conversation_session,
    insert_eval_result,
    insert_experiment,
    insert_human_approval,
    insert_improvement_trigger,
    insert_regression_example,
    insert_release_gate_decision,
    insert_ticket,
    list_audit_events,
    list_conversation_sessions,
    list_experiments,
    list_improvement_triggers,
    list_tickets,
    update_experiment,
    update_human_approval,
    update_improvement_trigger,
    upsert_failure_aggregate,
)
from src.models import (
    AgentRun,
    AnnotationLevel,
    AuditEvent,
    ConversationSession,
    EvalResult,
    EvalType,
    ExperimentRecord,
    ExperimentStatus,
    FailureAggregate,
    HumanApproval,
    ImprovementTrigger,
    RegressionExample,
    ReleaseDecision,
    ReleaseGateDecision,
    SupportTicket,
    TicketCategory,
    ToolCallRecord,
    TriggerReason,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    """Provide an in-memory SQLite connection with schema initialized."""
    await init_db(":memory:")
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    # Re-create tables on this specific connection (in-memory DBs are per-connection).
    # Apply column migrations the same way init_db() does so the schema matches
    # production after Wave 1 additive migrations.
    from src.db import _CREATE_TABLES_SQL, _apply_column_migrations
    await conn.executescript(_CREATE_TABLES_SQL)
    await conn.commit()
    await _apply_column_migrations(conn)
    yield conn
    await conn.close()


def _make_ticket(ticket_id: str = "T-001", category: str = "refund") -> SupportTicket:
    return SupportTicket(
        ticket_id=ticket_id,
        customer_id="C-100",
        category=TicketCategory(category),
        subject="Test subject",
        body="Test body",
        metadata_json={"priority": "high"},
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


def _make_session(
    session_id: str = "CS-001", ticket_id: str = "T-001"
) -> ConversationSession:
    return ConversationSession(
        conversation_session_id=session_id,
        ticket_id=ticket_id,
        started_at="2025-01-01T00:00:00Z",
    )


def _make_agent_run(
    run_id: str = "AR-001",
    session_id: str = "CS-001",
    ticket_id: str = "T-001",
) -> AgentRun:
    return AgentRun(
        agent_run_id=run_id,
        conversation_session_id=session_id,
        ticket_id=ticket_id,
        prompt_version="v1.0",
        response_json={"message": "Refund processed."},
        tool_calls_json=[
            ToolCallRecord(
                tool_name="lookup_order",
                input={"order_id": "ORD-001"},
                output={"status": "shipped"},
                latency_ms=50,
            )
        ],
        status="completed",
        latency_ms=200,
        token_count_input=100,
        token_count_output=50,
        created_at="2025-01-01T00:00:00Z",
    )


def _make_improvement_trigger(
    trigger_id: str = "IT-001",
) -> ImprovementTrigger:
    return ImprovementTrigger(
        improvement_trigger_id=trigger_id,
        failure_key="missing_required_tool::lookup_order",
        trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
        occurrence_count=3,
        example_run_ids_json=["AR-001", "AR-002"],
        diagnosis_json={"root_cause": "Prompt lacks tool instruction"},
        created_at="2025-01-01T00:00:00Z",
        updated_at="2025-01-01T00:00:00Z",
    )


async def _seed_ticket_session_run(db: aiosqlite.Connection) -> None:
    """Insert a ticket, session, and agent run as prerequisite data."""
    await insert_ticket(db, _make_ticket())
    await insert_conversation_session(db, _make_session())
    await insert_agent_run(db, _make_agent_run())


async def _seed_improvement_trigger(db: aiosqlite.Connection) -> None:
    """Insert an improvement trigger as prerequisite data."""
    await insert_improvement_trigger(db, _make_improvement_trigger())


# ---------------------------------------------------------------------------
# Schema initialization
# ---------------------------------------------------------------------------

class TestInitDb:
    @pytest.mark.asyncio
    async def test_creates_all_tables(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        table_names = sorted(r["name"] for r in rows)
        expected = sorted([
            "agent_runs",
            "audit_events",
            "canary_labels",
            "canary_runs",
            "conversation_sessions",
            "eval_results",
            "experiments",
            "failure_aggregates",
            "human_approvals",
            "improvement_triggers",
            "prompts",
            "prompt_versions",
            "regression_examples",
            "release_gate_decisions",
            "support_tickets",
        ])
        assert table_names == expected


# ---------------------------------------------------------------------------
# Support Tickets
# ---------------------------------------------------------------------------

class TestTicketCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        ticket = _make_ticket()
        await insert_ticket(db, ticket)
        result = await get_ticket(db, "T-001")
        assert result is not None
        assert result.ticket_id == "T-001"
        assert result.category == TicketCategory.REFUND
        assert result.metadata_json == {"priority": "high"}

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await get_ticket(db, "NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, db):
        for i in range(5):
            await insert_ticket(db, _make_ticket(f"T-{i:03d}"))

        items, total = await list_tickets(db, category=None, page=1, page_size=2)
        assert total == 5
        assert len(items) == 2

        items2, _ = await list_tickets(db, category=None, page=2, page_size=2)
        assert len(items2) == 2

        items3, _ = await list_tickets(db, category=None, page=3, page_size=2)
        assert len(items3) == 1

    @pytest.mark.asyncio
    async def test_list_with_category_filter(self, db):
        await insert_ticket(db, _make_ticket("T-001", "refund"))
        await insert_ticket(db, _make_ticket("T-002", "billing"))
        await insert_ticket(db, _make_ticket("T-003", "refund"))

        items, total = await list_tickets(db, category="refund", page=1, page_size=10)
        assert total == 2
        assert all(t.category == TicketCategory.REFUND for t in items)


# ---------------------------------------------------------------------------
# Conversation Sessions
# ---------------------------------------------------------------------------

class TestConversationSessionCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        await insert_ticket(db, _make_ticket())
        session = _make_session()
        await insert_conversation_session(db, session)
        result = await get_conversation_session(db, "CS-001")
        assert result is not None
        assert result.ticket_id == "T-001"
        assert result.turn_count == 0

    @pytest.mark.asyncio
    async def test_list_with_pagination(self, db):
        await insert_ticket(db, _make_ticket())
        for i in range(3):
            await insert_conversation_session(db, _make_session(f"CS-{i:03d}"))

        items, total = await list_conversation_sessions(db, page=1, page_size=2)
        assert total == 3
        assert len(items) == 2


# ---------------------------------------------------------------------------
# Agent Runs
# ---------------------------------------------------------------------------

class TestAgentRunCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        await _seed_ticket_session_run(db)
        result = await get_agent_run(db, "AR-001")
        assert result is not None
        assert result.agent_run_id == "AR-001"
        assert result.response_json == {"message": "Refund processed."}
        assert len(result.tool_calls_json) == 1
        assert result.tool_calls_json[0].tool_name == "lookup_order"
        assert result.latency_ms == 200

    @pytest.mark.asyncio
    async def test_get_runs_for_session(self, db):
        await insert_ticket(db, _make_ticket())
        await insert_conversation_session(db, _make_session())
        await insert_agent_run(db, _make_agent_run("AR-001"))
        await insert_agent_run(db, _make_agent_run("AR-002"))

        runs = await get_agent_runs_for_session(db, "CS-001")
        assert len(runs) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await get_agent_run(db, "NONEXISTENT")
        assert result is None


# ---------------------------------------------------------------------------
# Eval Results
# ---------------------------------------------------------------------------

class TestEvalResultCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get_for_run(self, db):
        await _seed_ticket_session_run(db)

        eval_result = EvalResult(
            eval_result_id="ER-001",
            agent_run_id="AR-001",
            evaluator_name="tool_coverage",
            eval_type=EvalType.CODE,
            score=0.85,
            outcome="pass",
            annotation_level=AnnotationLevel.SESSION,
            metadata_json={"detail": "ok"},
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_eval_result(db, eval_result)

        results = await get_eval_results_for_run(db, "AR-001")
        assert len(results) == 1
        assert results[0].evaluator_name == "tool_coverage"
        assert results[0].score == 0.85
        assert results[0].metadata_json == {"detail": "ok"}

    @pytest.mark.asyncio
    async def test_with_failure_fields(self, db):
        await _seed_ticket_session_run(db)

        eval_result = EvalResult(
            eval_result_id="ER-002",
            agent_run_id="AR-001",
            evaluator_name="tool_coverage",
            eval_type=EvalType.CODE,
            outcome="fail",
            failure_key="missing_required_tool::lookup_order",
            failure_summary="Agent did not call lookup_order",
            annotation_level=AnnotationLevel.SESSION,
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_eval_result(db, eval_result)

        results = await get_eval_results_for_run(db, "AR-001")
        assert results[0].failure_key == "missing_required_tool::lookup_order"


# ---------------------------------------------------------------------------
# Failure Aggregates
# ---------------------------------------------------------------------------

class TestFailureAggregateCrud:
    @pytest.mark.asyncio
    async def test_upsert_and_get(self, db):
        agg = FailureAggregate(
            failure_key="missing_required_tool::lookup_order",
            failure_summary="Agent never calls lookup_order",
            evaluator_name="tool_coverage",
            occurrence_count=3,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-02T00:00:00Z",
            example_run_ids_json=["AR-001"],
            computed_at="2025-01-02T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg)

        result = await get_failure_aggregate(db, "missing_required_tool::lookup_order")
        assert result is not None
        assert result.occurrence_count == 3
        assert result.example_run_ids_json == ["AR-001"]
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_upsert_replaces(self, db):
        agg1 = FailureAggregate(
            failure_key="test_key",
            failure_summary="First summary",
            evaluator_name="eval1",
            occurrence_count=1,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-01T00:00:00Z",
            computed_at="2025-01-01T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg1)

        agg2 = FailureAggregate(
            failure_key="test_key",
            failure_summary="Updated summary",
            evaluator_name="eval1",
            occurrence_count=5,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-03T00:00:00Z",
            example_run_ids_json=["AR-001", "AR-002"],
            computed_at="2025-01-03T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg2)

        result = await get_failure_aggregate(db, "test_key")
        assert result is not None
        assert result.occurrence_count == 5
        assert result.failure_summary == "Updated summary"
        assert len(result.example_run_ids_json) == 2

    @pytest.mark.asyncio
    async def test_get_active_only(self, db):
        active = FailureAggregate(
            failure_key="active_key",
            failure_summary="Active failure",
            evaluator_name="eval1",
            occurrence_count=2,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-01T00:00:00Z",
            is_active=True,
            computed_at="2025-01-01T00:00:00Z",
        )
        inactive = FailureAggregate(
            failure_key="inactive_key",
            failure_summary="Inactive failure",
            evaluator_name="eval1",
            occurrence_count=1,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-01T00:00:00Z",
            is_active=False,
            computed_at="2025-01-01T00:00:00Z",
        )
        await upsert_failure_aggregate(db, active)
        await upsert_failure_aggregate(db, inactive)

        results = await get_active_failure_aggregates(db)
        assert len(results) == 1
        assert results[0].failure_key == "active_key"


# ---------------------------------------------------------------------------
# Improvement Triggers
# ---------------------------------------------------------------------------

class TestImprovementTriggerCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        trigger = _make_improvement_trigger()
        await insert_improvement_trigger(db, trigger)

        result = await get_improvement_trigger(db, "IT-001")
        assert result is not None
        assert result.failure_key == "missing_required_tool::lookup_order"
        assert result.trigger_reason == TriggerReason.THRESHOLD_REPEATED_FAILURE
        assert result.example_run_ids_json == ["AR-001", "AR-002"]
        assert result.diagnosis_json == {"root_cause": "Prompt lacks tool instruction"}
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_update(self, db):
        trigger = _make_improvement_trigger()
        await insert_improvement_trigger(db, trigger)

        trigger.status = "completed"
        trigger.updated_at = "2025-01-02T00:00:00Z"
        trigger.patch_proposal_json = {"action": "add_tool_instruction"}
        await update_improvement_trigger(db, trigger)

        result = await get_improvement_trigger(db, "IT-001")
        assert result is not None
        assert result.status == "completed"
        assert result.patch_proposal_json == {"action": "add_tool_instruction"}

    @pytest.mark.asyncio
    async def test_list_with_status_filter(self, db):
        t1 = _make_improvement_trigger("IT-001")
        t2 = _make_improvement_trigger("IT-002")
        t2.status = "completed"
        await insert_improvement_trigger(db, t1)
        await insert_improvement_trigger(db, t2)

        items, total = await list_improvement_triggers(db, status="pending", page=1, page_size=10)
        assert total == 1
        assert items[0].improvement_trigger_id == "IT-001"

        items_all, total_all = await list_improvement_triggers(db, status=None, page=1, page_size=10)
        assert total_all == 2

    @pytest.mark.asyncio
    async def test_list_pagination(self, db):
        for i in range(5):
            await insert_improvement_trigger(db, _make_improvement_trigger(f"IT-{i:03d}"))

        items, total = await list_improvement_triggers(db, status=None, page=1, page_size=2)
        assert total == 5
        assert len(items) == 2


# ---------------------------------------------------------------------------
# Regression Examples
# ---------------------------------------------------------------------------

class TestRegressionExampleCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get_for_trigger(self, db):
        await _seed_improvement_trigger(db)

        example = RegressionExample(
            regression_example_id="RE-001",
            improvement_trigger_id="IT-001",
            input_ticket_json={"subject": "Refund", "body": "I want a refund"},
            expected_behavior="Agent should call lookup_order",
            failure_mode_targeted="missing_required_tool",
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_regression_example(db, example)

        results = await get_regression_examples_for_trigger(db, "IT-001")
        assert len(results) == 1
        assert results[0].input_ticket_json == {"subject": "Refund", "body": "I want a refund"}
        assert results[0].expected_behavior == "Agent should call lookup_order"


# ---------------------------------------------------------------------------
# Experiments
# ---------------------------------------------------------------------------

class TestExperimentCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        await _seed_improvement_trigger(db)

        exp = ExperimentRecord(
            experiment_id="EXP-001",
            improvement_trigger_id="IT-001",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_experiment(db, exp)

        result = await get_experiment(db, "EXP-001")
        assert result is not None
        assert result.status == ExperimentStatus.PENDING
        assert result.baseline_prompt_version == "v1.0"

    @pytest.mark.asyncio
    async def test_update(self, db):
        await _seed_improvement_trigger(db)

        exp = ExperimentRecord(
            experiment_id="EXP-001",
            improvement_trigger_id="IT-001",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_experiment(db, exp)

        exp.status = ExperimentStatus.COMPLETED
        exp.baseline_release_score = 0.70
        exp.candidate_release_score = 0.85
        exp.eval_summary_json = {"winner": "candidate"}
        exp.completed_at = "2025-01-02T00:00:00Z"
        await update_experiment(db, exp)

        result = await get_experiment(db, "EXP-001")
        assert result is not None
        assert result.status == ExperimentStatus.COMPLETED
        assert result.candidate_release_score == 0.85
        assert result.eval_summary_json == {"winner": "candidate"}

    @pytest.mark.asyncio
    async def test_list_pagination(self, db):
        await _seed_improvement_trigger(db)

        for i in range(4):
            await insert_experiment(
                db,
                ExperimentRecord(
                    experiment_id=f"EXP-{i:03d}",
                    improvement_trigger_id="IT-001",
                    baseline_prompt_version="v1.0",
                    candidate_prompt_version="v1.1",
                    dataset_id="DS-001",
                    created_at=f"2025-01-0{i + 1}T00:00:00Z",
                ),
            )

        items, total = await list_experiments(db, page=1, page_size=2)
        assert total == 4
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, db):
        result = await get_experiment(db, "NONEXISTENT")
        assert result is None


# ---------------------------------------------------------------------------
# Release Gate Decisions
# ---------------------------------------------------------------------------

class TestReleaseGateDecisionCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        await _seed_improvement_trigger(db)
        exp = ExperimentRecord(
            experiment_id="EXP-001",
            improvement_trigger_id="IT-001",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_experiment(db, exp)

        decision = ReleaseGateDecision(
            release_gate_decision_id="RGD-001",
            experiment_id="EXP-001",
            decision=ReleaseDecision.PROMOTED,
            release_score=0.85,
            promotion_rules_passed=5,
            rules_detail_json={"rule_1": True, "rule_2": True},
            requires_human_approval=False,
            decided_at="2025-01-02T00:00:00Z",
        )
        await insert_release_gate_decision(db, decision)

        result = await get_release_gate_decision(db, "RGD-001")
        assert result is not None
        assert result.decision == ReleaseDecision.PROMOTED
        assert result.release_score == 0.85
        assert result.requires_human_approval is False
        assert result.rules_detail_json == {"rule_1": True, "rule_2": True}

    @pytest.mark.asyncio
    async def test_get_for_experiment(self, db):
        await _seed_improvement_trigger(db)
        exp = ExperimentRecord(
            experiment_id="EXP-001",
            improvement_trigger_id="IT-001",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_experiment(db, exp)

        decision = ReleaseGateDecision(
            release_gate_decision_id="RGD-001",
            experiment_id="EXP-001",
            decision=ReleaseDecision.PENDING_HUMAN_REVIEW,
            release_score=0.80,
            promotion_rules_passed=4,
            decided_at="2025-01-02T00:00:00Z",
        )
        await insert_release_gate_decision(db, decision)

        result = await get_release_gate_for_experiment(db, "EXP-001")
        assert result is not None
        assert result.experiment_id == "EXP-001"


# ---------------------------------------------------------------------------
# Human Approvals
# ---------------------------------------------------------------------------

class TestHumanApprovalCrud:
    @pytest.mark.asyncio
    async def test_insert_and_get(self, db):
        # Set up prerequisite chain: trigger -> experiment -> decision
        await _seed_improvement_trigger(db)
        await insert_experiment(
            db,
            ExperimentRecord(
                experiment_id="EXP-001",
                improvement_trigger_id="IT-001",
                baseline_prompt_version="v1.0",
                candidate_prompt_version="v1.1",
                dataset_id="DS-001",
                created_at="2025-01-01T00:00:00Z",
            ),
        )
        await insert_release_gate_decision(
            db,
            ReleaseGateDecision(
                release_gate_decision_id="RGD-001",
                experiment_id="EXP-001",
                decision=ReleaseDecision.PENDING_HUMAN_REVIEW,
                release_score=0.80,
                promotion_rules_passed=4,
                decided_at="2025-01-02T00:00:00Z",
            ),
        )

        approval = HumanApproval(
            human_approval_id="HA-001",
            release_gate_decision_id="RGD-001",
            reviewer_id="reviewer-1",
            created_at="2025-01-02T00:00:00Z",
        )
        await insert_human_approval(db, approval)

        result = await get_human_approval_for_decision(db, "RGD-001")
        assert result is not None
        assert result.status == "pending"

    @pytest.mark.asyncio
    async def test_update(self, db):
        await _seed_improvement_trigger(db)
        await insert_experiment(
            db,
            ExperimentRecord(
                experiment_id="EXP-001",
                improvement_trigger_id="IT-001",
                baseline_prompt_version="v1.0",
                candidate_prompt_version="v1.1",
                dataset_id="DS-001",
                created_at="2025-01-01T00:00:00Z",
            ),
        )
        await insert_release_gate_decision(
            db,
            ReleaseGateDecision(
                release_gate_decision_id="RGD-001",
                experiment_id="EXP-001",
                decision=ReleaseDecision.PENDING_HUMAN_REVIEW,
                release_score=0.80,
                promotion_rules_passed=4,
                decided_at="2025-01-02T00:00:00Z",
            ),
        )

        approval = HumanApproval(
            human_approval_id="HA-001",
            release_gate_decision_id="RGD-001",
            reviewer_id="reviewer-1",
            created_at="2025-01-02T00:00:00Z",
        )
        await insert_human_approval(db, approval)

        approval.status = "approved"
        approval.comment = "Looks good"
        approval.reviewed_at = "2025-01-03T00:00:00Z"
        await update_human_approval(db, approval)

        result = await get_human_approval_for_decision(db, "RGD-001")
        assert result is not None
        assert result.status == "approved"
        assert result.comment == "Looks good"


# ---------------------------------------------------------------------------
# Audit Events
# ---------------------------------------------------------------------------

class TestAuditEventCrud:
    @pytest.mark.asyncio
    async def test_insert_and_list(self, db):
        event = AuditEvent(
            audit_event_id="AE-001",
            entity_type="experiment",
            entity_id="EXP-001",
            action="created",
            actor="system",
            detail_json={"note": "auto-triggered"},
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_audit_event(db, event)

        items, total = await list_audit_events(db, entity_type=None, page=1, page_size=10)
        assert total == 1
        assert items[0].entity_type == "experiment"
        assert items[0].detail_json == {"note": "auto-triggered"}

    @pytest.mark.asyncio
    async def test_list_with_entity_type_filter(self, db):
        e1 = AuditEvent(
            audit_event_id="AE-001",
            entity_type="experiment",
            entity_id="EXP-001",
            action="created",
            actor="system",
            created_at="2025-01-01T00:00:00Z",
        )
        e2 = AuditEvent(
            audit_event_id="AE-002",
            entity_type="ticket",
            entity_id="T-001",
            action="created",
            actor="user",
            created_at="2025-01-01T00:00:00Z",
        )
        await insert_audit_event(db, e1)
        await insert_audit_event(db, e2)

        items, total = await list_audit_events(db, entity_type="experiment", page=1, page_size=10)
        assert total == 1
        assert items[0].audit_event_id == "AE-001"

    @pytest.mark.asyncio
    async def test_list_pagination(self, db):
        for i in range(5):
            await insert_audit_event(
                db,
                AuditEvent(
                    audit_event_id=f"AE-{i:03d}",
                    entity_type="experiment",
                    entity_id=f"EXP-{i:03d}",
                    action="created",
                    actor="system",
                    created_at=f"2025-01-0{i + 1}T00:00:00Z",
                ),
            )

        items, total = await list_audit_events(db, entity_type=None, page=1, page_size=2)
        assert total == 5
        assert len(items) == 2


# ---------------------------------------------------------------------------
# Foreign Key Enforcement
# ---------------------------------------------------------------------------

class TestForeignKeys:
    @pytest.mark.asyncio
    async def test_session_requires_ticket(self, db):
        """Inserting a session with a nonexistent ticket_id should fail."""
        session = ConversationSession(
            conversation_session_id="CS-ORPHAN",
            ticket_id="NONEXISTENT",
            started_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(Exception):
            await insert_conversation_session(db, session)

    @pytest.mark.asyncio
    async def test_agent_run_requires_session(self, db):
        """Inserting an agent run with a nonexistent session_id should fail."""
        await insert_ticket(db, _make_ticket())
        run = _make_agent_run(session_id="NONEXISTENT")
        with pytest.raises(Exception):
            await insert_agent_run(db, run)

    @pytest.mark.asyncio
    async def test_eval_result_requires_agent_run(self, db):
        """Inserting an eval result with a nonexistent agent_run_id should fail."""
        eval_result = EvalResult(
            eval_result_id="ER-ORPHAN",
            agent_run_id="NONEXISTENT",
            evaluator_name="test",
            eval_type=EvalType.CODE,
            outcome="pass",
            annotation_level=AnnotationLevel.SESSION,
            created_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(Exception):
            await insert_eval_result(db, eval_result)

    @pytest.mark.asyncio
    async def test_regression_example_requires_trigger(self, db):
        """Inserting a regression example with a nonexistent trigger_id should fail."""
        example = RegressionExample(
            regression_example_id="RE-ORPHAN",
            improvement_trigger_id="NONEXISTENT",
            input_ticket_json={"subject": "Test"},
            expected_behavior="Test behavior",
            failure_mode_targeted="test_failure",
            created_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(Exception):
            await insert_regression_example(db, example)

    @pytest.mark.asyncio
    async def test_experiment_requires_trigger(self, db):
        """Inserting an experiment with a nonexistent trigger_id should fail."""
        exp = ExperimentRecord(
            experiment_id="EXP-ORPHAN",
            improvement_trigger_id="NONEXISTENT",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            created_at="2025-01-01T00:00:00Z",
        )
        with pytest.raises(Exception):
            await insert_experiment(db, exp)

    @pytest.mark.asyncio
    async def test_release_gate_requires_experiment(self, db):
        """Inserting a release gate decision with a nonexistent experiment_id should fail."""
        decision = ReleaseGateDecision(
            release_gate_decision_id="RGD-ORPHAN",
            experiment_id="NONEXISTENT",
            decision=ReleaseDecision.PROMOTED,
            release_score=0.85,
            promotion_rules_passed=5,
            decided_at="2025-01-02T00:00:00Z",
        )
        with pytest.raises(Exception):
            await insert_release_gate_decision(db, decision)

    @pytest.mark.asyncio
    async def test_human_approval_requires_decision(self, db):
        """Inserting a human approval with a nonexistent decision_id should fail."""
        approval = HumanApproval(
            human_approval_id="HA-ORPHAN",
            release_gate_decision_id="NONEXISTENT",
            reviewer_id="reviewer-1",
            created_at="2025-01-02T00:00:00Z",
        )
        with pytest.raises(Exception):
            await insert_human_approval(db, approval)
