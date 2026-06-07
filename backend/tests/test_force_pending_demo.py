"""Demo-mode coercion of release-gate verdicts."""

import uuid
from datetime import datetime, timezone

from src.experiments.release_gate import (
    check_promotion_rules,
    coerce_to_pending_review,
)
from src.models import ExperimentRecord, ExperimentStatus, ReleaseDecision


def _experiment(*, critical_failure_rate: float, candidate_score: float) -> ExperimentRecord:
    now = datetime.now(timezone.utc).isoformat()
    return ExperimentRecord(
        experiment_id=str(uuid.uuid4()),
        improvement_trigger_id=str(uuid.uuid4()),
        baseline_prompt_version="v1",
        candidate_prompt_version="v2",
        dataset_id="regression-test",
        status=ExperimentStatus.COMPLETED,
        baseline_release_score=0.5,
        candidate_release_score=candidate_score,
        baseline_critical_failure_rate=0.0,
        candidate_critical_failure_rate=critical_failure_rate,
        baseline_latency_p50_ms=1000,
        candidate_latency_p50_ms=1100,
        baseline_hallucination_rate=0.0,
        candidate_hallucination_rate=0.0,
        regression_cases_pass_rate=0.95,
        safety_canary_pass_rate=1.0,
        created_at=now,
    )


def test_coerce_flips_rejected_to_pending():
    # Score delta below threshold normally rejects
    decision = check_promotion_rules(_experiment(
        critical_failure_rate=0.0, candidate_score=0.51,
    ))
    assert decision.decision == ReleaseDecision.REJECTED

    forced = coerce_to_pending_review(decision)
    assert forced.decision == ReleaseDecision.PENDING_HUMAN_REVIEW
    assert forced.promotion_rules_passed == len(forced.rules_detail_json)
    for rule in forced.rules_detail_json.values():
        assert rule["passed"] is True
        assert rule.get("_demo_forced") is True


def test_coerce_preserves_score_and_experiment_id():
    decision = check_promotion_rules(_experiment(
        critical_failure_rate=0.0, candidate_score=0.51,
    ))
    forced = coerce_to_pending_review(decision)
    assert forced.release_score == decision.release_score
    assert forced.experiment_id == decision.experiment_id
    assert forced.release_gate_decision_id == decision.release_gate_decision_id
