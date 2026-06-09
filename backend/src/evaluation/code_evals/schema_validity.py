"""Schema validity evaluator — validates agent response against AgentResponseContract."""

import logging

from src.evaluation import BaseEvaluator, EvalOutput
from src.models import AgentRun, SupportTicket

logger = logging.getLogger(__name__)


class SchemaValidityEvaluator(BaseEvaluator):
    """Validate agent_run.response_json against AgentResponseContract fields."""

    @property
    def name(self) -> str:
        return "schema_validity"

    @property
    def eval_type(self) -> str:
        return "code"

    @property
    def annotation_level(self) -> str:
        return "span"

    @property
    def rubric_version(self) -> str:
        return "schema_validity_v1"

    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Check that response_json has all required fields with correct types."""
        response = agent_run.response_json
        errors: list[str] = []

        # Check 'answer' exists and is non-empty string
        if "answer" not in response:
            errors.append("missing field 'answer'")
        elif not isinstance(response["answer"], str):
            errors.append(f"'answer' must be str, got {type(response['answer']).__name__}")
        elif not response["answer"].strip():
            errors.append("'answer' is empty")

        # Check 'citations' is a list
        if "citations" not in response:
            errors.append("missing field 'citations'")
        elif not isinstance(response["citations"], list):
            errors.append(f"'citations' must be list, got {type(response['citations']).__name__}")

        # Check 'tools_used' is a list
        if "tools_used" not in response:
            errors.append("missing field 'tools_used'")
        elif not isinstance(response["tools_used"], list):
            errors.append(f"'tools_used' must be list, got {type(response['tools_used']).__name__}")

        # Check 'escalated' is bool
        if "escalated" not in response:
            errors.append("missing field 'escalated'")
        elif not isinstance(response["escalated"], bool):
            errors.append(f"'escalated' must be bool, got {type(response['escalated']).__name__}")

        # Check 'confidence' is float 0-1
        if "confidence" not in response:
            errors.append("missing field 'confidence'")
        elif not isinstance(response["confidence"], (int, float)):
            errors.append(f"'confidence' must be float, got {type(response['confidence']).__name__}")
        elif not (0.0 <= float(response["confidence"]) <= 1.0):
            errors.append(f"'confidence' must be 0-1, got {response['confidence']}")

        if errors:
            summary = "malformed_output"
            explanation = f"Schema validation failed: {'; '.join(errors)}"
            logger.warning("Schema validity check failed for run %s: %s", agent_run.agent_run_id, explanation)
            return self._make_failure_output(summary, explanation, evidence=errors)

        return self._make_pass_output("All required fields present with correct types.")
