"""Citation presence evaluator — checks that policy-related responses include citations."""

import logging

from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket, TicketCategory

logger = logging.getLogger(__name__)

# Categories that require citations (policy-related)
CITATION_REQUIRED_CATEGORIES: set[str] = {
    TicketCategory.REFUND.value,
    TicketCategory.BILLING.value,
    TicketCategory.PRIVACY.value,
    TicketCategory.ADMIN_ACCESS.value,
    TicketCategory.OUTAGE_CREDIT.value,
}

# Categories that may not need citations
CITATION_EXEMPT_CATEGORIES: set[str] = {
    TicketCategory.AMBIGUOUS.value,
    TicketCategory.LEGAL.value,
}


class CitationPresenceEvaluator(BaseEvaluator):
    """Check that policy-related responses include citations."""

    @property
    def name(self) -> str:
        return "citation_presence"

    @property
    def eval_type(self) -> str:
        return "code"

    @property
    def annotation_level(self) -> str:
        return "span"

    @property
    def rubric_version(self) -> str:
        return "citation_presence_v1"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Verify citations are present for policy-related categories."""
        category = ticket.category.value if isinstance(ticket.category, TicketCategory) else ticket.category

        # Exempt categories don't need citations
        if category in CITATION_EXEMPT_CATEGORIES:
            return self._make_pass_output(
                f"Category '{category}' is exempt from citation requirement."
            )

        # Non-policy categories don't need citations either
        if category not in CITATION_REQUIRED_CATEGORIES:
            return self._make_pass_output(
                f"Category '{category}' does not require citations."
            )

        # Policy-related category — check for citations
        citations = agent_run.response_json.get("citations", [])
        answer = agent_run.response_json.get("answer", "")

        if not isinstance(citations, list) or len(citations) == 0:
            summary = "retrieval_miss"
            explanation = (
                f"Category '{category}' is policy-related and requires citations, "
                f"but response has no citations."
            )
            logger.warning(
                "Citation presence check failed for run %s: %s",
                agent_run.agent_run_id,
                explanation,
            )
            return self._make_failure_output(
                summary,
                explanation,
                evidence=[
                    f"category={category}",
                    f"response_excerpt={answer[:120] if isinstance(answer, str) else ''}",
                    "citations=[]",
                ],
            )

        return self._make_pass_output(
            f"Response includes {len(citations)} citation(s) for policy-related category '{category}'.",
            evidence=[f"citations={citations}"],
        )
