"""Combined Phoenix tool evaluator — evaluates tool selection, invocation,
and response handling in a single Gemini call.

Replaces three separate evaluators that each made their own Gemini request.
"""

import json
import logging
from typing import Literal

from google.genai import types
from pydantic import BaseModel, Field

from src.config import get_settings
from src.evaluation import EvalOutput
from src.evaluation.json_repair import LLMJsonParseError, parse_llm_json
from src.models import AgentRun, SupportTicket
from src.utils.genai_client import make_genai_client
from src.utils.retry import retry_on_rate_limit

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 0.7

TOOL_EVAL_NAMES: tuple[str, ...] = (
    "tool_selection",
    "tool_invocation",
    "tool_response_handling",
)

AVAILABLE_TOOLS = [
    {
        "name": "search_policy",
        "description": (
            "Search Helios policy documents by query and category — "
            "returns matching paragraphs and the source filename."
        ),
    },
    {
        "name": "get_customer_context",
        "description": (
            "Return the customer profile, subscription, computed "
            "entitlements (incl. refund_eligible + reason), and recent "
            "ticket history in a single call."
        ),
    },
    {
        "name": "retrieve_similar_resolutions",
        "description": (
            "Fetch up to 3 prior successfully-resolved tickets from the "
            "'successful-resolutions' Phoenix dataset, scoped to the given "
            "category. Used as in-context exemplars before drafting."
        ),
    },
    {
        "name": "create_escalation",
        "description": "Escalate a ticket to a specialized team.",
    },
]


class ToolEvalVerdict(BaseModel):
    """Single tool-evaluator's structured verdict."""

    label: Literal["pass", "fail"]
    score: float = Field(ge=0.0, le=1.0)
    explanation: str = Field(min_length=1, max_length=2000)


class CombinedToolEvalResult(BaseModel):
    """Schema returned by Gemini for the combined tool-eval call."""

    tool_selection: ToolEvalVerdict
    tool_invocation: ToolEvalVerdict
    tool_response_handling: ToolEvalVerdict


EVAL_PROMPT_TEMPLATE = """\
You are a strict evaluator for the tool-use behavior of a Helios \
customer-support AI agent. You must return ONE JSON object containing three \
independent verdicts. Do NOT wrap the JSON in markdown fences. Do NOT include \
any text before or after the JSON.

# Input

## Ticket
- Category: {ticket_category}
- Customer ID: {ticket_customer_id}
- Ticket ID: {ticket_id}
- Body: {ticket_body}

## Available Tools
{tools_description}

## Tool Calls (with inputs, outputs, and status)
{tool_calls_detail}

## Agent's Final Response
{agent_response}

# Evaluation Criteria

For each of the three criteria, produce: label ("pass" or "fail"), score \
(0.0-1.0, where 1.0 is best), and a one-paragraph explanation citing specific \
tool calls. Label is "pass" if and only if score >= {pass_threshold}.

## 1. tool_selection
Did the agent choose the right tools for this query? Were any necessary tools \
omitted? Were any unnecessary tools called? If no tools were called at all, \
judge whether that omission was appropriate (e.g., a pure FAQ might need none, \
but a refund request always needs get_customer_context for the entitlements).

## 2. tool_invocation
Were tool arguments correct, complete, and derived from the ticket? Were any \
argument values hallucinated rather than taken from context? \
If no tools were called, return pass with explanation \
"no tool calls to evaluate" and score 1.0.

## 3. tool_response_handling
Did the agent correctly interpret each tool's output? Did it follow tool \
recommendations (e.g., deny refund when eligibility tool returned false)? Did \
it incorporate relevant fields into the final response, or ignore/contradict \
them? Did it fabricate facts not present in any tool output? \
If no tools were called, return pass with explanation \
"no tool calls to evaluate" and score 1.0.

# Output Format

Return EXACTLY this JSON shape, with all three keys present:

{{
  "tool_selection":         {{"label": "pass"|"fail", "score": 0.0-1.0, "explanation": "..."}},
  "tool_invocation":        {{"label": "pass"|"fail", "score": 0.0-1.0, "explanation": "..."}},
  "tool_response_handling": {{"label": "pass"|"fail", "score": 0.0-1.0, "explanation": "..."}}
}}
"""


