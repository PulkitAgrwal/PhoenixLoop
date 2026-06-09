"""Diagnosis sub-agent.

An ADK Agent whose toolbelt IS Phoenix MCP. When a failure cluster reaches
the threshold, the support team (or the auto-seed path) invokes this agent
with the cluster's ``failure_key`` and sample run IDs. The agent fetches
the failing spans + their eval annotations via Phoenix MCP, identifies the
common failure pattern, and emits a structured ``DiagnosisAgentResult``.

This is the honest answer to the Arize bonus criterion — an agent that
reads its own observability data to decide what to fix. The ``phoenix-mcp:``
spans the agent produces are real, not theater: the agent cannot complete
its job without them.

Token economy: the agent is constrained by prompt to make at most 4 MCP
tool calls and emit the final JSON in the same turn, so each invocation
is ~3 Gemini calls (planner + 2 tool-call turns + final answer). Logged
under ``gemini_call_purpose=diagnosis_agent``.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from typing import TYPE_CHECKING, Any

from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from openinference.instrumentation import using_attributes
from pydantic import BaseModel, Field, ValidationError

from src.config import get_settings
from src.models import ImprovementTrigger

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

DIAGNOSIS_APP_NAME = "phoenixloop"
DIAGNOSIS_AGENT_NAME = "phoenixloop_diagnosis_agent"


class DiagnosisAgentResult(BaseModel):
    """Structured output the diagnosis agent must emit.

    Mapped onto the existing ``trigger.diagnosis_json`` shape so the UI
    (which already renders ``failure_pattern`` / ``root_cause`` /
    ``evidence`` / ``confidence`` / ``suggested_fix``) keeps working without
    changes. ``mcp_tools_used`` is new — it powers the Diagnosis Trace
    panel in the redesigned UI.
    """

    failure_pattern: str = Field(min_length=1, max_length=400)
    root_cause: str = Field(min_length=1, max_length=2000)
    evidence_summary: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_fix: str = Field(min_length=1, max_length=2000)
    mcp_tools_used: list[str] = Field(default_factory=list)


DIAGNOSIS_INSTRUCTION = """\
You are the PhoenixLoop diagnosis agent. You reason over the support \
agent's own observability data to figure out why a failure cluster keeps \
repeating. You are NOT a customer-facing agent — your output is consumed \
by a release-gate pipeline.

## Available tools

Your Phoenix MCP toolset is restricted by the runtime to these five \
tools, plus one local clustering helper:

1. **get-spans** — fetch failing spans for a given trace_id or session_id.
   Useful for inspecting tool calls, latencies, errors.
2. **get-span-annotations** — fetch the eval annotations attached to a span.
   Useful for reading which evaluators failed and why.
3. **list-traces** — enumerate recent traces in a project. Useful when you \
need to confirm the failure cluster is still active (most-recent first).
4. **list-sessions** — enumerate recent sessions. Useful to scope down a \
noisy project before calling get-spans.
5. **list-experiments-for-dataset** — list past experiments tied to a \
dataset. Useful when you want to check whether a similar fix has already \
been A/B-tested and what its scores were.
6. **extract_categories** — LOCAL tool (not MCP). Given a ``failure_key``, \
asks Gemini to cluster the runs that fell under that key into 3-5 \
mutually exclusive failure categories. Call this AFTER you have used \
``get-spans`` / ``get-span-annotations`` to confirm what the cluster \
looks like; the categories belong in your ``evidence_summary``.

Prefer the broad list-* tools first to locate signal, then narrow with \
get-spans and get-span-annotations, then call ``extract_categories`` to \
crystallize the failure modes.

**Forbidden calls** — never invoke ``list-projects``, ``get-prompt``, \
``upsert-prompt``, ``add-prompt-version-tag``, or any tool not in the \
six listed above. ``list-projects`` in particular fails in this \
pipeline and will drop your confidence to zero. The Phoenix project \
name you need is supplied directly in the user message — use it.

