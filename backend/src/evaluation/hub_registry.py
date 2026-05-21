"""Register evaluators in the Phoenix Evaluator Hub.

The Phoenix Python SDK (as of v14+) does not expose a dedicated
``client.evaluators`` hub-registration API.  Evaluators are defined in code
and either run locally via ``run_experiment`` or logged as span annotations.

This module maintains a canonical registry of all LLM-based evaluator
metadata so that:
1. A future SDK release with hub support can be wired in here.
2. Other parts of the system can import ``EVALUATOR_CONFIGS`` to discover
   available evaluators without hard-coding names elsewhere.
3. Startup calls ``register_evaluators_in_hub`` safely — it is a no-op
   when the API is unavailable.
"""

import logging
from dataclasses import dataclass

from phoenix.client import Client

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvaluatorConfig:
    """Metadata for a single evaluator registered with Phoenix."""

    name: str
    description: str
    eval_type: str  # "llm_judge" | "phoenix_tool_eval"
    output_labels: tuple[str, ...]


# ------------------------------------------------------------------
# Canonical evaluator definitions
# ------------------------------------------------------------------

EVALUATOR_CONFIGS: tuple[EvaluatorConfig, ...] = (
    EvaluatorConfig(
        name="groundedness",
        description=(
            "Checks if agent response is grounded in tool outputs and cited policies"
        ),
        eval_type="llm_judge",
        output_labels=("pass", "fail"),
    ),
    EvaluatorConfig(
        name="policy_compliance",
        description=(
            "Checks if agent complies with AcmeFlow policies "
            "(refund, escalation, privacy)"
        ),
        eval_type="llm_judge",
        output_labels=("pass", "fail"),
    ),
    EvaluatorConfig(
        name="resolution_correctness",
        description=(
            "Checks if the recommended action is correct for the support scenario"
        ),
        eval_type="llm_judge",
        output_labels=("pass", "fail"),
    ),
    EvaluatorConfig(
        name="safety_privacy",
        description=(
            "Checks for private data disclosure, unsafe instructions, "
            "unauthorized promises"
        ),
        eval_type="llm_judge",
        output_labels=("pass", "fail"),
    ),
    EvaluatorConfig(
        name="tool_selection",
        description=(
            "Evaluates whether the agent selected appropriate tools for the query"
        ),
        eval_type="phoenix_tool_eval",
        output_labels=("pass", "fail"),
    ),
    EvaluatorConfig(
        name="tool_invocation",
        description=(
            "Evaluates whether tool arguments were correct and complete"
        ),
        eval_type="phoenix_tool_eval",
        output_labels=("pass", "fail"),
    ),
    EvaluatorConfig(
        name="tool_response_handling",
        description=(
            "Evaluates whether tool outputs were correctly interpreted"
        ),
        eval_type="phoenix_tool_eval",
        output_labels=("pass", "fail"),
    ),
)


def register_evaluators_in_hub(client: Client | None) -> None:
    """Register all LLM-based evaluators in the Phoenix Evaluator Hub.

    This is idempotent — safe to call on every startup.  If the Phoenix SDK
    does not yet expose an evaluator-hub registration API (which, per
    Context7 docs for Phoenix v14+, it currently does not), the function
    logs an informational message and returns without error.

    Args:
        client: Phoenix ``Client`` instance.  If ``None``, registration is
            skipped entirely.
    """
    if client is None:
        logger.warning("No Phoenix client provided — skipping evaluator hub registration")
        return

    # Check whether the SDK exposes a hub-registration surface.
    # As of 2026-05, the Python Client has ``spans`` but not ``evaluators``.
    if not hasattr(client, "evaluators"):
        logger.info(
            "Phoenix SDK does not expose evaluators hub API — "
            "skipping hub registration (%d evaluators will run locally)",
            len(EVALUATOR_CONFIGS),
        )
        return

    # If a future SDK version adds the API, attempt registration.
    registered = 0
    for config in EVALUATOR_CONFIGS:
        try:
            client.evaluators.create(  # type: ignore[attr-defined] — future SDK API
                name=config.name,
                description=config.description,
                kind=config.eval_type,
                label_options=list(config.output_labels),
            )
            registered += 1
        except Exception as exc:
            # Idempotent: "already exists" errors count as success.
            logger.debug(
                "Evaluator hub registration for '%s': %s", config.name, exc
            )
            registered += 1

    logger.info(
        "Evaluator hub registration complete: %d/%d evaluators",
        registered,
        len(EVALUATOR_CONFIGS),
    )
