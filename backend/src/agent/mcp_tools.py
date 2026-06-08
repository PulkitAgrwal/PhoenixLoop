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

# The exact Phoenix MCP tools the diagnosis sub-agent is allowed to call.
# Enforced at construction time via McpToolset's tool_filter so the model
# literally cannot reach for anything outside this list — including
# list-projects, which requires a projectIdentifier we don't supply and
# fails at runtime, polluting traces with confidence=0 diagnoses.
DIAGNOSIS_ALLOWED_TOOLS: list[str] = [
    "get-spans",
    "get-span-annotations",
    "list-traces",
    "list-sessions",
    "list-experiments-for-dataset",
]


def build_phoenix_mcp_toolset(
    *, tool_filter: list[str] | None = None
) -> Any | None:
    """Build the Phoenix MCP toolset, or return None when unconfigured.

    Args:
        tool_filter: Optional whitelist of tool names. When provided, the
            returned toolset exposes ONLY these tools to the agent. Used
            to scope the diagnosis sub-agent's surface area (see
            ``DIAGNOSIS_ALLOWED_TOOLS``). When ``None`` (default), all
            Phoenix MCP tools are exposed.

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
        tool_filter=tool_filter,
    )
    logger.info(
        "Phoenix MCP toolset built (npx @arizeai/phoenix-mcp@latest, base_url=%s, tool_filter=%s)",
        settings.phoenix_base_url,
        tool_filter or "all",
    )
    return toolset


def build_diagnosis_mcp_toolset() -> Any | None:
    """Build a filtered Phoenix MCP toolset for the diagnosis sub-agent.

    Restricts the surface to ``DIAGNOSIS_ALLOWED_TOOLS`` so the model
    cannot opportunistically call tools that need credentials/args this
    pipeline doesn't supply (notably ``list-projects``).
    """
    return build_phoenix_mcp_toolset(tool_filter=DIAGNOSIS_ALLOWED_TOOLS)
