"""Google ADK support agent definition and runner."""

import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from openinference.instrumentation import using_attributes
from opentelemetry import trace as otel_trace

from src.agent.mcp_tools import build_phoenix_mcp_toolset
from src.agent.prompts import PhoenixClientProtocol, get_production_prompt

if TYPE_CHECKING:
    import aiosqlite
from src.agent.schemas import AgentResponseContract
from src.agent.tools import (
    create_escalation,
    get_customer_context,
    retrieve_similar_resolutions,
    search_policy,
)
from src.config import get_settings
from src.models import AgentRun, SupportTicket, ToolCallRecord

logger = logging.getLogger(__name__)

APP_NAME = "phoenixloop"
AGENT_NAME = "helios_support_agent"
AGENT_VERSION = "1.0.0"


def create_agent(
    system_prompt: str,
    *,
    mcp_toolset: Any | None = None,
    enable_mcp_toolset: bool = False,
) -> Agent:
    """Create the ADK agent with tools and system prompt.

    ``thinking_budget=128`` gives the model just enough hidden reasoning to
    make judgment calls (e.g. "this denied refund has a customer dispute, so
    I should escalate") without burning latency on a longer planner trace.
    The consolidated 3-tool surface doesn't need the wider 512-token planner
    we used to ship with — fewer branches to evaluate.

    ``mcp_toolset`` accepts a pre-built, lifespan-owned Phoenix MCP toolset
    (see :func:`build_phoenix_mcp_toolset`). Pass the long-lived instance held
    on ``app.state.phoenix_mcp_toolset`` rather than instantiating per-request
    — ADK's :class:`MCPSessionManager` caches the stdio session inside the
    toolset, so we want exactly one toolset per process.

    ``enable_mcp_toolset`` (legacy) instantiates a fresh toolset inside this
    call. Kept for offline scripts and tests; do NOT use from a per-request
    handler — the stdio teardown clashes with FastAPI's per-request task
    scope.
    """
    tools: list = [
        search_policy,
        get_customer_context,
        retrieve_similar_resolutions,
        create_escalation,
    ]
    if mcp_toolset is not None:
        tools.append(mcp_toolset)
        logger.debug(
            "Phoenix MCP toolset (lifespan-managed) attached to agent "
            "(tool count=%d)",
            len(tools),
        )
    elif enable_mcp_toolset:
        phoenix_mcp_toolset = build_phoenix_mcp_toolset()
        if phoenix_mcp_toolset is not None:
            tools.append(phoenix_mcp_toolset)
            logger.info(
                "Phoenix MCP toolset registered on agent (tool count=%d)",
                len(tools),
            )

    return Agent(
        name=AGENT_NAME,
        model=get_settings().gemini_model,
        instruction=system_prompt,
        planner=BuiltInPlanner(
            thinking_config=types.ThinkingConfig(thinking_budget=128),
        ),
        tools=tools,
    )


