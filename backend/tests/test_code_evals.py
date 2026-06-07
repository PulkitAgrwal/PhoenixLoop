"""Tests for all 7 code-based evaluators."""

import pytest
from src.evaluation.code_evals.citation_presence import CitationPresenceEvaluator
from src.evaluation.code_evals.escalation_guard import EscalationGuardEvaluator
from src.evaluation.code_evals.latency_budget import LatencyBudgetEvaluator
from src.evaluation.code_evals.privacy_guard import PrivacyGuardEvaluator
from src.evaluation.code_evals.refund_guard import RefundGuardEvaluator
from src.evaluation.code_evals.schema_validity import SchemaValidityEvaluator
from src.evaluation.code_evals.tool_sequence import ToolSequenceEvaluator
from src.models import AgentRun, SupportTicket

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def make_run(
    response_json: dict | None = None,
    tool_calls: list | None = None,
    latency_ms: int = 1000,
    ticket_id: str = "TKT-001",
) -> AgentRun:
    """Create a test AgentRun with sensible defaults."""
    return AgentRun(
        agent_run_id="test-run-1",
        conversation_session_id="test-session-1",
        ticket_id=ticket_id,
        prompt_version="v1",
        response_json=response_json or {
            "answer": "test",
            "citations": ["refunds.md"],
            "tools_used": ["get_customer_context"],
            "escalated": False,
            "confidence": 0.9,
        },
        tool_calls_json=tool_calls or [],
        status="success",
        latency_ms=latency_ms,
        created_at="2026-05-17T00:00:00Z",
    )


