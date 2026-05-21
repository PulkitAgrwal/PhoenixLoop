"""Tool response handling evaluator — did the agent correctly interpret tool outputs?"""

import json
import logging

import google.genai as genai
from google.genai import types

from src.config import get_settings
from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)

EVAL_PROMPT = """You are evaluating whether an AI agent correctly interpreted and incorporated tool outputs into its final response.

## Customer Query
Category: {category}
{ticket_body}

## Tool Calls and Their Outputs
{tool_calls_detail}

## Agent's Final Response
{agent_response}

## Task
Evaluate how the agent handled the tool outputs:
1. Did the agent correctly interpret the tool output? (e.g., understood eligibility status, policy details)
2. Did it follow the tool's recommendation? (e.g., if refund eligibility returned false, did it deny the refund?)
3. Did it incorporate relevant tool output into its response? (e.g., cited policy details, used customer info)
4. Did it ignore or contradict any tool output?
5. Did it fabricate information not present in tool outputs?

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


def _format_tool_calls_with_outputs(agent_run: AgentRun) -> str:
    """Format tool calls with both inputs and outputs for the evaluation prompt."""
    if not agent_run.tool_calls_json:
        return "(no tools called)"

    lines: list[str] = []
    for idx, tc in enumerate(agent_run.tool_calls_json, start=1):
        lines.append(f"### Call {idx}: {tc.tool_name}")
        lines.append(f"Input: {json.dumps(tc.input, indent=2)}")
        lines.append(f"Output: {json.dumps(tc.output, indent=2)}")
        lines.append(f"Status: {tc.status}")
        lines.append("")
    return "\n".join(lines)


class ToolResponseHandlingEvaluator(BaseEvaluator):
    """Evaluate whether the agent correctly interpreted tool outputs."""

    @property
    def name(self) -> str:
        return "tool_response_handling"

    @property
    def eval_type(self) -> str:
        return "phoenix_tool_eval"

    @property
    def annotation_level(self) -> str:
        return "span"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Judge whether tool outputs were correctly interpreted and used."""
        if not agent_run.tool_calls_json:
            return self._make_pass_output(
                "No tool calls to evaluate for response handling."
            )

        tool_calls_detail = _format_tool_calls_with_outputs(agent_run)
        agent_response = json.dumps(agent_run.response_json, indent=2)

        prompt = EVAL_PROMPT.format(
            category=ticket.category.value,
            ticket_body=ticket.body,
            tool_calls_detail=tool_calls_detail,
            agent_response=agent_response,
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
                    summary=f"tool_response_handling: {result['explanation'][:100]}",
                    explanation=result["explanation"],
                )
            return self._make_pass_output(explanation=result["explanation"])

        except Exception as exc:
            logger.error(
                "ToolResponseHandlingEvaluator failed: %s", exc, exc_info=True
            )
            return self._make_failure_output(
                summary="tool_response_handling: evaluation error",
                explanation=f"Evaluator failed: {exc}",
            )