## Constraints — read carefully

- Make AT MOST 3 tool calls total per diagnosis (typically 2 MCP calls \
plus 1 ``extract_categories``). We are token-budgeted.
- **EVERY MCP tool call MUST include the ``projectIdentifier`` argument set \
to the project name from the user message** (e.g. ``projectIdentifier="phoenixloop"``). \
The Phoenix MCP read tools error out without it. Do not skip the tools \
on this basis — pass the argument every time.
- ``extract_categories`` only needs the ``failure_key`` from the user \
message; no ``projectIdentifier``.
- After your evidence is gathered, emit your final answer as a single \
JSON object — no markdown fences, no prose around it.
- Do not invent evidence. If the MCP calls return nothing useful, say so \
in ``evidence_summary`` and lower your ``confidence`` accordingly.
- If ``extract_categories`` returns categories, embed a one-line summary \
of them inside ``evidence_summary``.

## Output schema

Your final response MUST be a single JSON object with these fields:

```json
{
  "failure_pattern": "one-line description of the recurring failure",
  "root_cause": "underlying reason — what's wrong with the prompt, tool, or data flow",
  "evidence_summary": "1-3 sentence summary of what you saw in spans/annotations + categories from extract_categories",
  "confidence": 0.0,
  "suggested_fix": "the smallest prompt change that would address this",
  "mcp_tools_used": ["get-spans", "get-span-annotations", "extract_categories"]
}
```

