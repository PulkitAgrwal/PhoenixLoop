"""Manual-edit experiment creation helper.

The standard experiment flow (``experiments.orchestrator.run_experiment``)
starts from an ``ImprovementTrigger`` produced by the diagnosis pipeline.
The Prompts page exposes a parallel path: a human edits the active prompt
and chooses "Save and run experiment". That flow has no failure trigger,
so we synthesize one (with ``trigger_reason = manual_demo_trigger``) so the
``experiments.improvement_trigger_id`` FK stays populated.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

import aiosqlite

from src.db import (
    get_prompt_version,
    insert_experiment,
    insert_improvement_trigger,
)
from src.models import (
    ExperimentRecord,
    ExperimentStatus,
    ImprovementTrigger,
    TriggerReason,
)

logger = logging.getLogger(__name__)

MANUAL_FAILURE_KEY = "manual"
MANUAL_DATASET_ID = f"regression-{MANUAL_FAILURE_KEY}"


class PromptVersionNotFoundError(ValueError):
    """Raised when baseline or candidate version_id can't be resolved."""


async def create_experiment_from_versions(
    db: aiosqlite.Connection,
    baseline_version_id: str,
    candidate_version_id: str,
) -> ExperimentRecord:
    """Create a pending experiment comparing two prompt versions.

    Used by the Prompts page's "Save and run experiment" flow. Builds a
    synthetic ``ImprovementTrigger`` row to satisfy the NOT NULL FK on
    ``experiments.improvement_trigger_id`` — its ``trigger_reason`` is
    ``manual_demo_trigger`` so dashboards can distinguish manual experiments
    from auto-diagnosed ones.

    The experiment is created in ``pending`` status; downstream orchestration
    picks it up from there.

    Raises:
        PromptVersionNotFoundError: if either version_id does not exist.
    """
    baseline = await get_prompt_version(db, baseline_version_id)
    if baseline is None:
        raise PromptVersionNotFoundError(
            f"baseline prompt version not found: {baseline_version_id}"
        )
    candidate = await get_prompt_version(db, candidate_version_id)
    if candidate is None:
        raise PromptVersionNotFoundError(
            f"candidate prompt version not found: {candidate_version_id}"
        )

    now = datetime.now(timezone.utc).isoformat()

    trigger = ImprovementTrigger(
        improvement_trigger_id=str(uuid.uuid4()),
        failure_key=MANUAL_FAILURE_KEY,
        trigger_reason=TriggerReason.MANUAL_DEMO_TRIGGER,
        occurrence_count=0,
        example_run_ids_json=[],
        diagnosis_json=None,
        patch_proposal_json=None,
        regression_examples_json=[],
        status="ready",
        created_at=now,
        updated_at=now,
    )
    await insert_improvement_trigger(db, trigger)

    experiment = ExperimentRecord(
        experiment_id=str(uuid.uuid4()),
        improvement_trigger_id=trigger.improvement_trigger_id,
        baseline_prompt_version=baseline.version_tag,
        candidate_prompt_version=candidate.version_tag,
        dataset_id=MANUAL_DATASET_ID,
        status=ExperimentStatus.PENDING,
        baseline_prompt_version_id=baseline_version_id,
        candidate_prompt_version_id=candidate_version_id,
        created_at=now,
    )
    await insert_experiment(db, experiment)

    logger.info(
        "Manual experiment %s created: baseline=%s candidate=%s",
        experiment.experiment_id,
        baseline.version_tag,
        candidate.version_tag,
    )
    return experiment
