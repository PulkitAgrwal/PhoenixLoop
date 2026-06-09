"""Tests for canary fixtures, Cohen's kappa, and per-judge kappa rollup.

We avoid the in-memory ``:memory:`` test_db fixture pattern here because
the canary tables include ``ALTER TABLE`` column migrations that the
in-memory fixture bypasses. Instead each test gets a fresh tmp_path
SQLite file through ``init_db()`` so the full schema (including the
wave-1 column migrations) is applied.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest
from src.db import (
    get_db,
    init_db,
    insert_canary_label,
    insert_canary_run,
    list_canary_labels,
)
from src.evaluation.canary import (
    cohens_kappa,
    compute_kappa_all_judges,
    compute_kappa_for_judge,
    load_canary_fixtures,
)
from src.evaluation.llm_judges.combined import JUDGE_NAMES
from src.models import CanaryLabel, CanaryRun, JudgeLabel, TicketCategory

# ---------------------------------------------------------------------------
# Cohen's kappa — pure-function unit tests
# ---------------------------------------------------------------------------


class TestCohensKappa:
    """Hand-computed kappa values verify the formula."""

    def test_perfect_agreement_returns_one(self) -> None:
        a = ["pass", "fail", "pass", "fail", "insufficient_evidence"]
        b = ["pass", "fail", "pass", "fail", "insufficient_evidence"]
        assert cohens_kappa(a, b) == pytest.approx(1.0)

    def test_perfect_disagreement_is_negative(self) -> None:
        # Two raters split a 6-item set differently across two labels.
        a = ["pass"] * 3 + ["fail"] * 3
        b = ["fail"] * 3 + ["pass"] * 3
        # po = 0/6 = 0; pe = 0.5*0.5 + 0.5*0.5 = 0.5; kappa = (0 - 0.5)/0.5 = -1
        assert cohens_kappa(a, b) == pytest.approx(-1.0)

    def test_chance_agreement_returns_zero(self) -> None:
        # 4 items, raters agree on half, marginals are equal -> kappa = 0.
        # a: pass pass fail fail; b: pass fail pass fail
        # po = 2/4 = 0.5; pa(pass)=0.5, pb(pass)=0.5; pe = 0.5*0.5*2 = 0.5
        # kappa = (0.5 - 0.5) / (1 - 0.5) = 0
        a = ["pass", "pass", "fail", "fail"]
        b = ["pass", "fail", "pass", "fail"]
        assert cohens_kappa(a, b) == pytest.approx(0.0)

    def test_partial_agreement_hand_computed(self) -> None:
        # Hand-verified example with three labels and a known kappa.
        # 5 items:
        #   item 1: a=pass, b=pass        agree
        #   item 2: a=pass, b=fail        disagree
        #   item 3: a=fail, b=fail        agree
        #   item 4: a=fail, b=fail        agree
        #   item 5: a=insufficient, b=insufficient agree
        a = ["pass", "pass", "fail", "fail", "insufficient_evidence"]
        b = ["pass", "fail", "fail", "fail", "insufficient_evidence"]
        # po = 4/5 = 0.8
        # marginals a: pass=2/5, fail=2/5, insuf=1/5
        # marginals b: pass=1/5, fail=3/5, insuf=1/5
        # pe = (2/5)(1/5) + (2/5)(3/5) + (1/5)(1/5)
        #    = 2/25 + 6/25 + 1/25 = 9/25 = 0.36
        # kappa = (0.8 - 0.36) / (1 - 0.36) = 0.44 / 0.64 = 0.6875
        assert cohens_kappa(a, b) == pytest.approx(0.6875)

    def test_degenerate_all_same_label_perfect_agreement(self) -> None:
        a = ["pass"] * 4
        b = ["pass"] * 4
        # pe = 1.0 (degenerate), but all agree -> 1.0 by convention.
        assert cohens_kappa(a, b) == pytest.approx(1.0)

    def test_degenerate_all_same_per_rater_but_disagree(self) -> None:
        # Pathological — every item rater A says pass, rater B says fail.
        # po = 0; pe = pa(pass)*pb(pass) + pa(fail)*pb(fail) = 1*0 + 0*1 = 0
        # kappa = (0 - 0) / (1 - 0) = 0 — NOT a degenerate-pe case.
        a = ["pass"] * 4
        b = ["fail"] * 4
        assert cohens_kappa(a, b) == pytest.approx(0.0)

    def test_empty_lists_raise(self) -> None:
        with pytest.raises(ValueError):
            cohens_kappa([], [])

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            cohens_kappa(["pass"], ["pass", "fail"])


# ---------------------------------------------------------------------------
# Fixture loader idempotency
# ---------------------------------------------------------------------------


class TestLoadCanaryFixtures:
    """Loading the canary set is safe to call repeatedly."""

    @pytest.mark.asyncio
    async def test_idempotent_load(self, tmp_path) -> None:
        db_path = str(tmp_path / "canary_idem.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            inserted_first = await load_canary_fixtures(db)
            inserted_second = await load_canary_fixtures(db)

        assert inserted_first > 0
        assert inserted_second == 0

    @pytest.mark.asyncio
    async def test_load_matches_json_count(self, tmp_path) -> None:
        from src.evaluation.canary import _CANARY_LABELS_PATH

        with _CANARY_LABELS_PATH.open() as fh:
            raw_rows = json.load(fh)

        db_path = str(tmp_path / "canary_count.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            inserted = await load_canary_fixtures(db)
            labels = await list_canary_labels(db, judge_name=None)

        assert inserted == len(raw_rows)
        assert len(labels) == len(raw_rows)

    @pytest.mark.asyncio
    async def test_all_judges_covered(self, tmp_path) -> None:
        """Each of the 4 judges has labels — kappa is computable for all."""
        db_path = str(tmp_path / "canary_judges.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            await load_canary_fixtures(db)
            for judge_name in JUDGE_NAMES:
                labels = await list_canary_labels(db, judge_name=judge_name)
                assert len(labels) > 0, (
                    f"No canary labels for judge {judge_name!r}"
                )


# ---------------------------------------------------------------------------
# Per-judge kappa rollup
# ---------------------------------------------------------------------------


def _make_label(
    fixture_id: str,
    judge_name: str,
    expected: JudgeLabel,
    category: str = "refund",
) -> CanaryLabel:
    return CanaryLabel(
        canary_label_id=str(uuid.uuid4()),
        fixture_id=fixture_id,
        ticket_category=TicketCategory(category),
        judge_name=judge_name,
        expected_label=expected,
        rationale=f"test rationale for {fixture_id}/{judge_name}",
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def _make_run(
    label: CanaryLabel,
    predicted: JudgeLabel,
    judge_model: str = "gemini-2.5-flash",
) -> CanaryRun:
    return CanaryRun(
        canary_run_id=str(uuid.uuid4()),
        canary_label_id=label.canary_label_id,
        judge_name=label.judge_name,
        predicted_label=predicted,
        evidence_json=[f"evidence for {label.fixture_id}"],
        explanation=f"predicted {predicted.value}",
        judge_model=judge_model,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


class TestComputeKappaForJudge:
    """End-to-end kappa rollup with synthetic CanaryRuns inserted directly."""

    @pytest.mark.asyncio
    async def test_perfect_agreement(self, tmp_path) -> None:
        db_path = str(tmp_path / "kappa_perfect.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            labels = [
                _make_label("fx1", "groundedness", JudgeLabel.PASS),
                _make_label("fx2", "groundedness", JudgeLabel.FAIL),
                _make_label(
                    "fx3",
                    "groundedness",
                    JudgeLabel.INSUFFICIENT_EVIDENCE,
                ),
                _make_label("fx4", "groundedness", JudgeLabel.PASS),
            ]
            for label in labels:
                await insert_canary_label(db, label)
                await insert_canary_run(db, _make_run(label, label.expected_label))

            result = await compute_kappa_for_judge(db, "groundedness")

        assert result["judge_name"] == "groundedness"
        assert result["n_samples"] == 4
        assert result["cohens_kappa"] == pytest.approx(1.0)
        assert result["accuracy"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_zero_samples_kappa_none(self, tmp_path) -> None:
        db_path = str(tmp_path / "kappa_zero.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            result = await compute_kappa_for_judge(db, "groundedness")
        assert result["n_samples"] == 0
        assert result["cohens_kappa"] is None
        assert result["accuracy"] == 0.0

    @pytest.mark.asyncio
    async def test_one_sample_kappa_none(self, tmp_path) -> None:
        db_path = str(tmp_path / "kappa_one.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            label = _make_label("fx1", "groundedness", JudgeLabel.PASS)
            await insert_canary_label(db, label)
            await insert_canary_run(db, _make_run(label, JudgeLabel.PASS))
            result = await compute_kappa_for_judge(db, "groundedness")
        assert result["n_samples"] == 1
        # Kappa undefined on a single observation — accuracy still defined.
        assert result["cohens_kappa"] is None
        assert result["accuracy"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_partial_disagreement_confusion_matrix(self, tmp_path) -> None:
        db_path = str(tmp_path / "kappa_confusion.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            l1 = _make_label("fx1", "policy_compliance", JudgeLabel.PASS)
            l2 = _make_label("fx2", "policy_compliance", JudgeLabel.PASS)
            l3 = _make_label("fx3", "policy_compliance", JudgeLabel.FAIL)
            l4 = _make_label("fx4", "policy_compliance", JudgeLabel.FAIL)
            for label in (l1, l2, l3, l4):
                await insert_canary_label(db, label)
            await insert_canary_run(db, _make_run(l1, JudgeLabel.PASS))  # correct
            await insert_canary_run(db, _make_run(l2, JudgeLabel.FAIL))  # wrong
            await insert_canary_run(db, _make_run(l3, JudgeLabel.FAIL))  # correct
            await insert_canary_run(db, _make_run(l4, JudgeLabel.FAIL))  # correct

            result = await compute_kappa_for_judge(db, "policy_compliance")

        assert result["n_samples"] == 4
        assert result["accuracy"] == pytest.approx(0.75)
        # Confusion matrix [expected][predicted]:
        # expected=pass, predicted=pass -> 1
        # expected=pass, predicted=fail -> 1
        # expected=fail, predicted=fail -> 2
        cm = result["confusion_matrix"]
        assert cm["pass"]["pass"] == 1
        assert cm["pass"]["fail"] == 1
        assert cm["fail"]["fail"] == 2
        assert cm["fail"]["pass"] == 0
        # kappa: po = 3/4 = 0.75
        # marginals expected: pass=2/4=0.5, fail=2/4=0.5
        # marginals predicted: pass=1/4=0.25, fail=3/4=0.75
        # pe = 0.5*0.25 + 0.5*0.75 + 0*0 = 0.125 + 0.375 = 0.5
        # kappa = (0.75 - 0.5) / (1 - 0.5) = 0.5
        assert result["cohens_kappa"] == pytest.approx(0.5)


class TestComputeKappaAllJudges:
    """``compute_kappa_all_judges`` returns one entry per judge."""

    @pytest.mark.asyncio
    async def test_returns_four_judges(self, tmp_path) -> None:
        db_path = str(tmp_path / "kappa_all.db")
        await init_db(db_path)
        async with get_db(db_path) as db:
            results = await compute_kappa_all_judges(db)

        assert len(results) == 4
        names = {r["judge_name"] for r in results}
        assert names == set(JUDGE_NAMES)
        # Empty DB -> every judge reports zero samples + None kappa.
        for r in results:
            assert r["n_samples"] == 0
            assert r["cohens_kappa"] is None
