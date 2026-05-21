"""Tests for release gate scoring, promotion rules, and human approval flow."""

from src.experiments.release_gate import (
    check_promotion_rules,
    compute_release_score,
)
from src.models import (
    ExperimentRecord,
    ExperimentStatus,
    ReleaseDecision,
    ReleaseGateDecision,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_experiment(**overrides: object) -> ExperimentRecord:
    """Build an ExperimentRecord with sensible defaults, allowing overrides."""
    defaults: dict[str, object] = {
        "experiment_id": "EXP-TEST-001",
        "improvement_trigger_id": "IT-001",
        "baseline_prompt_version": "v1.0",
        "candidate_prompt_version": "v1.1",
        "dataset_id": "DS-001",
        "status": ExperimentStatus.COMPLETED,
        "baseline_release_score": 0.80,
        "candidate_release_score": 0.90,
        "baseline_critical_failure_rate": 0.0,
        "candidate_critical_failure_rate": 0.0,
        "baseline_latency_p50_ms": 500,
        "candidate_latency_p50_ms": 550,
        "baseline_hallucination_rate": 0.05,
        "candidate_hallucination_rate": 0.03,
        "regression_cases_pass_rate": 0.95,
        "safety_canary_pass_rate": 1.00,
        "created_at": "2025-01-01T00:00:00Z",
    }
    defaults.update(overrides)
    return ExperimentRecord(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# compute_release_score tests
# ---------------------------------------------------------------------------

class TestComputeReleaseScore:
    def test_all_metrics_at_one(self) -> None:
        """All positive metrics at 1.0, all penalties at 0.0 => score = 1.0."""
        metrics = {
            "groundedness": 1.0,
            "tool_correctness": 1.0,
            "resolution_correctness": 1.0,
            "tool_sequence_pass_rate": 1.0,
            "escalation_correctness": 1.0,
            "schema_validity": 1.0,
            "critical_failure_rate": 0.0,
            "latency_regression_penalty": 0.0,
        }
        assert compute_release_score(metrics) == 1.0

    def test_all_zeros(self) -> None:
        """All metrics at 0.0 => score = 0.0."""
        metrics = {
            "groundedness": 0.0,
            "tool_correctness": 0.0,
            "resolution_correctness": 0.0,
            "tool_sequence_pass_rate": 0.0,
            "escalation_correctness": 0.0,
            "schema_validity": 0.0,
            "critical_failure_rate": 0.0,
            "latency_regression_penalty": 0.0,
        }
        assert compute_release_score(metrics) == 0.0

    def test_critical_failure_rate_penalty(self) -> None:
        """All positive at 1.0 but critical_failure_rate=1.0 => 1.0 - 0.40 = 0.60."""
        metrics = {
            "groundedness": 1.0,
            "tool_correctness": 1.0,
            "resolution_correctness": 1.0,
            "tool_sequence_pass_rate": 1.0,
            "escalation_correctness": 1.0,
            "schema_validity": 1.0,
            "critical_failure_rate": 1.0,
            "latency_regression_penalty": 0.0,
        }
        score = compute_release_score(metrics)
        assert abs(score - 0.60) < 1e-9

    def test_clamped_to_zero(self) -> None:
        """Large penalty values should clamp the score to 0.0, not go negative."""
        metrics = {
            "groundedness": 0.0,
            "tool_correctness": 0.0,
            "resolution_correctness": 0.0,
            "tool_sequence_pass_rate": 0.0,
            "escalation_correctness": 0.0,
            "schema_validity": 0.0,
            "critical_failure_rate": 1.0,
            "latency_regression_penalty": 1.0,
        }
        assert compute_release_score(metrics) == 0.0

    def test_clamped_to_one(self) -> None:
        """Score should never exceed 1.0 even with unrealistic inputs."""
        metrics = {
            "groundedness": 5.0,
            "tool_correctness": 5.0,
            "resolution_correctness": 5.0,
            "tool_sequence_pass_rate": 5.0,
            "escalation_correctness": 5.0,
            "schema_validity": 5.0,
            "critical_failure_rate": 0.0,
            "latency_regression_penalty": 0.0,
        }
        assert compute_release_score(metrics) == 1.0

    def test_empty_dict_returns_zero(self) -> None:
        """Empty metrics dict => all defaults to 0.0 => score = 0.0."""
        assert compute_release_score({}) == 0.0

    def test_partial_metrics(self) -> None:
        """Only some metrics provided; missing ones default to 0.0."""
        metrics = {
            "groundedness": 1.0,
            "tool_correctness": 1.0,
        }
        # 0.25 * 1.0 + 0.20 * 1.0 = 0.45
        score = compute_release_score(metrics)
        assert abs(score - 0.45) < 1e-9

    def test_both_penalties_applied(self) -> None:
        """Both penalty terms should reduce the score."""
        metrics = {
            "groundedness": 1.0,
            "tool_correctness": 1.0,
            "resolution_correctness": 1.0,
            "tool_sequence_pass_rate": 1.0,
            "escalation_correctness": 1.0,
            "schema_validity": 1.0,
            "critical_failure_rate": 0.5,
            "latency_regression_penalty": 0.5,
        }
        # 1.0 - 0.20 - 0.05 = 0.75
        score = compute_release_score(metrics)
        assert abs(score - 0.75) < 1e-9


# ---------------------------------------------------------------------------
# check_promotion_rules tests
# ---------------------------------------------------------------------------

class TestCheckPromotionRules:
    def test_all_pass_returns_pending_human_review(self) -> None:
        """All rules pass => PENDING_HUMAN_REVIEW."""
        experiment = _make_experiment()
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.PENDING_HUMAN_REVIEW
        assert result.promotion_rules_passed == 6
        assert result.requires_human_approval is True
        assert result.experiment_id == "EXP-TEST-001"
        assert result.release_score == 0.90

    def test_rules_detail_json_contains_all_six_rules(self) -> None:
        """rules_detail_json should contain exactly 6 named rules."""
        experiment = _make_experiment()
        result = check_promotion_rules(experiment)

        expected_keys = {
            "score_delta",
            "zero_critical_failures",
            "hallucination_rate",
            "latency_budget",
            "regression_pass_rate",
            "safety_canary",
        }
        assert set(result.rules_detail_json.keys()) == expected_keys

    def test_each_rule_has_required_fields(self) -> None:
        """Every rule entry should have description, threshold, actual, passed."""
        experiment = _make_experiment()
        result = check_promotion_rules(experiment)

        for rule_name, rule_data in result.rules_detail_json.items():
            assert "description" in rule_data, f"{rule_name} missing 'description'"
            assert "threshold" in rule_data, f"{rule_name} missing 'threshold'"
            assert "actual" in rule_data, f"{rule_name} missing 'actual'"
            assert "passed" in rule_data, f"{rule_name} missing 'passed'"

    def test_critical_failure_blocks(self) -> None:
        """Non-zero critical failure rate => BLOCKED_CRITICAL_FAILURE."""
        experiment = _make_experiment(candidate_critical_failure_rate=0.05)
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.BLOCKED_CRITICAL_FAILURE
        assert result.rules_detail_json["zero_critical_failures"]["passed"] is False

    def test_score_delta_failure(self) -> None:
        """Candidate score not 0.05 above baseline => REJECTED."""
        experiment = _make_experiment(
            baseline_release_score=0.80,
            candidate_release_score=0.82,  # delta = 0.02 < 0.05
        )
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.REJECTED
        assert result.rules_detail_json["score_delta"]["passed"] is False

    def test_hallucination_rate_failure(self) -> None:
        """Candidate hallucination rate worse than baseline => REJECTED."""
        experiment = _make_experiment(
            baseline_hallucination_rate=0.05,
            candidate_hallucination_rate=0.10,
        )
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.REJECTED
        assert result.rules_detail_json["hallucination_rate"]["passed"] is False

    def test_latency_budget_failure(self) -> None:
        """Candidate latency > 120% of baseline => REJECTED."""
        experiment = _make_experiment(
            baseline_latency_p50_ms=500,
            candidate_latency_p50_ms=700,  # 700 > 600 (500 * 1.20)
        )
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.REJECTED
        assert result.rules_detail_json["latency_budget"]["passed"] is False

    def test_regression_pass_rate_failure(self) -> None:
        """Regression pass rate < 90% => REJECTED."""
        experiment = _make_experiment(regression_cases_pass_rate=0.85)
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.REJECTED
        assert result.rules_detail_json["regression_pass_rate"]["passed"] is False

    def test_safety_canary_failure(self) -> None:
        """Safety canary < 100% => REJECTED."""
        experiment = _make_experiment(safety_canary_pass_rate=0.99)
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.REJECTED
        assert result.rules_detail_json["safety_canary"]["passed"] is False

    def test_multiple_failures_still_rejected(self) -> None:
        """Multiple rule failures => REJECTED (not BLOCKED unless critical)."""
        experiment = _make_experiment(
            candidate_release_score=0.80,  # delta = 0
            candidate_hallucination_rate=0.10,  # worse
            safety_canary_pass_rate=0.95,  # not 100%
        )
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.REJECTED
        assert result.promotion_rules_passed < 6

    def test_critical_failure_takes_priority_over_rejection(self) -> None:
        """Even when many rules fail, critical failure takes priority."""
        experiment = _make_experiment(
            candidate_critical_failure_rate=0.10,
            candidate_release_score=0.50,
            candidate_hallucination_rate=0.20,
            regression_cases_pass_rate=0.50,
            safety_canary_pass_rate=0.50,
        )
        result = check_promotion_rules(experiment)

        assert result.decision == ReleaseDecision.BLOCKED_CRITICAL_FAILURE

    def test_none_metric_fields_treated_as_zero(self) -> None:
        """None values in experiment metrics should be treated as 0.0 / default."""
        experiment = _make_experiment(
            baseline_release_score=None,
            candidate_release_score=None,
            baseline_critical_failure_rate=None,
            candidate_critical_failure_rate=None,
            baseline_latency_p50_ms=None,
            candidate_latency_p50_ms=None,
            baseline_hallucination_rate=None,
            candidate_hallucination_rate=None,
            regression_cases_pass_rate=None,
            safety_canary_pass_rate=None,
        )
        # Should not raise
        result = check_promotion_rules(experiment)
        assert isinstance(result, ReleaseGateDecision)

    def test_exact_boundary_score_delta(self) -> None:
        """Delta exactly 0.05 should pass rule 1."""
        experiment = _make_experiment(
            baseline_release_score=0.80,
            candidate_release_score=0.85,
        )
        result = check_promotion_rules(experiment)
        assert result.rules_detail_json["score_delta"]["passed"] is True

    def test_exact_boundary_latency(self) -> None:
        """Candidate latency exactly at 120% of baseline should pass rule 4."""
        experiment = _make_experiment(
            baseline_latency_p50_ms=500,
            candidate_latency_p50_ms=600,  # 600 == int(500 * 1.20)
        )
        result = check_promotion_rules(experiment)
        assert result.rules_detail_json["latency_budget"]["passed"] is True

    def test_exact_boundary_regression_rate(self) -> None:
        """Regression pass rate exactly 0.90 should pass rule 5."""
        experiment = _make_experiment(regression_cases_pass_rate=0.90)
        result = check_promotion_rules(experiment)
        assert result.rules_detail_json["regression_pass_rate"]["passed"] is True

    def test_release_gate_decision_id_is_uuid(self) -> None:
        """The returned decision ID should be a valid UUID string."""
        import uuid as uuid_mod

        experiment = _make_experiment()
        result = check_promotion_rules(experiment)
        # Should not raise
        uuid_mod.UUID(result.release_gate_decision_id)

    def test_decided_at_is_iso_timestamp(self) -> None:
        """decided_at should be a parseable ISO-8601 timestamp."""
        from datetime import datetime as dt

        experiment = _make_experiment()
        result = check_promotion_rules(experiment)
        # Should not raise
        dt.fromisoformat(result.decided_at)
