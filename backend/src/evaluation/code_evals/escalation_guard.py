"""Escalation guard evaluator — ensures legal/threatening tickets are escalated."""

import logging
import re

from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket, TicketCategory

logger = logging.getLogger(__name__)

# Keywords in ticket body that signal escalation is required
ESCALATION_KEYWORDS: list[re.Pattern[str]] = [
    re.compile(r"\blawyer\b", re.IGNORECASE),
    re.compile(r"\battorney\b", re.IGNORECASE),
    re.compile(r"\blawsuit\b", re.IGNORECASE),
    re.compile(r"\blegal\s+action\b", re.IGNORECASE),
    re.compile(r"\bsue\b", re.IGNORECASE),
]


class EscalationGuardEvaluator(BaseEvaluator):
    """Check that tickets requiring escalation have create_escalation called."""

    @property
    def name(self) -> str:
        return "escalation_guard"

    @property
    def eval_type(self) -> str:
        return "code"

    @property
    def annotation_level(self) -> str:
        return "span"

    @property
    def rubric_version(self) -> str:
        return "escalation_guard_v1"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Verify escalation was created when required."""
        category = ticket.category.value if isinstance(ticket.category, TicketCategory) else ticket.category
        body = ticket.body or ""

        # Determine if escalation is required
        requires_escalation = False

        if category == TicketCategory.LEGAL.value:
            requires_escalation = True

        if not requires_escalation:
            for pattern in ESCALATION_KEYWORDS:
                if pattern.search(body):
                    requires_escalation = True
                    break

        if not requires_escalation:
            return self._make_pass_output(
                "Ticket does not require escalation based on category or content."
            )

        # Check if create_escalation was called
        escalation_called = False
        for tool_call in agent_run.tool_calls_json:
            tool_name = ""
            if hasattr(tool_call, "tool_name"):
                tool_name = tool_call.tool_name
            elif isinstance(tool_call, dict):
                tool_name = tool_call.get("tool_name", "")

            if tool_name == "create_escalation":
                escalation_called = True
                break

        if not escalation_called:
            summary = "wrong_escalation"
            explanation = (
                f"Ticket category='{category}' or body content requires escalation, "
                f"but create_escalation was not called."
            )
            logger.warning(
                "Escalation guard failed for run %s: %s",
                agent_run.agent_run_id,
                explanation,
            )
            return self._make_failure_output(
                summary,
                explanation,
                evidence=[
                    f"ticket_category={category}",
                    f"ticket_body_excerpt={body[:160]}",
                    "create_escalation_called=false",
                ],
            )

        return self._make_pass_output(
            "Escalation was properly created for ticket requiring escalation."
        )
