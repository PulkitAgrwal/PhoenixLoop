"""Tests that ``create_agent`` wires the Phoenix MCP toolset when available."""

from unittest.mock import MagicMock, patch

import pytest
from google.adk.tools.base_toolset import BaseToolset
from src.agent.support_agent import create_agent


def test_create_agent_includes_phoenix_mcp_toolset_when_enabled():
    """When enable_mcp_toolset=True, the toolset is added to tools."""
    sentinel_toolset = MagicMock(spec=BaseToolset)
    with patch(
        "src.agent.support_agent.build_phoenix_mcp_toolset",
        return_value=sentinel_toolset,
    ):
        agent = create_agent(system_prompt="test prompt", enable_mcp_toolset=True)

    assert sentinel_toolset in agent.tools, (
        "Phoenix MCP toolset should be appended when enable_mcp_toolset=True"
    )


def test_create_agent_omits_toolset_by_default():
    """Default per-request agent does NOT include MCP toolset (stdio teardown clashes with FastAPI task scope)."""
    with patch(
        "src.agent.support_agent.build_phoenix_mcp_toolset",
        return_value=MagicMock(spec=BaseToolset),
    ) as builder:
        agent = create_agent(system_prompt="test prompt")

    builder.assert_not_called()
    # 4-tool consolidated surface: search_policy, get_customer_context,
    # retrieve_similar_resolutions, create_escalation.
    assert len(agent.tools) == 4


@pytest.mark.asyncio
async def test_run_agent_uses_session_attributes(monkeypatch, tmp_path):
    """run_agent should call openinference.using_attributes with session/user/request IDs."""
    import aiosqlite
    from src.agent.support_agent import run_agent
    from src.models import SupportTicket, TicketCategory

    ticket = SupportTicket(
        ticket_id="t-test-1",
        customer_id="cust-test",
        category=TicketCategory.BILLING,
        subject="test",
        body="test body",
        metadata_json={},
        created_at="2026-06-06T00:00:00Z",
        updated_at="2026-06-06T00:00:00Z",
    )

    captured: dict = {}

    class FakeAttrCtx:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(
        "src.agent.support_agent.using_attributes",
        lambda **kwargs: FakeAttrCtx(**kwargs),
    )

    async def fake_events(*args, **kwargs):
        return
        yield  # pragma: no cover

    class FakeRunner:
        def __init__(self, *a, **k):
            pass

        def run_async(self, **kw):
            return fake_events()

    monkeypatch.setattr("src.agent.support_agent.Runner", FakeRunner)
    monkeypatch.setattr(
        "src.agent.support_agent.create_agent",
        lambda prompt, **kw: object(),
    )

    async def fake_get_prompt(db):
        return ("test-prompt", "pv-1")

    monkeypatch.setattr("src.agent.support_agent.get_production_prompt", fake_get_prompt)

    class FakeSessionService:
        async def create_session(self, **kwargs):
            return None

    monkeypatch.setattr(
        "src.agent.support_agent.InMemorySessionService", lambda: FakeSessionService()
    )

    async with aiosqlite.connect(":memory:") as db:
        try:
            await run_agent(ticket, "sess-test-1", db, None)
        except Exception:
            pass

    assert captured.get("session_id") == "sess-test-1"
    assert captured.get("user_id") == "cust-test"
    metadata = captured.get("metadata") or {}
    assert "request_id" in metadata