def make_ticket(category: str = "refund", body: str = "I want a refund") -> SupportTicket:
    """Create a test SupportTicket with sensible defaults."""
    return SupportTicket(
        ticket_id="TKT-001",
        customer_id="cus_AAAA0001",
        category=category,
        subject="Test ticket",
        body=body,
        created_at="2026-05-17T00:00:00Z",
        updated_at="2026-05-17T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# SchemaValidityEvaluator
# ---------------------------------------------------------------------------

class TestSchemaValidityEvaluator:
    """Tests for SchemaValidityEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_valid_response(self) -> None:
        evaluator = SchemaValidityEvaluator()
        run = make_run()
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_fail_missing_answer(self) -> None:
        evaluator = SchemaValidityEvaluator()
        run = make_run(response_json={
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.5,
        })
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert result.score == 0.0
        assert "answer" in result.explanation

    @pytest.mark.asyncio
    async def test_fail_empty_answer(self) -> None:
        evaluator = SchemaValidityEvaluator()
        run = make_run(response_json={
            "answer": "   ",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.5,
        })
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "empty" in result.explanation

    @pytest.mark.asyncio
    async def test_fail_wrong_type_confidence(self) -> None:
        evaluator = SchemaValidityEvaluator()
        run = make_run(response_json={
            "answer": "test",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": "high",
        })
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "confidence" in result.explanation

    @pytest.mark.asyncio
    async def test_fail_confidence_out_of_range(self) -> None:
        evaluator = SchemaValidityEvaluator()
        run = make_run(response_json={
            "answer": "test",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 1.5,
        })
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "confidence" in result.explanation


# ---------------------------------------------------------------------------
# ToolSequenceEvaluator
# ---------------------------------------------------------------------------

class TestToolSequenceEvaluator:
    """Tests for ToolSequenceEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_refund_with_required_tool(self) -> None:
        evaluator = ToolSequenceEvaluator()
        run = make_run(tool_calls=[
            {"tool_name": "get_customer_context", "input": {}, "output": {}},
        ])
        ticket = make_ticket(category="refund")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_fail_refund_missing_tool(self) -> None:
        evaluator = ToolSequenceEvaluator()
        run = make_run(tool_calls=[
            {"tool_name": "search_policy", "input": {}, "output": {}},
        ])
        ticket = make_ticket(category="refund")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "get_customer_context" in result.explanation

    @pytest.mark.asyncio
    async def test_pass_ambiguous_no_requirements(self) -> None:
        evaluator = ToolSequenceEvaluator()
        run = make_run()
        ticket = make_ticket(category="ambiguous")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"


# ---------------------------------------------------------------------------
# RefundGuardEvaluator
# ---------------------------------------------------------------------------

class TestRefundGuardEvaluator:
    """Tests for RefundGuardEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_refund_verified(self) -> None:
        evaluator = RefundGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "Your refund will be processed within 5 business days.",
                "citations": ["refunds.md"],
                "tools_used": ["get_customer_context"],
                "escalated": False,
                "confidence": 0.95,
            },
            tool_calls=[
                {
                    "tool_name": "get_customer_context",
                    "input": {"customer_id": "cus_AAAA0001"},
                    "output": {
                        "found": True,
                        "entitlements": {
                            "refund_eligible": True,
                            "refund_reason": "within_policy",
                        },
                    },
                },
            ],
        )
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_refund_without_check(self) -> None:
        evaluator = RefundGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "Your refund will be processed shortly.",
                "citations": [],
                "tools_used": [],
                "escalated": False,
                "confidence": 0.8,
            },
            tool_calls=[],
        )
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "get_customer_context" in result.explanation

    @pytest.mark.asyncio
    async def test_pass_no_refund_language(self) -> None:
        evaluator = RefundGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "I can help you look into your account.",
                "citations": [],
                "tools_used": [],
                "escalated": False,
                "confidence": 0.8,
            },
        )
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_refund_not_eligible(self) -> None:
        evaluator = RefundGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "We'll refund your purchase immediately.",
                "citations": [],
                "tools_used": ["get_customer_context"],
                "escalated": False,
                "confidence": 0.9,
            },
            tool_calls=[
                {
                    "tool_name": "get_customer_context",
                    "input": {"customer_id": "cus_AAAA0001"},
                    "output": {
                        "found": True,
                        "entitlements": {
                            "refund_eligible": False,
                            "refund_reason": "outside_policy",
                        },
                    },
                },
            ],
        )
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "refund_eligible" in result.explanation


# ---------------------------------------------------------------------------
# PrivacyGuardEvaluator
# ---------------------------------------------------------------------------

class TestPrivacyGuardEvaluator:
    """Tests for PrivacyGuardEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_clean_response(self) -> None:
        evaluator = PrivacyGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "Your account has been updated successfully.",
                "citations": [],
                "tools_used": [],
                "escalated": False,
                "confidence": 0.9,
            },
        )
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_other_customer_email(self) -> None:
        evaluator = PrivacyGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "I found the account. The email on file is bob@example.com.",
                "citations": [],
                "tools_used": [],
                "escalated": False,
                "confidence": 0.9,
            },
        )
        # Ticket is for cus_AAAA0001 (Alice), but response contains Bob's email
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "bob@example.com" in result.explanation

    @pytest.mark.asyncio
    async def test_pass_own_email(self) -> None:
        evaluator = PrivacyGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "Your email on file is alice@example.com.",
                "citations": [],
                "tools_used": [],
                "escalated": False,
                "confidence": 0.9,
            },
        )
        # Ticket is for cus_AAAA0001 (Alice) — her own email is fine
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_other_customer_name(self) -> None:
        evaluator = PrivacyGuardEvaluator()
        run = make_run(
            response_json={
                "answer": "I can see that Bob Smith also has a similar issue.",
                "citations": [],
                "tools_used": [],
                "escalated": False,
                "confidence": 0.9,
            },
        )
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "Bob Smith" in result.explanation


# ---------------------------------------------------------------------------
# EscalationGuardEvaluator
# ---------------------------------------------------------------------------