async def run_agent_events(
    ticket: SupportTicket,
    session_id: str,
    db: "aiosqlite.Connection",
    phoenix_client: PhoenixClientProtocol | None = None,
    mcp_toolset: Any | None = None,
    *,
    prompt_override: str | None = None,
    prompt_version_label: str = "production",
    gemini_call_purpose: str = "support_agent_response",
) -> AsyncIterator[dict[str, Any]]:
    """Run the agent and stream events as they happen.

    Yields dicts of shape ``{"type": "...", ...}``:

    - ``agent_start``: ``{agent_run_id, session_id}`` at the very beginning.
    - ``tool_call_started``: each function call the model emits, with
      ``index``, ``tool_name``, ``input``.
    - ``tool_call_completed``: matching response event with ``index``,
      ``tool_name``, ``output``, ``status``, ``latency_ms``.
    - ``text_chunk``: ``{text}`` incremental text from the final response.
    - ``agent_done``: ``{agent_run: AgentRun}`` — the final assembled record.

    ``run_agent`` is a thin wrapper that drains this generator.
    """
    _ = phoenix_client  # retained for API parity with callers
    if prompt_override is not None:
        # Experiment / eval path: caller supplies the exact prompt to run with
        # so we can score baseline vs candidate without touching the DB's
        # active version. ``prompt_version_id`` is left None — these runs
        # are not pinned to a stored prompt_versions row.
        prompt_text = prompt_override
        prompt_version_id = None
    else:
        prompt_text, prompt_version_id = await get_production_prompt(db)
    agent = create_agent(prompt_text, mcp_toolset=mcp_toolset)

    request_id = str(uuid.uuid4())
    logger.info(
        "gemini_call_purpose=%s ticket_id=%s session_id=%s",
        gemini_call_purpose,
        ticket.ticket_id,
        session_id,
        extra={
            "gemini_call_purpose": gemini_call_purpose,
            "ticket_id": ticket.ticket_id,
            "session_id": session_id,
        },
    )

    with using_attributes(
        session_id=session_id,
        user_id=ticket.customer_id,
        metadata={
            "request_id": request_id,
            "ticket_id": ticket.ticket_id,
            "category": ticket.category.value,
            "prompt_version_id": prompt_version_id or "fallback",
            "prompt_version_label": prompt_version_label,
            "gemini_call_purpose": gemini_call_purpose,
        },
        tags=["support-agent", ticket.category.value],
    ):
        session_service = InMemorySessionService()
        runner = Runner(
            agent=agent,
            app_name=APP_NAME,
            session_service=session_service,
        )

        # Create a session — provide a deterministic session_id for traceability
        adk_session_id = f"adk-{session_id}"
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=ticket.customer_id,
            session_id=adk_session_id,
        )

        # Build the user message with full ticket context
        user_message = (
            f"Support Ticket #{ticket.ticket_id}\n"
            f"Customer ID: {ticket.customer_id}\n"
            f"Category: {ticket.category.value}\n"
            f"Subject: {ticket.subject}\n\n"
            f"{ticket.body}"
        )

        run_id = str(uuid.uuid4())
        yield {
            "type": "agent_start",
            "agent_run_id": run_id,
            "session_id": session_id,
        }
        start_time = time.monotonic()

        tool_calls: list[ToolCallRecord] = []
        # Parallel array of monotonic start times so we can compute per-tool
        # latency when each tool's response event arrives.
        tool_start_times: list[float] = []
        final_response = ""

        # Span IDs are read lazily on the first event: at that point ADK's
        # root agent span is open and active in the OTel context. Reading
        # before iteration starts returns INVALID_SPAN. Reading after the
        # context exits drops back to the parent (or none). Capturing here
        # gives Phoenix annotations a real span_id to attach to.
        trace_id: str | None = None
        root_span_id: str | None = None

        content = types.Content(
            role="user",
            parts=[types.Part(text=user_message)],
        )

        events = runner.run_async(
            user_id=ticket.customer_id,
            session_id=adk_session_id,
            new_message=content,
        )

        async for event in events:
            if trace_id is None:
                span_ctx = otel_trace.get_current_span().get_span_context()
                if span_ctx.is_valid:
                    trace_id = f"{span_ctx.trace_id:032x}"
                    root_span_id = f"{span_ctx.span_id:016x}"
            # Collect tool (function) calls from each event
            function_calls = event.get_function_calls()
            if function_calls:
                for fc in function_calls:
                    idx = len(tool_calls)
                    tool_calls.append(
                        ToolCallRecord(
                            tool_name=fc.name,
                            input=fc.args if fc.args else {},
                            output={},
                            status="pending",
                        )
                    )
                    tool_start_times.append(time.monotonic())
                    yield {
                        "type": "tool_call_started",
                        "index": idx,
                        "tool_name": fc.name,
                        "input": fc.args if fc.args else {},
                    }

            # Collect tool (function) responses and update matching records
            function_responses = event.get_function_responses()
            if function_responses:
                for fr in function_responses:
                    # Find the matching pending tool call and update it (by index
                    # so we can pair it with its start time)
                    for i in range(len(tool_calls) - 1, -1, -1):
                        tc = tool_calls[i]
                        if tc.tool_name == fr.name and tc.status == "pending":
                            tc.output = fr.response if fr.response else {}
                            tc.status = "success"
                            tc.latency_ms = int(
                                (time.monotonic() - tool_start_times[i]) * 1000
                            )
                            yield {
                                "type": "tool_call_completed",
                                "index": i,
                                "tool_name": tc.tool_name,
                                "output": tc.output,
                                "status": tc.status,
                                "latency_ms": tc.latency_ms,
                            }
                            break

            # Capture the final text response
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text:
                        final_response += part.text
                        yield {"type": "text_chunk", "text": part.text}

        elapsed_ms = int((time.monotonic() - start_time) * 1000)

    # Mark any still-pending tool calls as completed (response may have
    # been processed in a batch or the tool execution was inline)
    for tc in tool_calls:
        if tc.status == "pending":
            tc.status = "success"

    # Try to parse the final response as our structured contract
    response_dict: dict
    try:
        response_contract = AgentResponseContract.model_validate_json(
            final_response,
        )
        response_dict = response_contract.model_dump()
    except Exception:
        # Agent returned free-form text — synthesize the structured envelope
        # from the tool-call history. Falling back to ``citations=[]`` would
        # spuriously fail the citation_presence evaluator on every policy
        # ticket even when the agent did consult policy docs.
        logger.info("Agent response is not structured JSON, using fallback format")
        response_dict = {
            "answer": final_response,
            "citations": _extract_citations(tool_calls),
            "tools_used": [tc.tool_name for tc in tool_calls],
            "escalated": any(
                tc.tool_name == "create_escalation" for tc in tool_calls
            ),
            "escalation_reason": _extract_escalation_reason(tool_calls),
            "confidence": 0.5,
        }

    now = datetime.now(timezone.utc).isoformat()
    agent_run = AgentRun(
        agent_run_id=run_id,
        conversation_session_id=session_id,
        ticket_id=ticket.ticket_id,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        prompt_version=prompt_version_label,
        trace_id=trace_id,
        root_span_id=root_span_id,
        phoenix_session_id=session_id,
        response_json=response_dict,
        tool_calls_json=tool_calls,
        status="success",
        latency_ms=elapsed_ms,
        token_count_input=None,
        token_count_output=None,
        prompt_version_id=prompt_version_id,
        created_at=now,
    )
    yield {"type": "agent_done", "agent_run": agent_run}


