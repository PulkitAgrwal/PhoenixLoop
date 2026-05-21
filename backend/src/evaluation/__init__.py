"""Evaluation framework for PhoenixLoop."""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.models import AgentRun, SupportTicket


@dataclass
class EvalOutput:
    """Result of a single evaluator run."""

    evaluator_name: str
    eval_type: str  # "code", "llm_judge", "phoenix_tool_eval"
    score: float  # 1.0 = pass, 0.0 = fail, or continuous 0-1
    outcome: str  # "pass" or "fail"
    explanation: str
    annotation_level: str  # "session" or "span"
    failure_key: str | None = None
    failure_summary: str | None = None


class BaseEvaluator(ABC):
    """Abstract base class for all evaluators."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique evaluator name."""

    @property
    @abstractmethod
    def eval_type(self) -> str:
        """Evaluator type: 'code', 'llm_judge', or 'phoenix_tool_eval'."""

    @property
    @abstractmethod
    def annotation_level(self) -> str:
        """Annotation level: 'session' or 'span'."""

    @abstractmethod
    async def evaluate(self, agent_run: AgentRun, ticket: SupportTicket) -> EvalOutput:
        """Run the evaluation and return result."""

    def _make_failure_output(self, summary: str, explanation: str) -> EvalOutput:
        """Helper to create a failure EvalOutput with computed failure_key."""
        failure_key = hashlib.sha256(
            (self.name + "|" + summary).encode()
        ).hexdigest()[:12]
        return EvalOutput(
            evaluator_name=self.name,
            eval_type=self.eval_type,
            score=0.0,
            outcome="fail",
            explanation=explanation,
            annotation_level=self.annotation_level,
            failure_key=failure_key,
            failure_summary=summary,
        )

    def _make_pass_output(self, explanation: str) -> EvalOutput:
        """Helper to create a pass EvalOutput."""
        return EvalOutput(
            evaluator_name=self.name,
            eval_type=self.eval_type,
            score=1.0,
            outcome="pass",
            explanation=explanation,
            annotation_level=self.annotation_level,
        )
