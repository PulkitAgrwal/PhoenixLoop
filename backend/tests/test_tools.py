"""Tests for the 4 consolidated agent tools."""

from unittest.mock import MagicMock, patch

import pytest
import src.agent.tools as tools_mod
from src.agent.tools import (
    create_escalation,
    get_customer_context,
    retrieve_similar_resolutions,
    search_policy,
)


@pytest.fixture(autouse=True)
def _clear_retrieval_cache():
    """Each test sees a clean cache; otherwise unrelated tests bleed state."""
    tools_mod._retrieval_cache.clear()
    yield
    tools_mod._retrieval_cache.clear()

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
# get_customer_context — consolidated profile + subscription + entitlements
# ---------------------------------------------------------------------------

class TestGetCustomerContext:
    def test_valid_customer_returns_profile_and_subscription(self):
        result = get_customer_context("cus_5WvnX4nq")
        assert result["found"] is True
        assert result["customer_id"] == "cus_5WvnX4nq"
        assert result["profile"]["name"] == "Maya Cole"
        assert result["profile"]["plan"] == "Pro"
        assert result["subscription"]["subscription_id"] == "SUB-001"
        assert result["subscription"]["status"] == "active"

    def test_unknown_customer_returns_found_false(self):
        result = get_customer_context("cus_does_not_exist")
        assert result["found"] is False
        assert result["customer_id"] == "cus_does_not_exist"
        assert result["profile"] is None
        assert result["subscription"] is None
        assert "error" in result

    def test_entitlements_always_present_even_for_unknown(self):
        """Agents should never have to handle a missing entitlements field."""
        result = get_customer_context("cus_does_not_exist")
        assert "entitlements" in result
        assert result["entitlements"]["refund_eligible"] is False

    def test_enterprise_refund_not_eligible_routes_to_account_mgmt(self):
        """Marcus Rivera is Enterprise — refunds handled by Account Management."""
        result = get_customer_context("cus_XIEADwIa")
        ent = result["entitlements"]
        assert ent["refund_eligible"] is False
        assert "account management" in ent["refund_reason"].lower()

    def test_free_plan_refund_not_eligible(self):
        """Liam Chen is Free — no charges to refund."""
        result = get_customer_context("cus_MAMb9OM3")
        ent = result["entitlements"]
        assert ent["refund_eligible"] is False
        assert "free plan" in ent["refund_reason"].lower()

    def test_canceled_subscription_outside_window_not_eligible(self):
        """Sofia Andersen canceled annual Pro long ago — outside refund window."""
        result = get_customer_context("cus_aH6NpKo2")
        ent = result["entitlements"]
        assert ent["refund_eligible"] is False
        assert "window" in ent["refund_reason"].lower()

    def test_eligible_customer_has_amount_and_type(self):
        """When eligible, entitlements include refund_type and refund_amount."""
        result = get_customer_context("cus_5WvnX4nq")
        ent = result["entitlements"]
        if ent["refund_eligible"]:
            assert ent["refund_type"] in ("full", "pro_rata")
            assert isinstance(ent["refund_amount"], (int, float))
            assert ent["days_since_last_payment"] is not None

    def test_recent_tickets_filtered_to_customer(self):
        """recent_tickets contains only tickets belonging to the customer."""
        result = get_customer_context("cus_5WvnX4nq")
        assert isinstance(result["recent_tickets"], list)
        for t in result["recent_tickets"]:
            assert "ticket_id" in t
            assert "subject" in t
            assert "category" in t
            # body intentionally omitted to keep token cost flat
            assert "body" not in t

    def test_profile_shape_keys(self):
        result = get_customer_context("cus_Jmvq4zyy")
        expected_keys = {"name", "email", "plan", "signup_date", "workspace_role"}
        assert expected_keys.issubset(set(result["profile"].keys()))


# ---------------------------------------------------------------------------
# retrieve_similar_resolutions
# ---------------------------------------------------------------------------


