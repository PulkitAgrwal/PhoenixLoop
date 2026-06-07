"""Public stats endpoint for the landing-page metrics strip.

Pure SQL — no Gemini calls. Reads:

- ``agent_runs_traced``: count of ``agent_runs`` with a non-null
  ``trace_id``. After P0-1 every real run is traced; the count is also
  the headline "we observe the agent" claim.
- ``evaluators_wired``: static count of registered evaluators (7 code
  + 4 LLM judges + 3 Phoenix tool evals). Static because the constant
  matters for the messaging, not for live introspection.
- ``mcp_tool_calls_per_run_avg``: average number of ``phoenix-mcp:`` /
  MCP-prefixed tool calls per recent agent run. Approximate — pulled
  from the JSON blob, capped at the most recent 50 runs.
- ``prompts_auto_promoted``: count of release-gate decisions with
  ``decision='promoted'`` (the self-improvement loop closing).
"""

import json
import logging

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import get_db_session, get_request_id
from src.models import ApiResponse, StatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])

# 7 code + 4 LLM judges + 3 Phoenix tool evals. Static — see
# `evaluation/runner.py:CODE_EVALUATORS` and
# `evaluation/llm_judges/combined.JUDGE_NAMES`.
EVALUATORS_WIRED = 7 + 4 + 3

_RECENT_RUN_SAMPLE = 50


@router.get("/stats")
async def get_stats(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Return landing-page stats. Pure SQL, no Gemini calls."""
    cur = await db.execute(
        "SELECT COUNT(*) FROM agent_runs WHERE trace_id IS NOT NULL"
    )
    row = await cur.fetchone()
    agent_runs_traced = int(row[0]) if row else 0

    cur = await db.execute(
        "SELECT tool_calls_json FROM agent_runs "
        "ORDER BY created_at DESC LIMIT ?",
        (_RECENT_RUN_SAMPLE,),
    )
    samples = await cur.fetchall()
    mcp_avg = _mcp_calls_per_run_avg(samples)

    cur = await db.execute(
        "SELECT COUNT(*) FROM release_gate_decisions WHERE decision = 'promoted'"
    )
    row = await cur.fetchone()
    promoted = int(row[0]) if row else 0

    return ApiResponse(
        ok=True,
        data=StatsResponse(
            agent_runs_traced=agent_runs_traced,
            evaluators_wired=EVALUATORS_WIRED,
            mcp_tool_calls_per_run_avg=round(mcp_avg, 2),
            prompts_auto_promoted=promoted,
        ),
        request_id=request_id,
    )


def _mcp_calls_per_run_avg(rows: list) -> float:
    """Average MCP tool calls across the sampled runs.

    Tool names produced by the lifespan-managed MCP toolset typically start
    with ``phoenix-mcp:`` or are exact Phoenix MCP tool names (``get-spans``,
    ``get-dataset-examples``, ``get-span-annotations``, ``add-dataset-examples``).
    We count any of those patterns to keep the metric stable across ADK
    version drifts in how MCP tool names are reported.
    """
    if not rows:
        return 0.0

    mcp_total = 0
    counted_runs = 0
    for row in rows:
        raw = row[0] if row else None
        if not raw:
            continue
        try:
            tool_calls = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(tool_calls, list):
            continue
        counted_runs += 1
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            name = (tc.get("tool_name") or "").lower()
            if _looks_like_mcp_call(name):
                mcp_total += 1

    return (mcp_total / counted_runs) if counted_runs else 0.0


_MCP_TOOL_HINTS = (
    "phoenix-mcp:",
    "get-spans",
    "get-span-annotations",
    "get-dataset",
    "add-dataset-examples",
    "list-datasets",
    "get-prompt",
)


def _looks_like_mcp_call(tool_name: str) -> bool:
    return any(hint in tool_name for hint in _MCP_TOOL_HINTS)
