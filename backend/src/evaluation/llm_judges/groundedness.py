"""Groundedness LLM judge evaluator.

Checks whether the agent's response is supported by the tool outputs
and policy documents it cited during the conversation.
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
You are evaluating whether an AI agent's response is grounded in the evidence \
it gathered from tool calls.

## Agent's Response
{response_text}

## Tool Outputs (Evidence)
{tool_outputs}

## Task
Score how well the response is supported by the tool outputs.
- 1.0 = Fully grounded, every claim backed by tool output
- 0.7-0.9 = Mostly grounded with minor unsupported details
- 0.4-0.6 = Partially grounded, some claims unsupported
- 0.0-0.3 = Largely ungrounded, making claims not in evidence

Pass threshold: score >= {pass_threshold}

Respond with JSON containing score, outcome, and explanation.\
"""


class JudgeVerdict(BaseModel):
    """Structured response schema for Gemini LLM judge."""

    score: float
    outcome: str
    explanation: str


class GroundednessEvaluator(BaseEvaluator):
    """Evaluate whether the agent's claims are grounded in tool output evidence."""

    @property
    def name(self) -> str:
        return "groundedness"

    @property
    def eval_type(self) -> str:
        return "llm_judge"

    @property
    def annotation_level(self) -> str:
        return "span"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Call Gemini to judge how well the response is grounded in evidence."""
        response_text = agent_run.response_json.get("answer", "")
        tool_outputs = self._format_tool_outputs(agent_run)

        prompt = EVAL_PROMPT_TEMPLATE.format(
            response_text=response_text,
            tool_outputs=tool_outputs,
            pass_threshold=PASS_THRESHOLD,
        )

        try:
            result = self._call_gemini(prompt)
            score = float(result.score)
            outcome = "pass" if score >= PASS_THRESHOLD else "fail"
            explanation = result.explanation

            if outcome == "fail":
                return self._make_failure_output(
                    summary=f"groundedness: {explanation[:100]}",
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
