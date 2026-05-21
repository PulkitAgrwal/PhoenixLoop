"""Tool selection evaluator — did the agent pick the right tool?"""

import json
import logging

import google.genai as genai
from google.genai import types

from src.config import get_settings
from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)

AVAILABLE_TOOLS = [
    {"name": "search_policy", "description": "Search AcmeFlow policy documents by query and category"},
    {"name": "lookup_customer", "description": "Look up customer profile by customer_id"},
    {"name": "lookup_subscription", "description": "Look up subscription details by customer_id"},
    {"name": "check_refund_eligibility", "description": "Check if a customer is eligible for a refund"},
    {"name": "create_escalation", "description": "Escalate a ticket to a specialized team"},
    {"name": "draft_customer_response", "description": "Draft a structured response to the customer"},
]

EVAL_PROMPT = """You are evaluating whether an AI agent selected the appropriate tools for a customer support query.

## Customer Query
Category: {category}
{ticket_body}

## Available Tools
{tools_description}

## Tools the Agent Selected
{selected_tools}

## Task
Evaluate whether the tool selection was appropriate for this query:
- Were the right tools chosen for this type of request?
- Were any necessary tools omitted?
- Were any unnecessary tools called?

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


class ToolSelectionEvaluator(BaseEvaluator):
    """Evaluate whether the agent selected the right tools for the query."""

    @property
    def name(self) -> str:
        return "tool_selection"

    @property
    def eval_type(self) -> str:
        return "phoenix_tool_eval"

    @property
    def annotation_level(self) -> str:
        return "span"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Judge whether the selected tools match the ticket needs."""
        selected = [tc.tool_name for tc in agent_run.tool_calls_json]
        tools_desc = "\n".join(
            f"- {t['name']}: {t['description']}" for t in AVAILABLE_TOOLS
        )

        prompt = EVAL_PROMPT.format(
            category=ticket.category.value,
            ticket_body=ticket.body,
            tools_description=tools_desc,
            selected_tools=json.dumps(selected) if selected else "(no tools called)",
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
                    summary=f"tool_selection: {result['explanation'][:100]}",
                    explanation=result["explanation"],
                )
            return self._make_pass_output(explanation=result["explanation"])

        except Exception as exc:
            logger.error("ToolSelectionEvaluator failed: %s", exc, exc_info=True)
            return self._make_failure_output(
                summary="tool_selection: evaluation error",
                explanation=f"Evaluator failed: {exc}",
            )