async def run_agent(
    ticket: SupportTicket,
    session_id: str,
    db: "aiosqlite.Connection",
    phoenix_client: PhoenixClientProtocol | None = None,
    mcp_toolset: Any | None = None,
    *,
    prompt_override: str | None = None,
    prompt_version_label: str = "production",
    gemini_call_purpose: str = "support_agent_response",
) -> AgentRun:
    """Run the support agent on a ticket and return an AgentRun record.

    Drains :func:`run_agent_events` and returns the final ``AgentRun``.
    Existing callers that don't need streaming use this wrapper.

    Experiment callers pass ``prompt_override`` to bypass the production
    prompt lookup and ``gemini_call_purpose='experiment_baseline'`` (or
    ``'experiment_candidate'``) so the per-purpose token accounting in the
    logs stays accurate.
    """
    async for event in run_agent_events(
        ticket,
        session_id,
        db,
        phoenix_client,
        mcp_toolset=mcp_toolset,
        prompt_override=prompt_override,
        prompt_version_label=prompt_version_label,
        gemini_call_purpose=gemini_call_purpose,
    ):
        if event["type"] == "agent_done":
            return event["agent_run"]
    raise RuntimeError("run_agent_events ended without emitting 'agent_done'")


_POLICY_ID_PATTERN = re.compile(r"POL-[A-Z]+-\d+")


def _extract_citations(tool_calls: list[ToolCallRecord]) -> list[str]:
    """Derive citation strings from any ``search_policy`` tool outputs.

    Falls back to the source filename (e.g. ``refunds.md``) when no explicit
    policy ID is present. Each citation appears at most once.
    """
    citations: list[str] = []
    for tc in tool_calls:
        if tc.tool_name != "search_policy":
            continue
        output = tc.output or {}
        if not output.get("found"):
            continue

        for excerpt in output.get("excerpts", []):
            for policy_id in _POLICY_ID_PATTERN.findall(str(excerpt)):
                if policy_id not in citations:
                    citations.append(policy_id)

        source = output.get("source")
        if isinstance(source, str) and source and source not in citations:
            citations.append(source)
    return citations


def _extract_escalation_reason(tool_calls: list[ToolCallRecord]) -> str | None:
    """Return the ``reason`` argument of the last ``create_escalation`` call, if any."""
    for tc in reversed(tool_calls):
        if tc.tool_name == "create_escalation":
            reason = (tc.input or {}).get("reason")
            if isinstance(reason, str) and reason.strip():
                return reason
            return None
    return None
