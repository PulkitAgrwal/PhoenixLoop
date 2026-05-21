"""Evaluation orchestrator — runs all 14 evaluators on an agent run."""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone

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
from src.evaluation.llm_judges import (
    GroundednessEvaluator,
    PolicyComplianceEvaluator,
    ResolutionCorrectnessEvaluator,
    SafetyPrivacyEvaluator,
)
from src.evaluation.tool_evals import (
    ToolInvocationEvaluator,
    ToolResponseHandlingEvaluator,
    ToolSelectionEvaluator,
)
from src.models import AgentRun, AnnotationLevel, EvalResult, EvalType, SupportTicket
from src.tracing.annotations import write_session_annotation, write_span_annotation

logger = logging.getLogger(__name__)

CODE_EVALUATORS: list[type[BaseEvaluator]] = [
    SchemaValidityEvaluator,
    ToolSequenceEvaluator,
    RefundGuardEvaluator,
    PrivacyGuardEvaluator,
    EscalationGuardEvaluator,
    CitationPresenceEvaluator,
    LatencyBudgetEvaluator,
]

LLM_JUDGES: list[type[BaseEvaluator]] = [
    GroundednessEvaluator,
    PolicyComplianceEvaluator,
    ResolutionCorrectnessEvaluator,
    SafetyPrivacyEvaluator,
]

TOOL_EVALUATORS: list[type[BaseEvaluator]] = [
    ToolSelectionEvaluator,
    ToolInvocationEvaluator,
    ToolResponseHandlingEvaluator,
]


def compute_failure_key(evaluator_name: str, failure_summary: str) -> str:
    """Compute a deterministic 12-char hex key for a failure mode."""
    return hashlib.sha256(
        (evaluator_name + "|" + failure_summary).encode()
    ).hexdigest()[:12]


async def _run_single_eval(
    evaluator: BaseEvaluator,
    agent_run: AgentRun,
    ticket: SupportTicket,
) -> EvalOutput:
    """Run a single evaluator with error handling.

    If the evaluator raises, log a warning and return an EvalOutput with
    outcome ``"error"`` so that one broken evaluator never blocks the rest.
    """
    try:
        return await evaluator.evaluate(agent_run, ticket)
    except Exception as exc:
        logger.warning(
            "Evaluator %s failed: %s", evaluator.name, exc, exc_info=True
        )
        return EvalOutput(
            evaluator_name=evaluator.name,
            eval_type=evaluator.eval_type,
            score=0.0,
            outcome="error",
            explanation=f"Evaluator failed: {exc}",
            annotation_level=evaluator.annotation_level,
        )


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
    if phoenix_client is None:
        return

    label = output.outcome
    score = output.score
    explanation = output.explanation or ""

    if output.annotation_level == "span" and agent_run.root_span_id:
        write_span_annotation(
            phoenix_client,
            agent_run.root_span_id,
            output.evaluator_name,
            label,
            score,
            explanation,
        )
    elif output.annotation_level == "session" and agent_run.root_span_id:
        # Session annotations are written on the root span with metadata
        # (see write_session_annotation's session_root_span_id parameter).
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
    """Run all 14 evaluators on a completed agent run.

    Execution order:
      1. Seven code evaluators (sequential — fast, no API calls).
      2. Four LLM judge evaluators (parallel via ``asyncio.gather``).
      3. Three Phoenix tool evaluators (parallel via ``asyncio.gather``).

    Each evaluator failure is isolated: a failing evaluator produces an
    ``EvalResult`` with ``outcome="error"`` and does not prevent the
    remaining evaluators from running.

    Returns:
        List of ``EvalResult`` models ready for DB insertion by the API layer.
    """
    outputs: list[EvalOutput] = []

    # 1. Code evals — fast, sequential
    for eval_cls in CODE_EVALUATORS:
        evaluator = eval_cls()
        output = await _run_single_eval(evaluator, agent_run, ticket)
        outputs.append(output)

    # 2. LLM judges — parallel (they make Gemini API calls)
    llm_tasks = [
        _run_single_eval(eval_cls(), agent_run, ticket) for eval_cls in LLM_JUDGES
    ]
    llm_outputs = await asyncio.gather(*llm_tasks)
    outputs.extend(llm_outputs)

    # 3. Tool evaluators — parallel (they make Phoenix/LLM calls)
    tool_tasks = [
        _run_single_eval(eval_cls(), agent_run, ticket) for eval_cls in TOOL_EVALUATORS
    ]
    tool_outputs = await asyncio.gather(*tool_tasks)
    outputs.extend(tool_outputs)

    # Convert to EvalResult and write annotations
    results: list[EvalResult] = []
    for output in outputs:
        result = _output_to_eval_result(output, agent_run)
        results.append(result)
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
