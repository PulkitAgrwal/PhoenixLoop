"""Tests for the failure aggregation pipeline."""

from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest
from src.db import (
    _CREATE_TABLES_SQL,
    get_failure_aggregate,
    init_db,
    insert_improvement_trigger,
    upsert_failure_aggregate,
)
from src.diagnosis.failure_aggregator import (
    CRITICAL_FAILURE_TYPES,
    EVALUATOR_FAILURE_MAP,
    _within_cooldown,
    check_thresholds,
    is_critical_failure,
    update_aggregates,
)
from src.models import (
    AnnotationLevel,
    EvalResult,
    EvalType,
    FailureAggregate,
    ImprovementTrigger,
    TriggerReason,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    """Provide an in-memory SQLite connection with schema initialized."""
    await init_db(":memory:")
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.executescript(_CREATE_TABLES_SQL)
    await conn.commit()
    yield conn
    await conn.close()


def _make_eval_result(
    eval_result_id: str = "ER-001",
    agent_run_id: str = "AR-001",
    evaluator_name: str = "tool_sequence",
    outcome: str = "fail",
    failure_key: str | None = "missing_required_tool::lookup_order",
    failure_summary: str | None = "Agent did not call lookup_order",
) -> EvalResult:
    """Create a test EvalResult."""
    return EvalResult(
        eval_result_id=eval_result_id,
        agent_run_id=agent_run_id,
        evaluator_name=evaluator_name,
        eval_type=EvalType.CODE,
        score=0.0 if outcome == "fail" else 1.0,
        outcome=outcome,
        failure_key=failure_key,
        failure_summary=failure_summary,
        annotation_level=AnnotationLevel.SESSION,
        created_at="2025-01-01T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# is_critical_failure
# ---------------------------------------------------------------------------


class TestIsCriticalFailure:
    def test_critical_evaluator_privacy_guard(self):
        result = _make_eval_result(evaluator_name="privacy_guard")
        assert is_critical_failure(result) is True

    def test_critical_evaluator_escalation_guard(self):
        result = _make_eval_result(evaluator_name="escalation_guard")
        assert is_critical_failure(result) is True

    def test_critical_evaluator_groundedness(self):
        result = _make_eval_result(evaluator_name="groundedness")
        assert is_critical_failure(result) is True

    def test_critical_evaluator_schema_validity(self):
        result = _make_eval_result(evaluator_name="schema_validity")
        assert is_critical_failure(result) is True

    def test_critical_evaluator_tool_sequence(self):
        result = _make_eval_result(evaluator_name="tool_sequence")
        assert is_critical_failure(result) is True

    def test_critical_evaluator_resolution_correctness(self):
        result = _make_eval_result(evaluator_name="resolution_correctness")
        assert is_critical_failure(result) is True

    def test_critical_evaluator_tool_selection(self):
        result = _make_eval_result(evaluator_name="tool_selection")
        assert is_critical_failure(result) is True

    def test_non_critical_evaluator_citation_presence(self):
        """citation_presence maps to RETRIEVAL_MISS which is not critical."""
        result = _make_eval_result(evaluator_name="citation_presence")
        assert is_critical_failure(result) is False

    def test_non_critical_evaluator_latency_budget(self):
        """latency_budget maps to LATENCY_REGRESSION which is not critical."""
        result = _make_eval_result(evaluator_name="latency_budget")
        assert is_critical_failure(result) is False

    def test_unknown_evaluator(self):
        """An evaluator not in the map should not be critical."""
        result = _make_eval_result(evaluator_name="unknown_evaluator")
        assert is_critical_failure(result) is False

    def test_all_critical_types_covered(self):
        """Verify that every CRITICAL_FAILURE_TYPE has at least one evaluator mapped."""
        mapped_types = set(EVALUATOR_FAILURE_MAP.values())
        for critical_type in CRITICAL_FAILURE_TYPES:
            assert critical_type in mapped_types, (
                f"{critical_type} is marked critical but has no evaluator mapping"
            )


# ---------------------------------------------------------------------------
# update_aggregates
# ---------------------------------------------------------------------------


class TestUpdateAggregates:
    @pytest.mark.asyncio
    async def test_creates_new_aggregate(self, db):
        """First failing eval creates a new aggregate with count=1."""
        results = [_make_eval_result()]
        updated_keys = await update_aggregates(results, db)

        assert updated_keys == ["missing_required_tool::lookup_order"]

        agg = await get_failure_aggregate(db, "missing_required_tool::lookup_order")
        assert agg is not None
        assert agg.occurrence_count == 1
        assert agg.evaluator_name == "tool_sequence"
        assert agg.example_run_ids_json == ["AR-001"]
        assert agg.is_active is True

    @pytest.mark.asyncio
    async def test_increments_existing_aggregate(self, db):
        """Second failing eval increments count and appends run_id."""
        first = _make_eval_result(
            eval_result_id="ER-001", agent_run_id="AR-001"
        )
        second = _make_eval_result(
            eval_result_id="ER-002", agent_run_id="AR-002"
        )

        await update_aggregates([first], db)
        await update_aggregates([second], db)

        agg = await get_failure_aggregate(db, "missing_required_tool::lookup_order")
        assert agg is not None
        assert agg.occurrence_count == 2
        assert "AR-001" in agg.example_run_ids_json
        assert "AR-002" in agg.example_run_ids_json

    @pytest.mark.asyncio
    async def test_skips_passing_evals(self, db):
        """Passing eval results should not create aggregates."""
        passing = _make_eval_result(outcome="pass", failure_key=None)
        updated_keys = await update_aggregates([passing], db)

        assert updated_keys == []

    @pytest.mark.asyncio
    async def test_skips_evals_without_failure_key(self, db):
        """Failing evals with no failure_key should be skipped."""
        no_key = _make_eval_result(failure_key=None)
        updated_keys = await update_aggregates([no_key], db)

        assert updated_keys == []

    @pytest.mark.asyncio
    async def test_deduplicates_run_ids(self, db):
        """Same run_id should not be appended twice."""
        result = _make_eval_result()
        await update_aggregates([result], db)
        await update_aggregates([result], db)

        agg = await get_failure_aggregate(db, "missing_required_tool::lookup_order")
        assert agg is not None
        assert agg.occurrence_count == 2
        # run_id appears only once despite two updates
        assert agg.example_run_ids_json.count("AR-001") == 1

    @pytest.mark.asyncio
    async def test_multiple_different_failure_keys(self, db):
        """Multiple failures with different keys each create their own aggregate."""
        r1 = _make_eval_result(
            eval_result_id="ER-001",
            failure_key="missing_required_tool::lookup_order",
            evaluator_name="tool_sequence",
        )
        r2 = _make_eval_result(
            eval_result_id="ER-002",
            failure_key="privacy_leak::pii_in_response",
            evaluator_name="privacy_guard",
            failure_summary="PII found in response",
        )

        updated_keys = await update_aggregates([r1, r2], db)
        assert len(updated_keys) == 2

        agg1 = await get_failure_aggregate(db, "missing_required_tool::lookup_order")
        agg2 = await get_failure_aggregate(db, "privacy_leak::pii_in_response")
        assert agg1 is not None
        assert agg2 is not None
        assert agg1.occurrence_count == 1
        assert agg2.occurrence_count == 1

    @pytest.mark.asyncio
    async def test_preserves_first_seen_at(self, db):
        """Incrementing should not change first_seen_at."""
        r1 = _make_eval_result(eval_result_id="ER-001", agent_run_id="AR-001")
        r2 = _make_eval_result(eval_result_id="ER-002", agent_run_id="AR-002")

        await update_aggregates([r1], db)
        agg1 = await get_failure_aggregate(db, "missing_required_tool::lookup_order")
        first_seen = agg1.first_seen_at

        await update_aggregates([r2], db)
        agg2 = await get_failure_aggregate(db, "missing_required_tool::lookup_order")

        assert agg2.first_seen_at == first_seen
        assert agg2.last_seen_at != first_seen  # last_seen should advance


# ---------------------------------------------------------------------------
# check_thresholds
# ---------------------------------------------------------------------------


class TestCheckThresholds:
    @pytest.mark.asyncio
    async def test_triggers_at_threshold(self, db):
        """Aggregate at repeated_failure_count should create a trigger."""
        # Seed an aggregate at count=2 (default threshold)
        agg = FailureAggregate(
            failure_key="missing_required_tool::lookup_order",
            failure_summary="Agent did not call lookup_order",
            evaluator_name="tool_sequence",
            occurrence_count=2,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-02T00:00:00Z",
            example_run_ids_json=["AR-001", "AR-002"],
            is_active=True,
            computed_at="2025-01-02T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg)

        triggers = await check_thresholds(db)
        assert len(triggers) == 1
        assert triggers[0].failure_key == "missing_required_tool::lookup_order"
        assert triggers[0].trigger_reason == TriggerReason.THRESHOLD_REPEATED_FAILURE
        assert triggers[0].occurrence_count == 2
        assert triggers[0].status == "pending"

    @pytest.mark.asyncio
    async def test_does_not_trigger_below_threshold(self, db):
        """Aggregate below repeated_failure_count should not create a trigger."""
        agg = FailureAggregate(
            failure_key="missing_required_tool::lookup_order",
            failure_summary="Agent did not call lookup_order",
            evaluator_name="tool_sequence",
            occurrence_count=1,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-01T00:00:00Z",
            example_run_ids_json=["AR-001"],
            is_active=True,
            computed_at="2025-01-01T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg)

        triggers = await check_thresholds(db)
        assert len(triggers) == 0

    @pytest.mark.asyncio
    async def test_critical_failure_immediate_trigger(self, db):
        """Critical failure should trigger immediately regardless of count."""
        eval_result = _make_eval_result(
            evaluator_name="privacy_guard",
            failure_key="privacy_leak::pii_in_response",
        )

        triggers = await check_thresholds(db, eval_results=[eval_result])
        assert len(triggers) == 1
        assert triggers[0].trigger_reason == TriggerReason.CRITICAL_FAILURE
        assert triggers[0].failure_key == "privacy_leak::pii_in_response"

    @pytest.mark.asyncio
    async def test_critical_failure_respects_cooldown(self, db):
        """Critical failure within cooldown period should not re-trigger."""
        # Insert an existing trigger created "now" (within cooldown)
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = ImprovementTrigger(
            improvement_trigger_id="IT-EXISTING",
            failure_key="privacy_leak::pii_in_response",
            trigger_reason=TriggerReason.CRITICAL_FAILURE,
            occurrence_count=1,
            example_run_ids_json=["AR-OLD"],
            status="pending",
            created_at=now_iso,
            updated_at=now_iso,
        )
        await insert_improvement_trigger(db, existing)

        eval_result = _make_eval_result(
            evaluator_name="privacy_guard",
            failure_key="privacy_leak::pii_in_response",
        )

        triggers = await check_thresholds(db, eval_results=[eval_result])
        assert len(triggers) == 0

    @pytest.mark.asyncio
    async def test_critical_failure_triggers_after_cooldown_expires(self, db):
        """Critical failure should trigger once cooldown has expired."""
        # Insert a trigger from well past the cooldown window
        old_time = (
            datetime.now(timezone.utc) - timedelta(minutes=60)
        ).isoformat()
        existing = ImprovementTrigger(
            improvement_trigger_id="IT-OLD",
            failure_key="privacy_leak::pii_in_response",
            trigger_reason=TriggerReason.CRITICAL_FAILURE,
            occurrence_count=1,
            example_run_ids_json=["AR-OLD"],
            status="pending",
            created_at=old_time,
            updated_at=old_time,
        )
        await insert_improvement_trigger(db, existing)

        eval_result = _make_eval_result(
            evaluator_name="privacy_guard",
            failure_key="privacy_leak::pii_in_response",
        )

        triggers = await check_thresholds(db, eval_results=[eval_result])
        assert len(triggers) == 1
        assert triggers[0].trigger_reason == TriggerReason.CRITICAL_FAILURE

    @pytest.mark.asyncio
    async def test_non_critical_failure_not_immediate(self, db):
        """Non-critical failure should not trigger immediately via eval_results."""
        eval_result = _make_eval_result(
            evaluator_name="citation_presence",
            failure_key="retrieval_miss::no_citation",
        )

        triggers = await check_thresholds(db, eval_results=[eval_result])
        # No aggregate at threshold, no critical failure -> no triggers
        assert len(triggers) == 0

    @pytest.mark.asyncio
    async def test_threshold_trigger_respects_cooldown(self, db):
        """Threshold trigger within cooldown should not re-trigger."""
        # Aggregate at threshold
        agg = FailureAggregate(
            failure_key="missing_required_tool::lookup_order",
            failure_summary="Agent did not call lookup_order",
            evaluator_name="tool_sequence",
            occurrence_count=3,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-02T00:00:00Z",
            example_run_ids_json=["AR-001", "AR-002", "AR-003"],
            is_active=True,
            computed_at="2025-01-02T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg)

        # Existing trigger still within cooldown
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = ImprovementTrigger(
            improvement_trigger_id="IT-EXISTING",
            failure_key="missing_required_tool::lookup_order",
            trigger_reason=TriggerReason.THRESHOLD_REPEATED_FAILURE,
            occurrence_count=2,
            example_run_ids_json=["AR-001", "AR-002"],
            status="pending",
            created_at=now_iso,
            updated_at=now_iso,
        )
        await insert_improvement_trigger(db, existing)

        triggers = await check_thresholds(db)
        assert len(triggers) == 0

    @pytest.mark.asyncio
    async def test_inactive_aggregates_ignored(self, db):
        """Inactive aggregates should not trigger even if above threshold."""
        agg = FailureAggregate(
            failure_key="old_failure::resolved",
            failure_summary="Old resolved failure",
            evaluator_name="tool_sequence",
            occurrence_count=10,
            first_seen_at="2025-01-01T00:00:00Z",
            last_seen_at="2025-01-05T00:00:00Z",
            example_run_ids_json=["AR-001"],
            is_active=False,
            computed_at="2025-01-05T00:00:00Z",
        )
        await upsert_failure_aggregate(db, agg)

        triggers = await check_thresholds(db)
        assert len(triggers) == 0

    @pytest.mark.asyncio
    async def test_passing_evals_do_not_trigger_critical(self, db):
        """Passing eval results should not trigger critical failure path."""
        eval_result = _make_eval_result(
            evaluator_name="privacy_guard",
            outcome="pass",
            failure_key=None,
        )

        triggers = await check_thresholds(db, eval_results=[eval_result])
        assert len(triggers) == 0


# ---------------------------------------------------------------------------
# _within_cooldown
# ---------------------------------------------------------------------------


class TestWithinCooldown:
    def test_within_cooldown_returns_true(self):
        recent = datetime.now(timezone.utc).isoformat()
        assert _within_cooldown(recent, cooldown_minutes=30) is True

    def test_past_cooldown_returns_false(self):
        old = (datetime.now(timezone.utc) - timedelta(minutes=60)).isoformat()
        assert _within_cooldown(old, cooldown_minutes=30) is False

    def test_invalid_timestamp_returns_false(self):
        assert _within_cooldown("not-a-timestamp", cooldown_minutes=30) is False

    def test_none_timestamp_returns_false(self):
        assert _within_cooldown(None, cooldown_minutes=30) is False  # type: ignore[arg-type]

    def test_naive_datetime_treated_as_utc(self):
        """Naive datetime strings should be treated as UTC."""
        recent = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        assert _within_cooldown(recent, cooldown_minutes=30) is True

    def test_zero_cooldown(self):
        """Zero-minute cooldown should never be within cooldown."""
        recent = datetime.now(timezone.utc).isoformat()
        assert _within_cooldown(recent, cooldown_minutes=0) is False