class TestEscalationGuardEvaluator:
    """Tests for EscalationGuardEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_legal_with_escalation(self) -> None:
        evaluator = EscalationGuardEvaluator()
        run = make_run(
            tool_calls=[
                {"tool_name": "create_escalation", "input": {}, "output": {}},
            ],
        )
        ticket = make_ticket(category="legal", body="I need legal assistance")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_legal_without_escalation(self) -> None:
        evaluator = EscalationGuardEvaluator()
        run = make_run(tool_calls=[])
        ticket = make_ticket(category="legal", body="I need legal assistance")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "create_escalation" in result.explanation

    @pytest.mark.asyncio
    async def test_pass_non_legal_no_escalation_needed(self) -> None:
        evaluator = EscalationGuardEvaluator()
        run = make_run(tool_calls=[])
        ticket = make_ticket(category="billing", body="I have a billing question")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_lawyer_keyword_without_escalation(self) -> None:
        evaluator = EscalationGuardEvaluator()
        run = make_run(tool_calls=[])
        ticket = make_ticket(
            category="refund",
            body="I want a refund or I will contact my lawyer about this",
        )
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"

    @pytest.mark.asyncio
    async def test_pass_lawyer_keyword_with_escalation(self) -> None:
        evaluator = EscalationGuardEvaluator()
        run = make_run(
            tool_calls=[
                {"tool_name": "create_escalation", "input": {}, "output": {}},
            ],
        )
        ticket = make_ticket(
            category="refund",
            body="I want a refund or I will contact my lawyer",
        )
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"


# ---------------------------------------------------------------------------
# CitationPresenceEvaluator
# ---------------------------------------------------------------------------

class TestCitationPresenceEvaluator:
    """Tests for CitationPresenceEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_with_citations(self) -> None:
        evaluator = CitationPresenceEvaluator()
        run = make_run(response_json={
            "answer": "Per our refund policy...",
            "citations": ["refunds.md"],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.9,
        })
        ticket = make_ticket(category="refund")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_fail_no_citations_on_refund(self) -> None:
        evaluator = CitationPresenceEvaluator()
        run = make_run(response_json={
            "answer": "Your refund has been processed.",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.9,
        })
        ticket = make_ticket(category="refund")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert "citations" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_pass_legal_exempt(self) -> None:
        evaluator = CitationPresenceEvaluator()
        run = make_run(response_json={
            "answer": "This has been escalated to our legal team.",
            "citations": [],
            "tools_used": [],
            "escalated": True,
            "confidence": 0.9,
        })
        ticket = make_ticket(category="legal")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_pass_ambiguous_exempt(self) -> None:
        evaluator = CitationPresenceEvaluator()
        run = make_run(response_json={
            "answer": "Could you clarify your question?",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.3,
        })
        ticket = make_ticket(category="ambiguous")
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"


# ---------------------------------------------------------------------------
# LatencyBudgetEvaluator
# ---------------------------------------------------------------------------

class TestLatencyBudgetEvaluator:
    """Tests for LatencyBudgetEvaluator."""

    @pytest.mark.asyncio
    async def test_pass_within_budget(self) -> None:
        evaluator = LatencyBudgetEvaluator()
        run = make_run(latency_ms=5000)
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"
        assert result.score == 1.0

    @pytest.mark.asyncio
    async def test_fail_exceeds_budget(self) -> None:
        evaluator = LatencyBudgetEvaluator()
        run = make_run(latency_ms=15000)
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "fail"
        assert result.score == 0.0
        assert "15000" in result.explanation

    @pytest.mark.asyncio
    async def test_pass_no_latency_recorded(self) -> None:
        evaluator = LatencyBudgetEvaluator()
        run = make_run(latency_ms=0)
        # Override latency_ms to None
        run.latency_ms = None
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"

    @pytest.mark.asyncio
    async def test_pass_exactly_at_budget(self) -> None:
        evaluator = LatencyBudgetEvaluator()
        run = make_run(latency_ms=10000)
        ticket = make_ticket()
        result = await evaluator.evaluate(run, ticket)
        assert result.outcome == "pass"