class CombinedToolEvals:
    """Run all three Phoenix tool evaluators as a single Gemini call."""

    name = "combined_tool_evals"
    output_names: tuple[str, ...] = TOOL_EVAL_NAMES

    async def evaluate(
        self, agent_run: AgentRun, ticket: SupportTicket
    ) -> list[EvalOutput]:
        """Run all three tool evaluators and return one EvalOutput per evaluator."""
        prompt = self._build_prompt(agent_run, ticket)

        try:
            verdicts = await self._call_gemini(prompt)
        except Exception as exc:
            logger.error("CombinedToolEvals failed: %s", exc, exc_info=True)
            return [
                _make_error_output(
                    name=eval_name,
                    explanation=f"Evaluator failed: {exc}",
                )
                for eval_name in TOOL_EVAL_NAMES
            ]

        outputs: list[EvalOutput] = []
        for eval_name in TOOL_EVAL_NAMES:
            verdict: ToolEvalVerdict = getattr(verdicts, eval_name)
            outputs.append(_verdict_to_output(eval_name, verdict))
        return outputs

    def _build_prompt(
        self, agent_run: AgentRun, ticket: SupportTicket
    ) -> str:
        tools_desc = "\n".join(
            f"- {t['name']}: {t['description']}" for t in AVAILABLE_TOOLS
        )
        return EVAL_PROMPT_TEMPLATE.format(
            ticket_category=ticket.category.value,
            ticket_customer_id=ticket.customer_id or "(none)",
            ticket_id=ticket.ticket_id,
            ticket_body=ticket.body,
            tools_description=tools_desc,
            tool_calls_detail=_format_tool_calls(agent_run),
            agent_response=json.dumps(agent_run.response_json, indent=2),
            pass_threshold=PASS_THRESHOLD,
        )

    @retry_on_rate_limit(max_attempts=3)
    async def _call_gemini(self, prompt: str) -> CombinedToolEvalResult:
        """Invoke Gemini asynchronously so it runs in parallel with the LLM judges."""
        settings = get_settings()
        client = make_genai_client()
        response = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=CombinedToolEvalResult,
            ),
        )
        try:
            return parse_llm_json(response.text or "", CombinedToolEvalResult)
        except LLMJsonParseError as exc:
            logger.warning("LLM JSON repair failed: %s", exc)
            raise


def _format_tool_calls(agent_run: AgentRun) -> str:
    if not agent_run.tool_calls_json:
        return "(no tools called)"
    lines: list[str] = []
    for idx, tool_call in enumerate(agent_run.tool_calls_json, start=1):
        lines.append(f"### Call {idx}: {tool_call.tool_name}")
        lines.append(f"Input: {json.dumps(tool_call.input, indent=2)}")
        lines.append(f"Output: {json.dumps(tool_call.output, indent=2)}")
        lines.append(f"Status: {tool_call.status}")
        lines.append("")
    return "\n".join(lines)


def _verdict_to_output(name: str, verdict: ToolEvalVerdict) -> EvalOutput:
    if verdict.label == "pass":
        return EvalOutput(
            evaluator_name=name,
            eval_type="phoenix_tool_eval",
            score=verdict.score,
            outcome="pass",
            explanation=verdict.explanation,
            annotation_level="span",
        )
    import hashlib
    summary = f"{name}: {verdict.explanation[:100]}"
    failure_key = hashlib.sha256(
        (name + "|" + summary).encode()
    ).hexdigest()[:12]
    return EvalOutput(
        evaluator_name=name,
        eval_type="phoenix_tool_eval",
        score=verdict.score,
        outcome="fail",
        explanation=verdict.explanation,
        annotation_level="span",
        failure_key=failure_key,
        failure_summary=summary,
    )


def _make_error_output(name: str, explanation: str) -> EvalOutput:
    import hashlib
    summary = f"{name}: evaluation error"
    failure_key = hashlib.sha256(
        (name + "|" + summary).encode()
    ).hexdigest()[:12]
    return EvalOutput(
        evaluator_name=name,
        eval_type="phoenix_tool_eval",
        score=0.0,
        outcome="error",
        explanation=explanation,
        annotation_level="span",
        failure_key=failure_key,
        failure_summary=summary,
    )
