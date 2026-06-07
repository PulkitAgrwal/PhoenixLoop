"""Phoenix MCP toolset factory for the support agent.

Wires ``@arizeai/phoenix-mcp`` (spawned via ``npx``) into the Google ADK
agent's tool list so the model can introspect Phoenix at runtime — query
its own spans, look up prompt versions, push examples to datasets.

The factory returns ``None`` when ``PHOENIX_API_KEY`` is unset so local
or test runs without Phoenix credentials don't crash the agent boot path.
"""

from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp.client.stdio import StdioServerParameters

from src.config import get_settings

logger = logging.getLogger(__name__)


def build_phoenix_mcp_toolset() -> Any | None:
    """Build the Phoenix MCP toolset, or return None when unconfigured.

    Returns:
        An ``McpToolset`` instance ready to register on the ADK agent's
        ``tools=[...]`` list, or ``None`` when ``PHOENIX_API_KEY`` is empty.
    """
    settings = get_settings()
    if not settings.phoenix_api_key:
        logger.warning(
            "Phoenix MCP toolset not built: PHOENIX_API_KEY is empty. "
            "Agent will run without runtime Phoenix introspection."
        )
        return None

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@arizeai/phoenix-mcp@latest"],
        env={
            "PHOENIX_API_KEY": settings.phoenix_api_key,
            "PHOENIX_BASE_URL": settings.phoenix_base_url,
        },
    )

    # 60s timeout — first `npx @arizeai/phoenix-mcp@latest` invocation has
    # to fetch the package and spawn Node, which can blow past the 5s default
    # on cold starts.
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=server_params,
            timeout=60.0,
        ),
    )
    logger.info(
        "Phoenix MCP toolset built (npx @arizeai/phoenix-mcp@latest, base_url=%s)",
        settings.phoenix_base_url,
    )
    return toolset
