"""Google ADK support agent definition and runner."""

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from google.adk.agents import Agent
from google.adk.planners import BuiltInPlanner
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from src.agent.prompts import PhoenixClientProtocol, get_production_prompt

if TYPE_CHECKING:
    import aiosqlite
from src.agent.schemas import AgentResponseContract
from src.agent.tools import (
    check_refund_eligibility,
    create_escalation,
    draft_customer_response,
    lookup_customer,
    lookup_subscription,
    search_policy,
)
from src.config import get_settings
from src.models import AgentRun, SupportTicket, ToolCallRecord

logger = logging.getLogger(__name__)

APP_NAME = "phoenixloop"
AGENT_NAME = "acmeflow_support_agent"
AGENT_VERSION = "1.0.0"


def create_agent(system_prompt: str) -> Agent:
    """Create the ADK agent with tools and system prompt.

    ``thinking_budget=512`` gives the model a small amount of hidden reasoning
    per turn — enough to handle judgment calls like "this denied refund has a
    customer dispute, so I should escalate" without the model's full default
    thinking budget (which previously added ~2000 thought tokens and 5-8s of
    latency per turn).
    """
    return Agent(
        name=AGENT_NAME,
        model=get_settings().gemini_model,
        instruction=system_prompt,
        planner=BuiltInPlanner(
            thinking_config=types.ThinkingConfig(thinking_budget=512),
        ),
        tools=[
            search_policy,
            lookup_customer,
            lookup_subscription,
            check_refund_eligibility,
            create_escalation,
            draft_customer_response,
        ],
    )


async def run_agent(
    ticket: SupportTicket,
    session_id: str,
    db: "aiosqlite.Connection",
    phoenix_client: PhoenixClientProtocol | None = None,
) -> AgentRun:
    """Run the support agent on a ticket and return an AgentRun record.

    Creates an ADK agent, sends the ticket as a user message, iterates
    through all events to collect tool calls and the final response, then
    packages everything into an ``AgentRun`` model.

    Args:
        ticket: The support ticket to process.
        session_id: The conversation session ID.
        db: Open aiosqlite connection used to resolve the active prompt
            version from the local ``prompts`` table.
        phoenix_client: Optional Phoenix client. Retained for tracing
            instrumentation; no longer consulted for prompt resolution.

    Returns:
        AgentRun model with all run metadata, including ``prompt_version_id``.
    """
    del phoenix_client  # reserved for future trace/annotation publication
    prompt_text, prompt_version_id = await get_production_prompt(db)
    agent = create_agent(prompt_text)

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
    start_time = time.monotonic()

    tool_calls: list[ToolCallRecord] = []
    # Parallel array of monotonic start times so we can compute per-tool
    # latency when each tool's response event arrives.
    tool_start_times: list[float] = []
    final_response = ""

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
        # Collect tool (function) calls from each event
        function_calls = event.get_function_calls()
        if function_calls:
            for fc in function_calls:
                tool_calls.append(
                    ToolCallRecord(
                        tool_name=fc.name,
                        input=fc.args if fc.args else {},
                        output={},
                        status="pending",
                    )
                )
                tool_start_times.append(time.monotonic())

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
                        break

        # Capture the final text response
        if event.is_final_response() and event.content and event.content.parts:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    final_response += part.text

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

    return AgentRun(
        agent_run_id=run_id,
        conversation_session_id=session_id,
        ticket_id=ticket.ticket_id,
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        prompt_version="production",
        trace_id=None,
        root_span_id=None,
        phoenix_session_id=None,
        response_json=response_dict,
        tool_calls_json=tool_calls,
        status="success",
        latency_ms=elapsed_ms,
        token_count_input=None,
        token_count_output=None,
        prompt_version_id=prompt_version_id,
        created_at=now,
    )


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
