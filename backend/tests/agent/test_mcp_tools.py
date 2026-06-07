"""Tests for the Phoenix MCP toolset factory."""

from unittest.mock import patch

import pytest
from src.agent.mcp_tools import build_phoenix_mcp_toolset


def test_build_phoenix_mcp_toolset_returns_toolset(monkeypatch):
    """Factory returns a non-None McpToolset when env vars are set."""
    monkeypatch.setenv("PHOENIX_API_KEY", "test-key")
    monkeypatch.setenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com")

    from src.config import get_settings

    get_settings.cache_clear()
    try:
        toolset = build_phoenix_mcp_toolset()
    finally:
        get_settings.cache_clear()

    assert toolset is not None
    assert "McpToolset" in type(toolset).__name__


def test_build_phoenix_mcp_toolset_skips_when_missing_api_key(monkeypatch):
    """Factory returns None when PHOENIX_API_KEY is empty so dev/test runs don't crash."""
    monkeypatch.setenv("PHOENIX_API_KEY", "")
    monkeypatch.setenv("PHOENIX_BASE_URL", "https://app.phoenix.arize.com")

    from src.config import get_settings

    get_settings.cache_clear()
    try:
        toolset = build_phoenix_mcp_toolset()
    finally:
        get_settings.cache_clear()

    assert toolset is None


@pytest.mark.asyncio
async def test_build_phoenix_mcp_toolset_passes_env(monkeypatch):
    """Subprocess env passed to npx must include PHOENIX_API_KEY and PHOENIX_BASE_URL."""
    monkeypatch.setenv("PHOENIX_API_KEY", "test-key-xyz")
    monkeypatch.setenv("PHOENIX_BASE_URL", "https://example.phoenix.test")

    from src.config import get_settings

    get_settings.cache_clear()

    captured: dict = {}

    with patch("src.agent.mcp_tools.McpToolset") as mock_cls:
        mock_cls.side_effect = lambda **kwargs: captured.setdefault("kwargs", kwargs) or object()
        try:
            build_phoenix_mcp_toolset()
        finally:
            get_settings.cache_clear()

    conn = captured["kwargs"].get("connection_params") or captured["kwargs"].get("server_params")
    assert conn is not None, f"factory did not pass connection_params; got {captured['kwargs']!r}"
