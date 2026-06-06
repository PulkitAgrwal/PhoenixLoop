"""Evaluation orchestrator — runs all evaluators on an agent run.

Twelve evaluators run per ticket: seven deterministic code evaluators and two
LLM-backed combined evaluators (one rolling up four judges, one rolling up
three Phoenix tool evaluators). Collapsing the seven LLM-judge / tool-eval
calls into two Gemini requests is what keeps PhoenixLoop under the
free-tier 5-RPM ceiling.
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Protocol

from phoenix.client import Client

from src.evaluation import BaseEvaluator, EvalOutput
from src.evaluation.code_evals import (
    CitationPresenceEvaluator,
    EscalationGuardEvaluator,
    LatencyBudgetEvaluator,
    PrivacyGuardEvaluator,
    RefundGuardEvaluator,
    SchemaValidityEvaluator,
    ToolSequenceEvaluator,
)
from src.evaluation.llm_judges import CombinedLLMJudges
from src.evaluation.tool_evals import CombinedToolEvals
from src.models import AgentRun, AnnotationLevel, EvalResult, EvalType, SupportTicket
from src.tracing.annotations import write_session_annotation, write_span_annotation

logger = logging.getLogger(__name__)


class _CombinedEvaluator(Protocol):
    """Structural interface for combined evaluators (CombinedLLMJudges, CombinedToolEvals)."""

    name: str
    output_names: tuple[str, ...]

    async def evaluate(
        self, agent_run: AgentRun, ticket: SupportTicket
    ) -> list[EvalOutput]: ...


CODE_EVALUATORS: list[type[BaseEvaluator]] = [
    SchemaValidityEvaluator,
    ToolSequenceEvaluator,
    RefundGuardEvaluator,
    PrivacyGuardEvaluator,
    EscalationGuardEvaluator,
    CitationPresenceEvaluator,
    LatencyBudgetEvaluator,
]

# Combined LLM-backed evaluators. Each one makes ONE Gemini call and returns
# multiple EvalOutputs. Keeping these as instance factories (rather than
# importing instances) preserves the symmetry with CODE_EVALUATORS.
COMBINED_EVALUATORS: list[type] = [
    CombinedLLMJudges,
    CombinedToolEvals,
]


def compute_failure_key(evaluator_name: str, failure_summary: str) -> str:
    """Compute a deterministic 12-char hex key for a failure mode."""
    return hashlib.sha256(
        (evaluator_name + "|" + failure_summary).encode()
    ).hexdigest()[:12]


async def _run_code_eval(
    evaluator: BaseEvaluator, agent_run: AgentRun, ticket: SupportTicket
) -> list[EvalOutput]:
    """Run a single code evaluator with error isolation; always returns a list."""
    try:
        result = await evaluator.evaluate(agent_run, ticket)
    except Exception as exc:
        logger.warning(
            "Code evaluator %s failed: %s", evaluator.name, exc, exc_info=True
        )
        return [
            EvalOutput(
                evaluator_name=evaluator.name,
                eval_type=evaluator.eval_type,
                score=0.0,
                outcome="error",
                explanation=f"Evaluator failed: {exc}",
                annotation_level=evaluator.annotation_level,
            )
        ]
    return [result] if isinstance(result, EvalOutput) else list(result)


async def _run_combined_eval(
    evaluator: _CombinedEvaluator,
    agent_run: AgentRun,
    ticket: SupportTicket,
) -> list[EvalOutput]:
    """Run a combined evaluator. Its own ``evaluate`` already produces error
    outputs internally; this wrapper handles the unexpected case where
    ``evaluate`` itself raises (e.g. import-time failure)."""
    try:
        return await evaluator.evaluate(agent_run, ticket)
    except Exception as exc:
        logger.error(
            "Combined evaluator %s crashed: %s", evaluator.name, exc, exc_info=True
        )
        return [
            EvalOutput(
                evaluator_name=output_name,
                eval_type="llm_judge",
                score=0.0,
                outcome="error",
                explanation=f"Combined evaluator crashed: {exc}",
                annotation_level="span",
            )
            for output_name in evaluator.output_names
        ]


def _output_to_eval_result(output: EvalOutput, agent_run: AgentRun) -> EvalResult:
    """Convert an EvalOutput dataclass into a persisted EvalResult model."""
    return EvalResult(
        eval_result_id=str(uuid.uuid4()),
        agent_run_id=agent_run.agent_run_id,
        evaluator_name=output.evaluator_name,
        eval_type=EvalType(output.eval_type),
        score=output.score,
        outcome=output.outcome,
        explanation=output.explanation,
        failure_key=output.failure_key,
        failure_summary=output.failure_summary,
        annotation_level=AnnotationLevel(output.annotation_level),
        span_id=agent_run.root_span_id,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _write_annotation(
    output: EvalOutput,
    agent_run: AgentRun,
    phoenix_client: Client | None,
) -> None:
    """Write a span or session annotation to Phoenix for a single eval output."""
    if phoenix_client is None or not agent_run.root_span_id:
        return

    label = output.outcome
    score = output.score
    explanation = output.explanation or ""

    if output.annotation_level == "span":
        write_span_annotation(
            phoenix_client,
            agent_run.root_span_id,
            output.evaluator_name,
            label,
            score,
            explanation,
        )
    elif output.annotation_level == "session":
        write_session_annotation(
            phoenix_client,
            agent_run.root_span_id,
            output.evaluator_name,
            label,
            score,
            explanation,
        )


async def run_all_evals(
    agent_run: AgentRun,
    ticket: SupportTicket,
    phoenix_client: Client | None = None,
) -> list[EvalResult]:
    """Run all evaluators on a completed agent run.

    Execution shape:
      1. Seven code evaluators in parallel via ``asyncio.gather`` (each is
         microseconds of CPU work, so concurrency is free).
      2. Two combined LLM evaluators in parallel via ``asyncio.gather`` — one
         Gemini call each, producing four + three outputs respectively.

    Total Gemini calls per ticket: 2 (down from 7). The combined evaluators
    catch their own per-call failures and produce error outputs without
    raising, so a single rate-limited request never blocks anything else.

    Returns:
        List of ``EvalResult`` models ready for DB insertion by the API layer.
    """
    code_tasks: list[Awaitable[list[EvalOutput]]] = [
        _run_code_eval(eval_cls(), agent_run, ticket) for eval_cls in CODE_EVALUATORS
    ]
    combined_tasks: list[Awaitable[list[EvalOutput]]] = [
        _run_combined_eval(eval_cls(), agent_run, ticket)
        for eval_cls in COMBINED_EVALUATORS
    ]

    all_results = await asyncio.gather(*code_tasks, *combined_tasks)

    outputs: list[EvalOutput] = [out for batch in all_results for out in batch]

    results: list[EvalResult] = []
    for output in outputs:
        results.append(_output_to_eval_result(output, agent_run))
        _write_annotation(output, agent_run, phoenix_client)

    pass_count = sum(1 for r in results if r.outcome == "pass")
    fail_count = sum(1 for r in results if r.outcome == "fail")
    error_count = sum(1 for r in results if r.outcome == "error")
    logger.info(
        "Eval run complete for %s: %d pass, %d fail, %d error",
        agent_run.agent_run_id,
        pass_count,
        fail_count,
        error_count,
    )

    return results
