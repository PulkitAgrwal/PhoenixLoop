"""Tests that verify the agent stack runs cleanly without ``PHOENIX_API_KEY``.

"Run locally without Phoenix credentials" is a real developer workflow —
contributors who don't have a Phoenix Cloud account should still be able to
boot the backend, run the agent, and iterate on the UI. These tests pin
the degradation paths so we don't regress them by accident.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from src.agent.mcp_tools import build_phoenix_mcp_toolset
from src.agent.tools import retrieve_similar_resolutions
from src.config import Settings


def test_mcp_toolset_returns_none_when_key_unset() -> None:
    fake = Settings(phoenix_api_key="")
    with patch("src.agent.mcp_tools.get_settings", return_value=fake):
        toolset = build_phoenix_mcp_toolset()
    assert toolset is None


def test_retrieve_similar_resolutions_returns_empty_when_key_unset() -> None:
    fake = Settings(phoenix_api_key="")
    # Wipe cache before/after so the cached empty result doesn't poison
    # other tests in the same process.
    from src.agent import tools as tools_mod

    tools_mod._retrieval_cache.clear()
    try:
        with patch("src.agent.tools.get_settings", return_value=fake):
            result = retrieve_similar_resolutions("refund", "test brief")
    finally:
        tools_mod._retrieval_cache.clear()

    assert result["found"] is False
    assert result["examples"] == []
    assert "PHOENIX_API_KEY" in (result.get("reason") or "")


@pytest.mark.asyncio
async def test_diagnosis_agent_falls_back_when_toolset_unavailable() -> None:
    """No MCP toolset → diagnosis agent returns the fallback shape, not a crash."""
    from src.agent.diagnosis_agent import run_diagnosis_agent
    from src.models import ImprovementTrigger, TriggerReason

    trigger = ImprovementTrigger(
        improvement_trigger_id="trig-degraded",
        failure_key="test::failure",
        trigger_reason=TriggerReason.MANUAL_DEMO_TRIGGER,
        occurrence_count=1,
        example_run_ids_json=[],
        status="pending",
        created_at="2026-06-07T00:00:00+00:00",
        updated_at="2026-06-07T00:00:00+00:00",
    )

    result = await run_diagnosis_agent(trigger, mcp_toolset=None)
    assert result["mcp_status"] == "agent_fallback"
    assert result["confidence"] == 0.0
    assert "failure_pattern" in result
    assert "root_cause" in result
    assert isinstance(result.get("mcp_tools_used"), list)
