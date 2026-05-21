"""Phoenix annotation writer for eval results."""

import logging
from typing import List, Optional

from phoenix.client import Client
from phoenix.client.resources.spans import SpanAnnotationData

logger = logging.getLogger(__name__)

# All 14 annotation names (one per evaluator).
ANNOTATION_NAMES: List[str] = [
    # Code evaluators
    "schema_validity",
    "tool_sequence",
    "refund_guard",
    "privacy_guard",
    "escalation_guard",
    "citation_presence",
    "latency_budget",
    # LLM judges
    "groundedness",
    "policy_compliance",
    "resolution_correctness",
    "safety_privacy",
    # Phoenix tool evaluators
    "tool_selection",
    "tool_invocation",
    "tool_response_handling",
]


def write_span_annotation(
    client: Optional[Client],
    span_id: str,
    annotation_name: str,
    label: str,
    score: float,
    explanation: str,
) -> None:
    """Write a span-level annotation to Phoenix.

    Uses ``client.spans.log_span_annotations`` which is the canonical
    Python SDK method (verified via context7).

    Args:
        client: Phoenix client instance.
        span_id: The OpenTelemetry hex span ID to annotate.
        annotation_name: Name of the annotation (should match one of
            ``ANNOTATION_NAMES``).
        label: ``"pass"`` or ``"fail"``.
        score: Numeric score (1.0 for pass, 0.0 for fail).
        explanation: Human-readable explanation of the eval result.
    """
    if client is None:
        logger.debug(
            "No Phoenix client, skipping span annotation for %s", annotation_name
        )
        return

    annotation = SpanAnnotationData(
        name=annotation_name,
        span_id=span_id,
        annotator_kind="LLM",
        result={
            "label": label,
            "score": score,
            "explanation": explanation,
        },
    )

    try:
        client.spans.log_span_annotations(
            span_annotations=[annotation],
            sync=False,
        )
        logger.debug(
            "Wrote span annotation %s on span %s: %s",
            annotation_name,
            span_id,
            label,
        )
    except Exception as exc:
        logger.warning("Failed to write span annotation %s: %s", annotation_name, exc)


def write_session_annotation(
    client: Optional[Client],
    session_root_span_id: str,
    annotation_name: str,
    label: str,
    score: float,
    explanation: str,
) -> None:
    """Write a session-level annotation to Phoenix.

    Phoenix does not expose a dedicated session-annotation API in the
    Python SDK.  Session-level annotations are recorded as span
    annotations on the *root span* of the session, with an extra
    metadata field (``annotation_level: session``) so downstream
    consumers can distinguish them from ordinary span annotations.

    Args:
        client: Phoenix client instance.
        session_root_span_id: The OpenTelemetry hex span ID of the
            session's root span.
        annotation_name: Name of the annotation (should match one of
            ``ANNOTATION_NAMES``).
        label: ``"pass"`` or ``"fail"``.
        score: Numeric score (1.0 for pass, 0.0 for fail).
        explanation: Human-readable explanation of the eval result.
    """
    if client is None:
        logger.debug(
            "No Phoenix client, skipping session annotation for %s",
            annotation_name,
        )
        return

    annotation = SpanAnnotationData(
        name=annotation_name,
        span_id=session_root_span_id,
        annotator_kind="LLM",
        result={
            "label": label,
            "score": score,
            "explanation": explanation,
        },
        metadata={"annotation_level": "session"},
    )

    try:
        client.spans.log_span_annotations(
            span_annotations=[annotation],
            sync=False,
        )
        logger.debug(
            "Wrote session annotation %s on root span %s: %s",
            annotation_name,
            session_root_span_id,
            label,
        )
    except Exception as exc:
        logger.warning(
            "Failed to write session annotation %s: %s", annotation_name, exc
        )


def write_annotations_batch(
    client: Optional[Client],
    annotations: List[SpanAnnotationData],
) -> None:
    """Write multiple span annotations to Phoenix in a single call.

    This is more efficient than calling ``write_span_annotation`` in a
    loop when several evaluators produce results for the same turn.

    Args:
        client: Phoenix client instance.
        annotations: Pre-built ``SpanAnnotationData`` objects.
    """
    if client is None:
        logger.debug("No Phoenix client, skipping batch annotation write")
        return

    if not annotations:
        return

    try:
        client.spans.log_span_annotations(
            span_annotations=annotations,
            sync=False,
        )
        logger.debug("Wrote %d annotations in batch", len(annotations))
    except Exception as exc:
        logger.warning("Failed to write annotation batch: %s", exc)
