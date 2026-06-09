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
- ``baseline_avg_score`` / ``post_heal_avg_score`` / ``delta_pct``:
  mean release scores across completed experiments — the headline
  "match rate" improvement number for the landing-page strip.
- ``auto_promoted_regression_count``: how many regression rows came
  from the auto-promote pipeline (vs manual diagnosis-derived rows).
"""

import json
import logging

import aiosqlite
from fastapi import APIRouter, Depends

from src.api.dependencies import get_db_session, get_request_id
from src.db import list_regression_examples_auto_promoted
from src.models import ApiResponse, StatsResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stats"])

# 7 code + 4 LLM judges + 3 Phoenix tool evals. Static — see
# `evaluation/runner.py:CODE_EVALUATORS` and
# `evaluation/llm_judges/combined.JUDGE_NAMES`.
EVALUATORS_WIRED = 7 + 4 + 3

_RECENT_RUN_SAMPLE = 50

# Cap the auto-promoted lookup so a huge backfill doesn't pull millions
# of rows just to count them. The CRUD function takes a ``limit``
# argument (no count-only helper exists for this filter yet); we cap at
# 10 000 to match the task spec.
_AUTO_PROMOTED_LIMIT = 10_000


class StatsExtendedResponse(StatsResponse):
    """Stats payload extended with the multi-dim healing metrics.

    Extends ``StatsResponse`` (defined in ``models.py``) so the existing
    four-field landing-page contract stays intact while the new
    healing-loop fields can be appended without touching shared models.
    """

    baseline_avg_score: float | None = None
    post_heal_avg_score: float | None = None
    delta_pct: float | None = None
    auto_promoted_regression_count: int = 0


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

    cur = await db.execute(
        "SELECT AVG(baseline_release_score), AVG(candidate_release_score) "
        "FROM experiments WHERE status = 'completed' "
        "AND baseline_release_score IS NOT NULL "
        "AND candidate_release_score IS NOT NULL"
    )
    row = await cur.fetchone()
    baseline_avg = float(row[0]) if row and row[0] is not None else None
    post_heal_avg = float(row[1]) if row and row[1] is not None else None
    delta_pct = _delta_pct(baseline_avg, post_heal_avg)

    auto_promoted_rows = await list_regression_examples_auto_promoted(
        db, limit=_AUTO_PROMOTED_LIMIT
    )
    auto_promoted_count = len(auto_promoted_rows)

    return ApiResponse(
        ok=True,
        data=StatsExtendedResponse(
            agent_runs_traced=agent_runs_traced,
            evaluators_wired=EVALUATORS_WIRED,
            mcp_tool_calls_per_run_avg=round(mcp_avg, 2),
            prompts_auto_promoted=promoted,
            baseline_avg_score=(
                round(baseline_avg, 4) if baseline_avg is not None else None
            ),
            post_heal_avg_score=(
                round(post_heal_avg, 4) if post_heal_avg is not None else None
            ),
            delta_pct=(round(delta_pct, 2) if delta_pct is not None else None),
            auto_promoted_regression_count=auto_promoted_count,
        ),
        request_id=request_id,
    )


def _delta_pct(baseline: float | None, post_heal: float | None) -> float | None:
    """Percent improvement of post_heal over baseline.

    Returns ``None`` when either value is missing or when baseline is
    zero (avoids ZeroDivisionError and a meaningless +infinity).
    """
    if baseline is None or post_heal is None:
        return None
    if baseline == 0.0:
        return None
    return ((post_heal - baseline) / baseline) * 100.0


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
