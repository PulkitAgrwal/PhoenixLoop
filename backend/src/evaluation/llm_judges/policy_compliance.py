"""Policy compliance LLM judge evaluator.

Checks whether the agent's response complies with AcmeFlow support policies,
including refund windows, escalation triggers, and privacy rules.
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
You are evaluating whether an AI support agent's response complies with \
AcmeFlow company policies.

## Ticket Category
{ticket_category}

## Customer Inquiry
{ticket_body}

## Agent's Response
{response_text}

## Tool Call History
{tool_outputs}

## AcmeFlow Policies to Check

### Refund Policy
- Refunds are only valid within a 30-day window from the purchase date.
- The agent must verify eligibility via a tool call before approving a refund.
- If outside the 30-day window, the agent must deny the refund or escalate.

### Escalation Policy
- Legal threats, lawsuits, or regulatory complaints must be escalated immediately.
- Security incidents (data breach, unauthorized access) must be escalated immediately.
- Requests the agent cannot handle must be escalated, never guessed at.

### Privacy Policy
- Customer personal data (email, phone, address, payment details) must not be \
disclosed to other parties.
- The agent must not repeat sensitive data back unnecessarily.
- Data export requests must go through the proper data-export tool.

## Task
Evaluate whether the agent's response follows all applicable policies for the \
"{ticket_category}" category. Consider only the policies relevant to the \
ticket category.

- 1.0 = Fully compliant with all applicable policies
- 0.7-0.9 = Mostly compliant with minor deviations
- 0.4-0.6 = Partially compliant, some policy violations
- 0.0-0.3 = Serious policy violations

Pass threshold: score >= {pass_threshold}

Respond with JSON containing score, outcome, and explanation.\
"""


class JudgeVerdict(BaseModel):
    """Structured response schema for Gemini LLM judge."""

    score: float
    outcome: str
    explanation: str


class PolicyComplianceEvaluator(BaseEvaluator):
    """Evaluate whether the agent's response complies with AcmeFlow policies."""

    @property
    def name(self) -> str:
        return "policy_compliance"

    @property
    def eval_type(self) -> str:
        return "llm_judge"

    @property
    def annotation_level(self) -> str:
        return "session"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Call Gemini to judge policy compliance of the agent's response."""
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
                    summary=f"policy_compliance: {explanation[:100]}",
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
