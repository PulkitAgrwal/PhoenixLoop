"""Resolution correctness LLM judge evaluator.

Checks whether the action the agent recommended (refund, escalation,
information provided, etc.) was the correct resolution for the support scenario.
"""

import json
import logging

import google.genai as genai
from google.genai import types
from pydantic import BaseModel

from src.config import get_settings
from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 0.7

EVAL_PROMPT_TEMPLATE = """\
You are evaluating whether an AI support agent chose the correct resolution \
for a customer support scenario.

## Ticket Category
{ticket_category}

## Customer Inquiry
{ticket_body}

## Agent's Response
{response_text}

## Tool Call History
{tool_outputs}

## Task
Assess whether the action taken by the agent (refund, escalation, information \
provided, denial, etc.) was the correct resolution for this support scenario.

Consider:
- Was the action type appropriate for the customer's issue?
- Did the agent use the correct tools to gather information before acting?
- Was the resolution complete, or did it leave the customer's issue unresolved?
- Would a competent human support agent have chosen the same resolution?

- 1.0 = Perfectly correct resolution, optimal action taken
- 0.7-0.9 = Correct general direction with minor improvements possible
- 0.4-0.6 = Partially correct but missed key aspects of the issue
- 0.0-0.3 = Wrong resolution, would harm customer experience or company

Pass threshold: score >= {pass_threshold}

Respond with JSON containing score, outcome, and explanation.\
"""


class JudgeVerdict(BaseModel):
    """Structured response schema for Gemini LLM judge."""

    score: float
    outcome: str
    explanation: str


class ResolutionCorrectnessEvaluator(BaseEvaluator):
    """Evaluate whether the agent chose the correct resolution for the scenario."""

    @property
    def name(self) -> str:
        return "resolution_correctness"

    @property
    def eval_type(self) -> str:
        return "llm_judge"

    @property
    def annotation_level(self) -> str:
        return "session"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Call Gemini to judge whether the resolution was correct."""
        response_text = agent_run.response_json.get("answer", "")
        tool_outputs = self._format_tool_outputs(agent_run)

        prompt = EVAL_PROMPT_TEMPLATE.format(
            response_text=response_text,
            tool_outputs=tool_outputs,
            ticket_body=ticket.body,
            ticket_category=ticket.category.value,
            pass_threshold=PASS_THRESHOLD,
        )

        try:
            result = self._call_gemini(prompt)
            score = float(result.score)
            outcome = "pass" if score >= PASS_THRESHOLD else "fail"
            explanation = result.explanation

            if outcome == "fail":
                return self._make_failure_output(
                    summary=f"resolution_correctness: {explanation[:100]}",
                    explanation=explanation,
                )
            return self._make_pass_output(explanation=explanation)

        except Exception as exc:
            logger.error("LLM judge %s failed: %s", self.name, exc, exc_info=True)
            return self._make_failure_output(
                summary=f"{self.name}: evaluation error",
                explanation=f"LLM judge failed: {exc}",
            )

    def _call_gemini(self, prompt: str) -> JudgeVerdict:
        """Invoke Gemini with structured JSON output and return parsed verdict."""
        settings = get_settings()
        client = genai.Client(api_key=settings.google_api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=JudgeVerdict,
            ),
        )
        return JudgeVerdict.model_validate_json(response.text)

    @staticmethod
    def _format_tool_outputs(agent_run: AgentRun) -> str:
        """Format tool call records into a readable string for the prompt."""
        lines: list[str] = []
        for tc in agent_run.tool_calls_json:
            lines.append(f"Tool: {tc.tool_name}")
            lines.append(f"  Input: {json.dumps(tc.input)}")
            lines.append(f"  Output: {json.dumps(tc.output)}")
        return "\n".join(lines) if lines else "(no tool calls)"
