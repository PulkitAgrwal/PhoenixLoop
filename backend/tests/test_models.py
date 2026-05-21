"""Tests for Pydantic models and enums."""

import pytest
from pydantic import ValidationError

from src.models import (
    AgentRun,
    AnnotationLevel,
    ApiResponse,
    AuditEvent,
    ConversationSession,
    EvalResult,
    EvalType,
    ExperimentRecord,
    ExperimentStatus,
    FailureAggregate,
    FailureType,
    HumanApproval,
    ImprovementTrigger,
    PaginatedData,
    PatchType,
    RegressionExample,
    ReleaseDecision,
    ReleaseGateDecision,
    Severity,
    SupportTicket,
    TicketCategory,
    ToolCallRecord,
    TriggerReason,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------

class TestEnums:
    def test_ticket_category_values(self):
        assert TicketCategory.REFUND == "refund"
        assert TicketCategory.BILLING == "billing"
        assert TicketCategory.ADMIN_ACCESS == "admin_access"
        assert TicketCategory.DATA_EXPORT == "data_export"
        assert TicketCategory.PRIVACY == "privacy"
        assert TicketCategory.LEGAL == "legal"
        assert TicketCategory.OUTAGE_CREDIT == "outage_credit"
        assert TicketCategory.AMBIGUOUS == "ambiguous"
        assert len(TicketCategory) == 8

    def test_severity_values(self):
        assert Severity.INFO == "info"
        assert Severity.LOW == "low"
        assert Severity.MEDIUM == "medium"
        assert Severity.HIGH == "high"
        assert Severity.CRITICAL == "critical"
        assert len(Severity) == 5

    def test_failure_type_values(self):
        assert FailureType.MISSING_REQUIRED_TOOL == "missing_required_tool"
        assert FailureType.PRIVACY_LEAK == "privacy_leak"
        assert FailureType.TOKEN_BUDGET_EXCEEDED == "token_budget_exceeded"
        assert FailureType.TOOL_ERROR == "tool_error"
        assert len(FailureType) == 10

    def test_patch_type_values(self):
        assert PatchType.TOOL_POLICY_RULE == "tool_policy_rule"
        assert PatchType.ESCALATION_RULE == "escalation_rule"
        assert PatchType.PROMPT_CONSTRAINT == "prompt_constraint"
        assert PatchType.RETRIEVAL_ROUTING == "retrieval_routing"
        assert len(PatchType) == 4

    def test_trigger_reason_values(self):
        assert TriggerReason.THRESHOLD_REPEATED_FAILURE == "threshold_repeated_failure"
        assert TriggerReason.CRITICAL_FAILURE == "critical_failure"
        assert TriggerReason.MANUAL_DEMO_TRIGGER == "manual_demo_trigger"
        assert len(TriggerReason) == 3

    def test_release_decision_values(self):
        assert ReleaseDecision.PROMOTED == "promoted"
        assert ReleaseDecision.REJECTED == "rejected"
        assert ReleaseDecision.PENDING_HUMAN_REVIEW == "pending_human_review"
        assert ReleaseDecision.BLOCKED_CRITICAL_FAILURE == "blocked_critical_failure"
        assert len(ReleaseDecision) == 4

    def test_experiment_status_values(self):
        assert ExperimentStatus.PENDING == "pending"
        assert ExperimentStatus.RUNNING == "running"
        assert ExperimentStatus.COMPLETED == "completed"
        assert ExperimentStatus.FAILED == "failed"
        assert len(ExperimentStatus) == 4

    def test_eval_type_values(self):
        assert EvalType.CODE == "code"
        assert EvalType.LLM_JUDGE == "llm_judge"
        assert EvalType.PHOENIX_TOOL_EVAL == "phoenix_tool_eval"
        assert len(EvalType) == 3

    def test_annotation_level_values(self):
        assert AnnotationLevel.SESSION == "session"
        assert AnnotationLevel.SPAN == "span"
        assert len(AnnotationLevel) == 2

    def test_enums_are_str_subclass(self):
        """All enums should be str subclasses for JSON serialization."""
        assert isinstance(TicketCategory.REFUND, str)
        assert isinstance(Severity.HIGH, str)
        assert isinstance(FailureType.PRIVACY_LEAK, str)
        assert isinstance(ExperimentStatus.RUNNING, str)


# ---------------------------------------------------------------------------
# Pydantic model creation tests
# ---------------------------------------------------------------------------

class TestSupportTicket:
    def test_valid_creation(self):
        ticket = SupportTicket(
            ticket_id="T-001",
            customer_id="C-100",
            category=TicketCategory.REFUND,
            subject="Refund request",
            body="I want a refund for order #123",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        assert ticket.ticket_id == "T-001"
        assert ticket.category == TicketCategory.REFUND
        assert ticket.metadata_json is None

    def test_with_metadata(self):
        ticket = SupportTicket(
            ticket_id="T-002",
            customer_id="C-200",
            category=TicketCategory.BILLING,
            subject="Billing issue",
            body="Overcharged",
            metadata_json={"priority": "high"},
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        assert ticket.metadata_json == {"priority": "high"}

    def test_category_from_string(self):
        """Category should accept raw string matching enum value."""
        ticket = SupportTicket(
            ticket_id="T-003",
            customer_id="C-300",
            category="refund",
            subject="Test",
            body="Test body",
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        assert ticket.category == TicketCategory.REFUND

    def test_missing_required_field(self):
        with pytest.raises(ValidationError):
            SupportTicket(
                ticket_id="T-004",
                customer_id="C-400",
                category=TicketCategory.REFUND,
                # subject missing
                body="Test body",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            SupportTicket(
                ticket_id="T-005",
                customer_id="C-500",
                category="nonexistent_category",
                subject="Test",
                body="Test body",
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )


class TestToolCallRecord:
    def test_valid_creation(self):
        record = ToolCallRecord(
            tool_name="lookup_order",
            input={"order_id": "ORD-001"},
            output={"status": "shipped"},
        )
        assert record.tool_name == "lookup_order"
        assert record.status == "success"
        assert record.span_id is None
        assert record.latency_ms is None

    def test_with_optional_fields(self):
        record = ToolCallRecord(
            tool_name="lookup_order",
            input={"order_id": "ORD-001"},
            output={"status": "shipped"},
            span_id="span-123",
            latency_ms=42,
            status="error",
        )
        assert record.span_id == "span-123"
        assert record.latency_ms == 42
        assert record.status == "error"


class TestConversationSession:
    def test_valid_creation(self):
        session = ConversationSession(
            conversation_session_id="CS-001",
            ticket_id="T-001",
            started_at="2025-01-01T00:00:00Z",
        )
        assert session.turn_count == 0
        assert session.ended_at is None
        assert session.outcome is None


class TestAgentRun:
    def test_valid_creation(self):
        run = AgentRun(
            agent_run_id="AR-001",
            conversation_session_id="CS-001",
            ticket_id="T-001",
            prompt_version="v1.0",
            response_json={"message": "Your refund is processed."},
            status="completed",
            created_at="2025-01-01T00:00:00Z",
        )
        assert run.agent_name == "acmeflow_support_agent"
        assert run.agent_version == "1.0.0"
        assert run.tool_calls_json == []
        assert run.trace_id is None

    def test_with_tool_calls(self):
        tc = ToolCallRecord(
            tool_name="lookup_order",
            input={"order_id": "ORD-001"},
            output={"status": "shipped"},
        )
        run = AgentRun(
            agent_run_id="AR-002",
            conversation_session_id="CS-001",
            ticket_id="T-001",
            prompt_version="v1.0",
            response_json={"message": "Done"},
            tool_calls_json=[tc],
            status="completed",
            created_at="2025-01-01T00:00:00Z",
        )
        assert len(run.tool_calls_json) == 1
        assert run.tool_calls_json[0].tool_name == "lookup_order"

    def test_missing_response_json(self):
        with pytest.raises(ValidationError):
            AgentRun(
                agent_run_id="AR-003",
                conversation_session_id="CS-001",
                ticket_id="T-001",
                prompt_version="v1.0",
                # response_json missing
                status="completed",
                created_at="2025-01-01T00:00:00Z",
            )


class TestEvalResult:
    def test_valid_creation(self):
        result = EvalResult(
            eval_result_id="ER-001",
            agent_run_id="AR-001",
            evaluator_name="tool_coverage",
            eval_type=EvalType.CODE,
            score=0.95,
            outcome="pass",
            annotation_level=AnnotationLevel.SESSION,
            created_at="2025-01-01T00:00:00Z",
        )
        assert result.score == 0.95
        assert result.failure_key is None

    def test_with_failure(self):
        result = EvalResult(
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
        assert result.failure_key is not None

    def test_invalid_eval_type(self):
        with pytest.raises(ValidationError):
            EvalResult(
                eval_result_id="ER-003",
                agent_run_id="AR-001",
                evaluator_name="test",
                eval_type="invalid_type",
                outcome="pass",
                annotation_level=AnnotationLevel.SESSION,
                created_at="2025-01-01T00:00:00Z",
            )


class TestFailureAggregate:
    def test_valid_creation(self):
        agg = FailureAggregate(
            failure_key="missing_required_tool::lookup_order",
            failure_summary="Agent never calls lookup_order",
            evaluator_name="tool_coverage",
            occurrence_count=5,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-02T00:00:00Z",
            example_run_ids_json=["AR-001", "AR-002"],
            computed_at="2025-01-02T00:00:00Z",
        )
        assert agg.is_active is True
        assert len(agg.example_run_ids_json) == 2

    def test_defaults(self):
        agg = FailureAggregate(
            failure_key="test",
            failure_summary="test summary",
            evaluator_name="test_eval",
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-01T00:00:00Z",
            computed_at="2025-01-01T00:00:00Z",
        )
        assert agg.occurrence_count == 0
        assert agg.example_run_ids_json == []
        assert agg.is_active is True


class TestImprovementTrigger:
    def test_valid_creation(self):
        trigger = ImprovementTrigger(
            improvement_trigger_id="IT-001",
            failure_key="missing_required_tool::lookup_order",
            trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
            occurrence_count=3,
            created_at="2025-01-01T00:00:00Z",
            updated_at="2025-01-01T00:00:00Z",
        )
        assert trigger.status == "pending"
        assert trigger.diagnosis_json is None

    def test_invalid_trigger_reason(self):
        with pytest.raises(ValidationError):
            ImprovementTrigger(
                improvement_trigger_id="IT-002",
                failure_key="test",
                trigger_reason="not_a_reason",
                occurrence_count=1,
                created_at="2025-01-01T00:00:00Z",
                updated_at="2025-01-01T00:00:00Z",
            )


class TestRegressionExample:
    def test_valid_creation(self):
        example = RegressionExample(
            regression_example_id="RE-001",
            improvement_trigger_id="IT-001",
            input_ticket_json={"subject": "Refund request", "body": "I want a refund"},
            expected_behavior="Agent should call lookup_order then process_refund",
            failure_mode_targeted="missing_required_tool",
            created_at="2025-01-01T00:00:00Z",
        )
        assert example.phoenix_dataset_id is None
        assert example.uploaded_at is None


class TestExperimentRecord:
    def test_valid_creation(self):
        exp = ExperimentRecord(
            experiment_id="EXP-001",
            improvement_trigger_id="IT-001",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            created_at="2025-01-01T00:00:00Z",
        )
        assert exp.status == ExperimentStatus.PENDING
        assert exp.baseline_release_score is None

    def test_status_from_string(self):
        exp = ExperimentRecord(
            experiment_id="EXP-002",
            improvement_trigger_id="IT-001",
            baseline_prompt_version="v1.0",
            candidate_prompt_version="v1.1",
            dataset_id="DS-001",
            status="running",
            created_at="2025-01-01T00:00:00Z",
        )
        assert exp.status == ExperimentStatus.RUNNING

    def test_invalid_status(self):
        with pytest.raises(ValidationError):
            ExperimentRecord(
                experiment_id="EXP-003",
                improvement_trigger_id="IT-001",
                baseline_prompt_version="v1.0",
                candidate_prompt_version="v1.1",
                dataset_id="DS-001",
                status="invalid_status",
                created_at="2025-01-01T00:00:00Z",
            )


class TestReleaseGateDecision:
    def test_valid_creation(self):
        decision = ReleaseGateDecision(
            release_gate_decision_id="RGD-001",
            experiment_id="EXP-001",
            decision=ReleaseDecision.PROMOTED,
            release_score=0.85,
            promotion_rules_passed=5,
            decided_at="2025-01-01T00:00:00Z",
        )
        assert decision.requires_human_approval is True
        assert decision.rules_detail_json is None


class TestHumanApproval:
    def test_valid_creation(self):
        approval = HumanApproval(
            human_approval_id="HA-001",
            release_gate_decision_id="RGD-001",
            reviewer_id="reviewer-1",
            created_at="2025-01-01T00:00:00Z",
        )
        assert approval.status == "pending"
        assert approval.comment is None
        assert approval.reviewed_at is None


class TestAuditEvent:
    def test_valid_creation(self):
        event = AuditEvent(
            audit_event_id="AE-001",
            entity_type="experiment",
            entity_id="EXP-001",
            action="created",
            actor="system",
            created_at="2025-01-01T00:00:00Z",
        )
        assert event.detail_json is None


# ---------------------------------------------------------------------------
# API Response envelope tests
# ---------------------------------------------------------------------------

class TestApiResponse:
    def test_success_response(self):
        resp = ApiResponse[str](ok=True, data="hello", request_id="req-1")
        assert resp.ok is True
        assert resp.data == "hello"
        assert resp.error is None

    def test_error_response(self):
        resp = ApiResponse[str](ok=False, error="Not found", request_id="req-2")
        assert resp.ok is False
        assert resp.data is None
        assert resp.error == "Not found"


class TestPaginatedData:
    def test_valid_creation(self):
        page = PaginatedData[str](
            items=["a", "b", "c"],
            total_count=10,
            page=1,
            page_size=3,
            has_next=True,
        )
        assert len(page.items) == 3
        assert page.has_next is True
