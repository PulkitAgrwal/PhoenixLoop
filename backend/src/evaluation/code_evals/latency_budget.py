"""Latency budget evaluator — checks agent response time against configured threshold."""

import logging

from src.config import get_settings
from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)


class LatencyBudgetEvaluator(BaseEvaluator):
    """Check that agent_run.latency_ms is within the configured latency budget."""

    @property
    def name(self) -> str:
        return "latency_budget"

    @property
    def eval_type(self) -> str:
        return "code"

    @property
    def annotation_level(self) -> str:
        return "span"

    @property
    def rubric_version(self) -> str:
        return "latency_budget_v1"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Verify latency is within budget."""
        settings = get_settings()
        budget_ms = settings.latency_budget_ms
        actual_ms = agent_run.latency_ms

        if actual_ms is None:
            return self._make_pass_output(
                "No latency recorded for this run; skipping budget check."
            )

        if actual_ms > budget_ms:
            summary = "latency_regression"
            explanation = (
                f"Latency {actual_ms}ms exceeds budget of {budget_ms}ms "
                f"(over by {actual_ms - budget_ms}ms)."
            )
            logger.warning(
                "Latency budget exceeded for run %s: %s",
                agent_run.agent_run_id,
                explanation,
            )
            return self._make_failure_output(
                summary,
                explanation,
                evidence=[
                    f"observed_latency_ms={actual_ms}",
                    f"budget_ms={budget_ms}",
                ],
            )

        return self._make_pass_output(
            f"Latency {actual_ms}ms is within budget of {budget_ms}ms."
        )