Confidence rubric:
- 0.9+ — multiple spans clearly show the same root cause
- 0.6-0.8 — pattern is plausible but evidence is partial
- 0.3-0.5 — guess based on the failure_key alone
- 0.0-0.2 — no useful evidence; fall back to the failure_key text
"""


def create_diagnosis_agent(
    mcp_toolset: Any | None,
    *,
    db: "aiosqlite.Connection | None" = None,
) -> Agent:
    """Build the diagnosis ADK agent.

    ``mcp_toolset`` is the lifespan-managed Phoenix MCP toolset from
    ``app.state.phoenix_mcp_toolset``. When ``None`` the agent is built
    with no tools — useful only for unit tests; the caller should fall
    back to the service-side ``diagnose()`` path instead.

    ``db`` is the aiosqlite connection. When supplied, the ``extract_categories``
    tool is wired in as a closure so the model can call it without
    knowing about the DB session. The field name is kept identical to
    ``src.agent.tools.extract_categories`` so the frontend's
    ``mcp_tools_used`` checklist matches.
    """
    tools: list = []
    if mcp_toolset is not None:
        tools.append(mcp_toolset)
        logger.debug(
            "Diagnosis agent constructed with Phoenix MCP toolset attached"
        )
    else:
        logger.warning(
            "Diagnosis agent has NO Phoenix MCP toolset. "
            "Output will be a degenerate guess from the failure_key alone."
        )

    if db is not None:
        from src.agent.tools import extract_categories as _extract_categories_impl

        async def extract_categories(
            failure_key: str, max_categories: int = 5
        ) -> list[dict]:
            """Cluster failed runs under a failure_key into mutually exclusive
            categories using an LLM call.

            Call this AFTER inspecting spans + annotations via Phoenix MCP.
            Pass the ``failure_key`` exactly as it appears in the user message.

            Args:
                failure_key: The cluster identifier from the user message
                    (e.g. ``"missing_required_tool::lookup_order"``).
                max_categories: Cap on the number of categories returned
                    (3-5 is the useful range; 5 is the hard ceiling).

            Returns:
                A list of dicts of shape
                ``{"category": str, "count": int, "example_run_ids": [str]}``.
            """
            return await _extract_categories_impl(
                failure_key=failure_key,
                max_categories=max_categories,
                db=db,
            )

        tools.append(extract_categories)
        logger.debug("Diagnosis agent: extract_categories tool wired")

    return Agent(
        name=DIAGNOSIS_AGENT_NAME,
        model=get_settings().gemini_model,
        instruction=DIAGNOSIS_INSTRUCTION,
        planner=BuiltInPlanner(
            thinking_config=types.ThinkingConfig(thinking_budget=128),
        ),
        tools=tools,
    )


# Alias kept for callers that prefer the ``build_*`` naming used elsewhere
# in the codebase (matches ``build_phoenix_mcp_toolset``).
build_diagnosis_agent = create_diagnosis_agent


_JSON_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json_block(text: str) -> str | None:
    """Pull the first ``{...}`` JSON object out of free-form model output."""
    if not text:
        return None
    match = _JSON_OBJECT_PATTERN.search(text)
    return match.group(0) if match else None


def _fallback_result(trigger: ImprovementTrigger, reason: str) -> dict:
    """Construct a minimal diagnosis dict when the agent path can't deliver.

    Keeps the UI's expected shape so the page doesn't crash on missing keys.
    """
    return {
        "failure_pattern": trigger.failure_key,
        "root_cause": f"Diagnosis agent could not produce structured output: {reason}",
        "evidence_summary": "(none — fell back to placeholder)",
        "evidence": [],
        "confidence": 0.0,
        "suggested_fix": "Manual review required",
        "mcp_tools_used": [],
        "mcp_status": "agent_fallback",
    }


async def run_diagnosis_agent(
    trigger: ImprovementTrigger,
    mcp_toolset: Any | None,
    *,
    session_id: str | None = None,
    phoenixloop_cycle_id: str | None = None,
    example_trace_ids: list[str] | None = None,
    db: "aiosqlite.Connection | None" = None,
) -> dict:
    """Invoke the diagnosis sub-agent end-to-end and return the diagnosis dict.

    Behaviour:
    - Builds the agent with the lifespan-managed MCP toolset.
    - Sends a user message that lays out the failure context (failure_key,
      occurrence_count, sample run IDs) so the agent has somewhere to start
      its MCP queries.
    - Streams events to collect tool spans + final response.
    - Parses the final text as JSON matching ``DiagnosisAgentResult``.
    - On parse / validation failure, returns a fallback dict — the calling
      endpoint can still try the service-side path.

    Returns a dict shaped like the existing ``trigger.diagnosis_json`` plus
    new ``mcp_tools_used`` and ``evidence_summary`` fields.
    """
    if mcp_toolset is None:
        logger.info(
            "Diagnosis agent skipped — no Phoenix MCP toolset available "
            "(falling back to service-side diagnose)"
        )
        return _fallback_result(trigger, "MCP toolset unavailable")

    agent = create_diagnosis_agent(mcp_toolset, db=db)
    session_service = InMemorySessionService()
    runner = Runner(
        agent=agent,
        app_name=DIAGNOSIS_APP_NAME,
        session_service=session_service,
    )

    sess_id = session_id or f"diag-{uuid.uuid4().hex[:12]}"
    user_id = f"diagnosis-runner-{trigger.improvement_trigger_id}"
    await session_service.create_session(
        app_name=DIAGNOSIS_APP_NAME,
        user_id=user_id,
        session_id=sess_id,
    )

    project_name = get_settings().phoenix_project_name
    # Prefer real Phoenix trace_ids (resolved by the caller from agent_runs);
    # only fall back to the trigger's local agent_run_ids if a caller didn't
    # supply them — those won't actually resolve in Phoenix and the agent
    # will report "no spans found", but the call still completes cleanly.
    sample_ids = (example_trace_ids or trigger.example_run_ids_json or [])[:3]
    id_label = "Phoenix trace_ids" if example_trace_ids else "local agent_run_ids (best-effort)"
    user_message = (
        f"Phoenix project: `{project_name}` "
        f"— pass this exact string as the `projectIdentifier` argument to "
        f"every MCP tool call (get-spans, get-span-annotations, list-traces, "
        f"list-sessions, list-experiments-for-dataset).\n"
        f"Failure cluster: `{trigger.failure_key}`\n"
        f"Occurrences: {trigger.occurrence_count}\n"
        f"Trigger reason: {trigger.trigger_reason.value}\n"
        f"Sample failing {id_label} (pass each as `trace_id` to get-spans, "
        f"together with `projectIdentifier=\"{project_name}\"`): "
        f"{sample_ids}\n\n"
        "Investigate and emit your final JSON diagnosis."
    )

    content = types.Content(role="user", parts=[types.Part(text=user_message)])

    tools_seen: list[str] = []
    final_text_parts: list[str] = []
    started = time.monotonic()

    # P2-8: same ``phoenixloop_cycle_id`` plumbing as the support agent —
    # see ``run_agent_events`` for rationale. Fallback to ``sess_id`` keeps
    # the attribute populated when no orchestrator is in scope.
    cycle_id = phoenixloop_cycle_id or sess_id
    with using_attributes(
        session_id=sess_id,
        user_id=user_id,
        metadata={
            "request_id": str(uuid.uuid4()),
            "improvement_trigger_id": trigger.improvement_trigger_id,
            "failure_key": trigger.failure_key,
            "purpose": "diagnosis_agent",
            "phoenixloop_cycle_id": cycle_id,
        },
    ):
        try:
            events = runner.run_async(
                user_id=user_id,
                session_id=sess_id,
                new_message=content,
            )
            async for event in events:
                for fc in event.get_function_calls() or []:
                    if fc.name:
                        tools_seen.append(fc.name)
                if event.is_final_response() and event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            final_text_parts.append(part.text)
        except Exception as exc:
            logger.error(
                "Diagnosis agent invocation failed for trigger %s: %s",
                trigger.improvement_trigger_id, exc, exc_info=True,
            )
            return _fallback_result(trigger, f"agent crash: {exc.__class__.__name__}")

    elapsed_ms = int((time.monotonic() - started) * 1000)
    final_text = "".join(final_text_parts).strip()

    json_block = _extract_json_block(final_text)
    if json_block is None:
        logger.warning(
            "Diagnosis agent emitted no JSON object (chars=%d, tools=%s)",
            len(final_text), tools_seen,
        )
        return _fallback_result(trigger, "no JSON in agent output")

    try:
        parsed_dict = json.loads(json_block)
    except json.JSONDecodeError as exc:
        logger.warning("Diagnosis agent JSON decode failed: %s", exc)
        return _fallback_result(trigger, f"JSON decode: {exc.msg}")

    try:
        result = DiagnosisAgentResult.model_validate(parsed_dict)
    except ValidationError as exc:
        logger.warning("Diagnosis agent validation failed: %s", exc.errors())
        return _fallback_result(
            trigger,
            f"schema validation: {len(exc.errors())} error(s)",
        )

    logger.info(
        "Diagnosis agent complete: trigger=%s confidence=%.2f tools=%s elapsed=%dms",
        trigger.improvement_trigger_id,
        result.confidence,
        tools_seen,
        elapsed_ms,
    )

    # Merge agent-observed tools with any the model self-reported. Dedupe but
    # preserve insertion order so the UI shows them chronologically.
    merged_tools: list[str] = []
    for name in (*tools_seen, *result.mcp_tools_used):
        if name not in merged_tools:
            merged_tools.append(name)

    return {
        "failure_pattern": result.failure_pattern,
        "root_cause": result.root_cause,
        "evidence_summary": result.evidence_summary,
        # ``evidence`` retained for backwards compat with the legacy
        # service-side diagnosis shape — UI iterates over it.
        "evidence": [result.evidence_summary] if result.evidence_summary else [],
        "confidence": result.confidence,
        "suggested_fix": result.suggested_fix,
        "mcp_tools_used": merged_tools,
        "mcp_status": "completed",
        "elapsed_ms": elapsed_ms,
    }
