"""Tool sequence evaluator — checks required tools were called per ticket category."""

import logging

from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket, TicketCategory

logger = logging.getLogger(__name__)

# Required tools per ticket category
#
# After the 6→3 tool consolidation, ``get_customer_context`` is the single
# data-gathering tool — it carries refund eligibility, the subscription, and
# the profile. Every category whose answer depends on customer facts now
# requires it. ``create_escalation`` and ``search_policy`` requirements are
# unchanged.
REQUIRED_TOOLS: dict[str, list[str]] = {
    TicketCategory.REFUND.value: ["get_customer_context"],
    TicketCategory.LEGAL.value: ["create_escalation"],
    TicketCategory.OUTAGE_CREDIT.value: ["search_policy"],
    TicketCategory.ADMIN_ACCESS.value: ["get_customer_context"],
}


class ToolSequenceEvaluator(BaseEvaluator):
    """Check that required tools were called for the ticket category."""

    @property
    def name(self) -> str:
        return "tool_sequence"

    @property
    def eval_type(self) -> str:
        return "code"

    @property
    def annotation_level(self) -> str:
        return "span"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Verify required tools were called based on ticket category."""
        category = ticket.category.value if isinstance(ticket.category, TicketCategory) else ticket.category
        required = REQUIRED_TOOLS.get(category, [])

        if not required:
            return self._make_pass_output(
                f"No required tools defined for category '{category}'."
            )

        # Extract tool names from tool_calls_json
        called_tools: set[str] = set()
        for tool_call in agent_run.tool_calls_json:
            if hasattr(tool_call, "tool_name"):
                called_tools.add(tool_call.tool_name)
            elif isinstance(tool_call, dict):
                tool_name = tool_call.get("tool_name", "")
                called_tools.add(tool_name)

        missing = [t for t in required if t not in called_tools]

        if missing:
            summary = "missing_required_tool"
            explanation = (
                f"Category '{category}' requires tools {required}, "
                f"but missing: {missing}. Called: {sorted(called_tools)}"
            )
            logger.warning(
                "Tool sequence check failed for run %s: %s",
                agent_run.agent_run_id,
                explanation,
            )
            return self._make_failure_output(summary, explanation)

        return self._make_pass_output(
            f"All required tools for '{category}' were called: {required}."
        )
