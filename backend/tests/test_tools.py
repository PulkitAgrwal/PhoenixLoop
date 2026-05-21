"""Tests for agent tool functions."""

import pytest

from src.agent.tools import (
    check_refund_eligibility,
    create_escalation,
    draft_customer_response,
    lookup_customer,
    lookup_subscription,
    search_policy,
)


# ---------------------------------------------------------------------------
# search_policy
# ---------------------------------------------------------------------------

class TestSearchPolicy:
    def test_search_refund_category_finds_excerpts(self):
        result = search_policy("refund", "refund")
        assert result["found"] is True
        assert result["source"] == "refunds.md"
        assert len(result["excerpts"]) > 0
        assert result["query"] == "refund"

    def test_search_billing_category(self):
        result = search_policy("payment", "billing")
        assert result["found"] is True
        assert result["source"] == "billing.md"
        assert len(result["excerpts"]) > 0

    def test_search_escalation_category(self):
        result = search_policy("escalation", "escalation")
        assert result["found"] is True
        assert result["source"] == "escalation.md"

    def test_search_legal_maps_to_escalation(self):
        result = search_policy("legal", "legal")
        assert result["found"] is True
        assert result["source"] == "escalation.md"

    def test_search_nonexistent_query_returns_not_found(self):
        result = search_policy("xyznonexistent_zzz_notaword", "billing")
        assert result["found"] is False
        assert result["source"] is None
        assert result["excerpts"] == []

    def test_search_unknown_category_searches_all(self):
        """An unrecognized category should search all policy files."""
        result = search_policy("refund", "unknown_category")
        assert result["found"] is True
        assert len(result["excerpts"]) > 0

    def test_search_returns_query_in_result(self):
        result = search_policy("eligibility window", "refund")
        assert result["query"] == "eligibility window"


# ---------------------------------------------------------------------------
# lookup_customer
# ---------------------------------------------------------------------------

class TestLookupCustomer:
    def test_valid_customer(self):
        result = lookup_customer("CUST-001")
        assert result["customer_id"] == "CUST-001"
        assert result["name"] == "Jane Doe"
        assert result["plan"] == "Pro"
        assert result["email"] == "jane.doe@example.com"

    def test_another_valid_customer(self):
        result = lookup_customer("CUST-002")
        assert result["customer_id"] == "CUST-002"
        assert result["name"] == "Marcus Rivera"
        assert result["plan"] == "Enterprise"

    def test_customer_not_found(self):
        result = lookup_customer("CUST-999")
        assert result["error"] == "Customer not found"
        assert result["customer_id"] == "CUST-999"

    def test_empty_customer_id(self):
        result = lookup_customer("")
        assert "error" in result

    def test_all_customer_fields_present(self):
        result = lookup_customer("CUST-003")
        expected_keys = {"customer_id", "name", "email", "plan", "signup_date", "workspace_role"}
        assert expected_keys.issubset(set(result.keys()))


# ---------------------------------------------------------------------------
# lookup_subscription
# ---------------------------------------------------------------------------

class TestLookupSubscription:
    def test_valid_subscription(self):
        result = lookup_subscription("CUST-001")
        assert result["subscription_id"] == "SUB-001"
        assert result["customer_id"] == "CUST-001"
        assert result["plan"] == "Pro"
        assert result["status"] == "active"

    def test_enterprise_subscription(self):
        result = lookup_subscription("CUST-002")
        assert result["plan"] == "Enterprise"
        assert result["billing_cycle"] == "annual"

    def test_subscription_not_found(self):
        result = lookup_subscription("CUST-999")
        assert result["error"] == "Subscription not found"
        assert result["customer_id"] == "CUST-999"

    def test_canceled_subscription(self):
        result = lookup_subscription("CUST-005")
        assert result["status"] == "canceled"
        assert result["canceled_at"] is not None

    def test_free_plan_subscription(self):
        result = lookup_subscription("CUST-004")
        assert result["plan"] == "Free"
        assert result["monthly_amount"] == 0


# ---------------------------------------------------------------------------
# check_refund_eligibility
# ---------------------------------------------------------------------------

class TestCheckRefundEligibility:
    def test_enterprise_not_eligible(self):
        """Enterprise refunds are handled by account management."""
        result = check_refund_eligibility("CUST-002", "CHG-100")
        assert result["eligible"] is False
        assert "account management" in result["reason"].lower()

    def test_free_plan_not_eligible(self):
        """Free plan has no charges to refund."""
        result = check_refund_eligibility("CUST-004", "CHG-200")
        assert result["eligible"] is False
        assert "free plan" in result["reason"].lower()

    def test_nonexistent_customer(self):
        """Non-existent customer should fail gracefully."""
        result = check_refund_eligibility("CUST-999", "CHG-300")
        assert result["eligible"] is False
        assert "lookup failed" in result["reason"].lower() or "not found" in result["reason"].lower()

    def test_pro_active_subscription(self):
        """CUST-001 is Pro/active with recent payment — should be eligible or
        outside window depending on date, but should not error."""
        result = check_refund_eligibility("CUST-001", "CHG-400")
        assert "eligible" in result
        assert "reason" in result
        assert result.get("charge_id") == "CHG-400"

    def test_another_enterprise_customer(self):
        """CUST-006 is Enterprise — should not be eligible."""
        result = check_refund_eligibility("CUST-006", "CHG-500")
        assert result["eligible"] is False
        assert "account management" in result["reason"].lower()

    def test_another_free_customer(self):
        """CUST-008 is Free — should not be eligible."""
        result = check_refund_eligibility("CUST-008", "CHG-600")
        assert result["eligible"] is False
        assert "free plan" in result["reason"].lower()

    def test_result_contains_charge_id(self):
        """All refund results should echo back the charge_id."""
        result = check_refund_eligibility("CUST-001", "CHG-700")
        assert result["charge_id"] == "CHG-700"


# ---------------------------------------------------------------------------
# create_escalation
# ---------------------------------------------------------------------------

class TestCreateEscalation:
    def test_creates_escalation_record(self):
        result = create_escalation("TKT-001", "Legal threat detected", "Legal")
        assert result["ticket_id"] == "TKT-001"
        assert result["target_team"] == "Legal"
        assert result["reason"] == "Legal threat detected"
        assert result["status"] == "created"
        assert result["escalation_id"].startswith("ESC-")

    def test_escalation_id_is_unique(self):
        r1 = create_escalation("TKT-001", "reason1", "Legal")
        r2 = create_escalation("TKT-002", "reason2", "Security")
        assert r1["escalation_id"] != r2["escalation_id"]

    def test_security_escalation(self):
        result = create_escalation("TKT-003", "Unauthorized access reported", "Security")
        assert result["target_team"] == "Security"
        assert result["status"] == "created"


# ---------------------------------------------------------------------------
# draft_customer_response
# ---------------------------------------------------------------------------

class TestDraftCustomerResponse:
    def test_returns_draft_and_tone(self):
        result = draft_customer_response(
            draft="We apologize for the inconvenience.",
            tone="empathetic",
        )
        assert result["draft"] == "We apologize for the inconvenience."
        assert result["tone"] == "empathetic"
        assert result["status"] == "ready"

    def test_professional_tone(self):
        result = draft_customer_response(
            draft="Your refund has been processed.",
            tone="professional",
        )
        assert result["tone"] == "professional"
        assert result["status"] == "ready"

    def test_empty_draft(self):
        result = draft_customer_response(draft="", tone="neutral")
        assert result["draft"] == ""
        assert result["status"] == "ready"
