"""Tool invocation evaluator — did the agent call tools with correct arguments?"""

import json
import logging

import google.genai as genai
from google.genai import types

from src.config import get_settings
from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)

EVAL_PROMPT = """You are evaluating whether an AI agent called its tools with correct and complete arguments.

## Customer Query
Category: {category}
Customer ID: {customer_id}
Ticket ID: {ticket_id}
{ticket_body}

## Tool Calls Made by the Agent
{tool_calls_detail}

## Task
Evaluate the quality of the tool invocations:
1. Were the tool arguments correct? (e.g., right customer_id, right category for policy search)
2. Were arguments complete? (no missing required parameters)
3. Were arguments derived from the ticket context? (customer_id matches ticket, category is appropriate)
4. Were there any hallucinated or fabricated argument values not present in the ticket?

Respond with JSON: {{"score": float between 0.0 and 1.0, "outcome": "pass" or "fail", "explanation": "brief reason"}}
Pass threshold: score >= 0.7
"""

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "outcome": {"type": "string", "enum": ["pass", "fail"]},
        "explanation": {"type": "string"},
    },
    "required": ["score", "outcome", "explanation"],
}


def _format_tool_calls(agent_run: AgentRun) -> str:
    """Format tool calls with their inputs for the evaluation prompt."""
    if not agent_run.tool_calls_json:
        return "(no tools called)"

    lines: list[str] = []
    for idx, tc in enumerate(agent_run.tool_calls_json, start=1):
        lines.append(f"### Call {idx}: {tc.tool_name}")
        lines.append(f"Input: {json.dumps(tc.input, indent=2)}")
        lines.append(f"Status: {tc.status}")
        lines.append("")
    return "\n".join(lines)


class ToolInvocationEvaluator(BaseEvaluator):
    """Evaluate whether the agent called tools with correct arguments."""

    @property
    def name(self) -> str:
        return "tool_invocation"

    @property
    def eval_type(self) -> str:
        return "phoenix_tool_eval"

    @property
    def annotation_level(self) -> str:
        return "span"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Judge whether tool arguments were correct and complete."""
        if not agent_run.tool_calls_json:
            return self._make_pass_output(
                "No tool calls to evaluate for argument correctness."
            )

        tool_calls_detail = _format_tool_calls(agent_run)

        prompt = EVAL_PROMPT.format(
            category=ticket.category.value,
            customer_id=ticket.customer_id,
            ticket_id=ticket.ticket_id,
            ticket_body=ticket.body,
            tool_calls_detail=tool_calls_detail,
        )

        try:
            settings = get_settings()
            client = genai.Client(api_key=settings.google_api_key)
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_json_schema=_RESPONSE_SCHEMA,
                ),
            )
            result = json.loads(response.text)

            if result["outcome"] == "fail":
                return self._make_failure_output(
                    summary=f"tool_invocation: {result['explanation'][:100]}",
                    explanation=result["explanation"],
                )
            return self._make_pass_output(explanation=result["explanation"])

        except Exception as exc:
            logger.error("ToolInvocationEvaluator failed: %s", exc, exc_info=True)
            return self._make_failure_output(
                summary="tool_invocation: evaluation error",
                explanation=f"Evaluator failed: {exc}",
            )
