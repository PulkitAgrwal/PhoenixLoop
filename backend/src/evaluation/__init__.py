"""Evaluation framework for PhoenixLoop."""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.models import AgentRun, SupportTicket


@dataclass
class EvalOutput:
    """Result of a single evaluator run.

    ``rubric_version`` and ``evidence`` are populated by evaluators (code
    and LLM judges) so they survive into the persisted ``EvalResult`` row
    and give downstream UI / kappa code an audit trail.
    """

    evaluator_name: str
    eval_type: str  # "code", "llm_judge", "phoenix_tool_eval"
    score: float | None  # 1.0 = pass, 0.0 = fail, None = abstain
    outcome: str  # "pass" or "fail"
    explanation: str
    annotation_level: str  # "session" or "span"
    failure_key: str | None = None
    failure_summary: str | None = None
    rubric_version: str | None = None
    evidence: list[str] = field(default_factory=list)
    judge_label: str | None = None  # categorical label for LLM judges


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

    @property
    def rubric_version(self) -> str | None:
        """Per-evaluator rubric identifier.

        Subclasses override with a static string (e.g. ``"schema_validity_v1"``)
        so the eval payload schema records which rule set produced the row.
        ``None`` means the evaluator has not been versioned yet.
        """
        return None

    def _make_failure_output(
        self,
        summary: str,
        explanation: str,
        evidence: list[str] | None = None,
    ) -> EvalOutput:
        """Helper to create a failure EvalOutput with computed failure_key.

        ``evidence`` is a list of short verbatim quotes from the agent
        output that justify the failure — the UI surfaces these so the
        signal is grounded rather than rationalised.
        """
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
            rubric_version=self.rubric_version,
            evidence=list(evidence or []),
        )

    def _make_pass_output(
        self,
        explanation: str,
        evidence: list[str] | None = None,
    ) -> EvalOutput:
        """Helper to create a pass EvalOutput.

        ``evidence`` is optional on pass; most evaluators leave it empty
        because there is no failure to ground. Callers that want to record
        what was checked (e.g. ``CitationPresence``) may pass quotes.
        """
        return EvalOutput(
            evaluator_name=self.name,
            eval_type=self.eval_type,
            score=1.0,
            outcome="pass",
            explanation=explanation,
            annotation_level=self.annotation_level,
            rubric_version=self.rubric_version,
            evidence=list(evidence or []),
        )
