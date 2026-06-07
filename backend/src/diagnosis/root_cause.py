"""Structured root cause diagnosis using Phoenix evidence and Gemini."""

import json
import logging
from typing import Protocol, runtime_checkable

from google.genai import types
from pydantic import BaseModel

from src.config import get_settings
from src.diagnosis.phoenix_mcp import PromptInfo, TraceRecord
from src.models import ImprovementTrigger
from src.utils.genai_client import make_genai_client
from src.utils.retry import retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol for MCP client (mirrors PhoenixMCPClient in phoenix_mcp.py)
# ---------------------------------------------------------------------------


@runtime_checkable
class MCPReadProtocol(Protocol):
    """Duck-typed interface for the read-side of PhoenixMCPClient."""

    async def read_production_prompt(self) -> PromptInfo | None: ...
    async def query_spans(self, trace_id: str) -> list[TraceRecord]: ...
    async def read_annotations(self, trace_id: str) -> list[dict]: ...


# ---------------------------------------------------------------------------
# Pydantic schemas for structured Gemini output
# ---------------------------------------------------------------------------


class DiagnosisResult(BaseModel):
    """Structured response schema for root cause diagnosis."""

    failure_pattern: str
    root_cause: str
    evidence: list[str]
    confidence: float
    suggested_fix: str


# ---------------------------------------------------------------------------
# Prompt template
# ---------------------------------------------------------------------------

DIAGNOSIS_PROMPT = """You are a diagnostic AI analyzing failure patterns in a customer support agent.

## Failure Pattern
Failure Key: {failure_key}
Trigger Reason: {trigger_reason}
Occurrence Count: {occurrence_count}

## Evidence from Phoenix Traces
{evidence_text}

## Current Production Prompt
{current_prompt}

## Task
Analyze the root cause of this failure pattern. Consider:
1. Is the prompt missing a specific instruction?
2. Is a tool being used incorrectly?
3. Is there an edge case not covered by the current rules?
4. Is the failure due to ambiguous instructions?

Provide your analysis as structured JSON with these fields:
- failure_pattern: description of the repeated failure pattern
- root_cause: the underlying reason for the failure
- evidence: list of specific evidence points from traces
- confidence: 0.0 to 1.0 confidence score
- suggested_fix: what should be changed in the prompt to fix this
"""

# Maximum number of example runs to fetch evidence for
MAX_EVIDENCE_RUNS = 5

# Maximum spans per run to include in evidence
MAX_SPANS_PER_RUN = 3

# Truncation limit for prompt text to avoid token limits
PROMPT_TRUNCATION_LIMIT = 3000


# ---------------------------------------------------------------------------
# Core diagnosis logic
# ---------------------------------------------------------------------------


@retry(max_attempts=3, backoff_base=1.0, retryable_exceptions=(Exception,))
async def _call_gemini_diagnosis(prompt_text: str) -> DiagnosisResult:
    """Call Gemini for structured diagnosis with retry.

    Args:
        prompt_text: Fully formatted diagnosis prompt.

    Returns:
        Parsed DiagnosisResult from Gemini response.
    """
    settings = get_settings()
    client = make_genai_client()
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=DiagnosisResult,
        ),
    )
    return DiagnosisResult.model_validate_json(response.text)


def _format_trace_record(record: TraceRecord) -> dict:
    """Convert a TraceRecord to a serialisable dict for the evidence prompt.

    Args:
        record: A single trace/span record from Phoenix.

    Returns:
        Compact dict suitable for embedding in the diagnosis prompt.
    """
    return {
        "span_id": record.span_id,
        "name": record.name,
        "status": record.status_code,
        "latency_ms": record.latency_ms,
    }


async def _gather_trace_evidence(
    trigger: ImprovementTrigger,
    mcp_client: MCPReadProtocol,
) -> str:
    """Gather evidence from Phoenix traces for the failing runs.

    Args:
        trigger: The improvement trigger with example run IDs.
        mcp_client: MCP client for querying spans.

    Returns:
        Formatted evidence text string.
    """
    evidence_parts: list[str] = []

    for run_id in trigger.example_run_ids_json[:MAX_EVIDENCE_RUNS]:
        try:
            spans = await mcp_client.query_spans(run_id)
            if spans:
                truncated = [
                    _format_trace_record(s) for s in spans[:MAX_SPANS_PER_RUN]
                ]
                evidence_parts.append(
                    f"Run {run_id}: {json.dumps(truncated, default=str)}"
                )
        except Exception as exc:
            logger.warning(
                "Failed to query spans for run %s: %s", run_id, exc
            )

    return "\n\n".join(evidence_parts) if evidence_parts else "(no trace evidence available)"


async def diagnose(
    trigger: ImprovementTrigger,
    mcp_client: MCPReadProtocol,
    current_prompt: str | None = None,
) -> dict:
    """Perform root cause diagnosis using Phoenix evidence and Gemini.

    Gathers trace evidence from Phoenix, reads the current production prompt,
    then calls Gemini to produce a structured diagnosis of the failure pattern.

    Args:
        trigger: The improvement trigger with failure details.
        mcp_client: PhoenixMCPClient for reading traces and prompts.
        current_prompt: Pre-resolved production prompt text. When provided,
            skips the Phoenix prompt lookup — preferred path post-spec-0
            where the local DB is the source of truth.

    Returns:
        Structured diagnosis dict with keys: failure_pattern, root_cause,
        evidence, confidence, suggested_fix, mcp_status.
    """
    # 1. Gather evidence from Phoenix traces
    evidence_text = await _gather_trace_evidence(trigger, mcp_client)

    # 2. Resolve production prompt (caller-supplied if available, MCP fallback)
    if current_prompt is None:
        prompt_info = await mcp_client.read_production_prompt()
        current_prompt = prompt_info.template if prompt_info else None
    if not current_prompt:
        current_prompt = "(unavailable)"

    # 3. Build the diagnosis prompt
    diagnosis_prompt = DIAGNOSIS_PROMPT.format(
        failure_key=trigger.failure_key,
        trigger_reason=trigger.trigger_reason.value,
        occurrence_count=trigger.occurrence_count,
        evidence_text=evidence_text,
        current_prompt=current_prompt[:PROMPT_TRUNCATION_LIMIT],
    )

    # 4. Call Gemini for structured diagnosis
    try:
        result = await _call_gemini_diagnosis(diagnosis_prompt)
        diagnosis = result.model_dump()
        diagnosis["mcp_status"] = "completed"

        logger.info(
            "Diagnosis complete for %s: confidence=%.2f",
            trigger.failure_key,
            result.confidence,
        )
        return diagnosis

    except Exception as exc:
        logger.error(
            "Diagnosis failed for %s: %s",
            trigger.failure_key,
            exc,
            exc_info=True,
        )
        return {
            "failure_pattern": trigger.failure_key,
            "root_cause": f"Diagnosis failed: {exc}",
            "evidence": [],
            "confidence": 0.0,
            "suggested_fix": "Manual review required",
            "mcp_status": "failed",
        }
