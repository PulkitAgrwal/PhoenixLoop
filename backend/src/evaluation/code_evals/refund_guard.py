"""Refund guard evaluator — ensures refunds are only promised when properly verified."""

import logging
import re

from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)

# Patterns indicating the agent is approving/granting a refund
REFUND_APPROVAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"refund\s+approved", re.IGNORECASE),
    re.compile(r"process\s+your\s+refund", re.IGNORECASE),
    re.compile(r"refund\s+will\s+be", re.IGNORECASE),
    re.compile(r"we'll\s+refund", re.IGNORECASE),
    re.compile(r"approved\s+your\s+refund", re.IGNORECASE),
]


class RefundGuardEvaluator(BaseEvaluator):
    """Check that refunds are only promised when ``get_customer_context``
    reported ``entitlements.refund_eligible == true``.

    After the 6→3 tool consolidation, refund eligibility no longer ships as
    its own tool — it lives in the ``entitlements`` block returned by
    ``get_customer_context``. This evaluator follows the data, not the old
    tool name.
    """

    @property
    def name(self) -> str:
        return "refund_guard"

    @property
    def eval_type(self) -> str:
        return "code"

    @property
    def annotation_level(self) -> str:
        return "span"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Verify refund promises are backed by an eligibility signal."""
        answer = agent_run.response_json.get("answer", "")

        refund_mentioned = any(pattern.search(answer) for pattern in REFUND_APPROVAL_PATTERNS)

        if not refund_mentioned:
            return self._make_pass_output("No refund approval language detected in response.")

        context_called = False
        refund_eligible = False

        for tool_call in agent_run.tool_calls_json:
            tool_name = ""
            tool_output: dict = {}

            if hasattr(tool_call, "tool_name"):
                tool_name = tool_call.tool_name
                tool_output = tool_call.output if hasattr(tool_call, "output") else {}
            elif isinstance(tool_call, dict):
                tool_name = tool_call.get("tool_name", "")
                tool_output = tool_call.get("output", {})

            if tool_name == "get_customer_context":
                context_called = True
                if isinstance(tool_output, dict):
                    entitlements = tool_output.get("entitlements") or {}
                    if entitlements.get("refund_eligible") is True:
                        refund_eligible = True
                break

        if not context_called:
            summary = "unsupported_claim"
            explanation = (
                "Response promises a refund but get_customer_context was never called."
            )
            logger.warning(
                "Refund guard failed for run %s: %s",
                agent_run.agent_run_id,
                explanation,
            )
            return self._make_failure_output(summary, explanation)

        if not refund_eligible:
            summary = "unsupported_claim"
            explanation = (
                "Response promises a refund but get_customer_context's "
                "entitlements.refund_eligible was not true."
            )
            logger.warning(
                "Refund guard failed for run %s: %s",
                agent_run.agent_run_id,
                explanation,
            )
            return self._make_failure_output(summary, explanation)

        return self._make_pass_output(
            "Refund approval is backed by entitlements.refund_eligible == true."
        )