class TestRetrieveSimilarResolutions:
    def test_returns_empty_when_phoenix_key_unset(self, monkeypatch):
        """No PHOENIX_API_KEY → graceful degradation, no examples, no crash."""
        from src.config import Settings, get_settings

        get_settings.cache_clear()
        monkeypatch.setenv("PHOENIX_API_KEY", "")
        # Force a fresh Settings read by clearing the lru_cache.
        # (Settings reads from .env which may still set the key — patch directly.)
        fake = Settings(phoenix_api_key="")
        with patch("src.agent.tools.get_settings", return_value=fake):
            result = retrieve_similar_resolutions("refund", "duplicate charge refund")
        assert result["found"] is False
        assert result["examples"] == []
        assert "PHOENIX_API_KEY" in result["reason"]

    def test_returns_empty_when_phoenix_client_unavailable(self):
        """Settings has a key but get_phoenix_client returns None → degrade."""
        from src.config import Settings

        fake = Settings(phoenix_api_key="fake-key")
        with patch("src.agent.tools.get_settings", return_value=fake), \
             patch("src.agent.tools.get_phoenix_client", return_value=None):
            result = retrieve_similar_resolutions("refund", "duplicate charge")
        assert result["found"] is False
        assert result["examples"] == []

    def test_returns_empty_when_dataset_lookup_raises(self):
        """Phoenix call raises (dataset missing, network) → degrade silently."""
        from src.config import Settings

        fake = Settings(phoenix_api_key="fake-key")
        fake_client = MagicMock()
        fake_client.datasets.get_dataset.side_effect = RuntimeError("not found")

        with patch("src.agent.tools.get_settings", return_value=fake), \
             patch(
                 "src.agent.tools.get_phoenix_client",
                 return_value=fake_client,
             ):
            result = retrieve_similar_resolutions("refund", "duplicate charge")
        assert result["found"] is False
        assert result["examples"] == []
        assert "Dataset lookup failed" in result["reason"]

    def test_returns_top_3_filtered_by_category(self):
        """Returns only same-category examples, capped at 3."""
        from src.config import Settings

        fake = Settings(phoenix_api_key="fake-key")
        fake_dataset = MagicMock()
        fake_dataset.examples = [
            {
                "id": f"ex-{i}",
                "input": {"subject": f"refund #{i}", "body": "I need a refund"},
                "output": {"answer": f"answer-{i}", "citations": ["POL-REFUND-001"]},
                "metadata": {"category": "refund"},
            }
            for i in range(5)
        ] + [
            {
                "id": "ex-billing",
                "input": {"subject": "billing"},
                "output": {"answer": "billing answer"},
                "metadata": {"category": "billing"},
            },
        ]
        fake_client = MagicMock()
        fake_client.datasets.get_dataset.return_value = fake_dataset

        with patch("src.agent.tools.get_settings", return_value=fake), \
             patch(
                 "src.agent.tools.get_phoenix_client",
                 return_value=fake_client,
             ):
            result = retrieve_similar_resolutions("refund", "I need a refund")

        assert result["found"] is True
        assert len(result["examples"]) == 3
        for ex in result["examples"]:
            assert ex["category"] == "refund"
            assert ex["id"].startswith("ex-")
            assert ex["id"] != "ex-billing"
        # Cap respected.
        assert len(result["examples"]) <= 3

    def test_returns_not_found_when_no_category_matches(self):
        """Dataset has examples but none match the requested category."""
        from src.config import Settings

        fake = Settings(phoenix_api_key="fake-key")
        fake_dataset = MagicMock()
        fake_dataset.examples = [
            {
                "id": "ex-billing",
                "input": {"subject": "billing"},
                "output": {"answer": "billing answer"},
                "metadata": {"category": "billing"},
            },
        ]
        fake_client = MagicMock()
        fake_client.datasets.get_dataset.return_value = fake_dataset

        with patch("src.agent.tools.get_settings", return_value=fake), \
             patch(
                 "src.agent.tools.get_phoenix_client",
                 return_value=fake_client,
             ):
            result = retrieve_similar_resolutions("refund", "anything")
        assert result["found"] is False
        assert result["examples"] == []
        assert "refund" in result["reason"]

    def test_caches_within_ttl(self):
        """Second call with same args reuses the cache and skips Phoenix."""
        from src.config import Settings

        fake = Settings(phoenix_api_key="fake-key")
        fake_dataset = MagicMock()
        fake_dataset.examples = [
            {
                "id": "ex-1",
                "input": {"subject": "refund"},
                "output": {"answer": "a"},
                "metadata": {"category": "refund"},
            },
        ]
        fake_client = MagicMock()
        fake_client.datasets.get_dataset.return_value = fake_dataset

        with patch("src.agent.tools.get_settings", return_value=fake), \
             patch(
                 "src.agent.tools.get_phoenix_client",
                 return_value=fake_client,
             ):
            retrieve_similar_resolutions("refund", "first call")
            retrieve_similar_resolutions("refund", "first call")
        assert fake_client.datasets.get_dataset.call_count == 1


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
