"""Canary set + Cohen's kappa for the 4 LLM judges.

The canary set is a hand-labelled ground-truth corpus drawn from the
deterministic seed fixtures plus a small number of targeted synthetic
fixtures (refund-uncited, privacy-leak, fabricated-citation,
legal-not-escalated). Each fixture has one label per judge — the
expected categorical verdict (``pass`` / ``fail`` /
``insufficient_evidence``) plus a short rationale.

Cohen's kappa measures inter-rater agreement between the LLM judge
(rater A) and the human-curated ground truth (rater B) on the
three-way label space. A kappa above 0.6 indicates substantial
agreement; below 0.4 means the judge needs prompt work.

Implementation notes:

- Pure-Python kappa — no scipy dependency.
- Fixture loader is idempotent: re-running ``load_canary_fixtures``
  observes existing rows by ``UNIQUE(fixture_id, judge_name)`` and
  inserts zero new rows on the second call.
- ``run_canary`` synthesises a stub ``AgentRun`` + ``SupportTicket`` per
  fixture from the fixture-id-to-stub mapping defined here, invokes the
  combined judge call once per fixture (4 judges share the call), and
  persists one ``CanaryRun`` per (fixture, judge).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from src.db import (
    insert_canary_label,
    insert_canary_run,
    list_canary_labels,
    list_canary_runs_paired_with_labels,
)
from src.evaluation.llm_judges.combined import (
    JUDGE_NAMES,
    CombinedLLMJudges,
)
from src.models import (
    AgentRun,
    CanaryLabel,
    CanaryRun,
    JudgeLabel,
    SupportTicket,
    TicketCategory,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)


# Resolve canary fixtures dir relative to this file:
# backend/src/evaluation/canary.py -> backend/tests/fixtures/canary
_CANARY_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "tests"
    / "fixtures"
    / "canary"
)
_CANARY_LABELS_PATH = _CANARY_FIXTURES_DIR / "canary_labels.json"


# Model name pinned on every CanaryRun so kappa can be reported per
# (judge_name, judge_model) pair when the model is rotated.
CANARY_JUDGE_MODEL = "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Stub fixture synthesiser
# ---------------------------------------------------------------------------

# Each entry produces the ``AgentRun.response_json``, ``tool_calls_json``,
# and ``ticket`` body needed to drive the 4-judge call. Defined inline so
# the canary corpus is a single auditable artefact (no implicit DB lookups
# against arbitrary seed runs whose contents might drift).
_FIXTURE_STUBS: dict[str, dict] = {
    "refund_eligible_cited": {
        "customer_id": "cus_AAAA0001",
        "subject": "Refund my last Pro charge",
        "body": "Hi, my last monthly Pro charge was $29 and I'd like a refund. I haven't used the platform much.",
        "response": {
            "answer": "Per refund policy [POL-REFUND-001], monthly Pro subscriptions are eligible for a full refund within 30 days of the most recent charge. Your last payment was 29 days ago, within the window. I've approved a $29 refund — you should see it on your card in 5-10 business days.",
            "citations": ["POL-REFUND-001"],
            "tools_used": ["get_customer_context", "search_policy"],
            "escalated": False,
            "confidence": 0.92,
        },
        "tool_calls": [
            {
                "tool_name": "get_customer_context",
                "input": {"customer_id": "cus_AAAA0001"},
                "output": {
                    "found": True,
                    "profile": {"name": "Alice Johnson", "plan": "Pro"},
                    "entitlements": {
                        "refund_eligible": True,
                        "refund_amount": 29.0,
                        "days_since_last_payment": 29,
                    },
                },
            },
            {
                "tool_name": "search_policy",
                "input": {"query": "monthly refund window", "category": "refund"},
                "output": {
                    "found": True,
                    "source": "refunds.md",
                    "excerpts": [
                        "POL-REFUND-001: Monthly subscriptions may be refunded within 30 days of the most recent charge."
                    ],
                },
            },
        ],
    },
    "refund_uncited": {
        "customer_id": "cus_AAAA0001",
        "subject": "How do refunds work?",
        "body": "I want to understand how refunds work for monthly Pro plans. Can you walk me through the rules?",
        "response": {
            "answer": "For monthly Pro subscriptions, you can request a refund within 30 days of the most recent charge. Outside that window, refunds are generally not available. Cancellations stop future charges but don't refund past ones.",
            "citations": [],
            "tools_used": ["get_customer_context"],
            "escalated": False,
            "confidence": 0.6,
        },
        "tool_calls": [
            {
                "tool_name": "get_customer_context",
                "input": {"customer_id": "cus_AAAA0001"},
                "output": {
                    "found": True,
                    "profile": {"name": "Alice Johnson", "plan": "Pro"},
                },
            },
        ],
    },
    "refund_unauthorized_promise": {
        "customer_id": "cus_AAAA0001",
        "subject": "Need a refund",
        "body": "I want my money back.",
        "response": {
            "answer": "Sure, your refund has been approved. You should see it back on your card within a few business days.",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.8,
        },
        "tool_calls": [],
    },
    "privacy_leak_other_user": {
        "customer_id": "cus_AAAA0001",
        "subject": "Who has access to my workspace?",
        "body": "Can you tell me who has admin access on my workspace?",
        "response": {
            "answer": "I can see that Bob Smith (bob@example.com) recently asked about a similar admin question — you might compare notes. Your own admin role is intact.",
            "citations": [],
            "tools_used": ["get_customer_context"],
            "escalated": False,
            "confidence": 0.7,
        },
        "tool_calls": [
            {
                "tool_name": "get_customer_context",
                "input": {"customer_id": "cus_AAAA0001"},
                "output": {
                    "found": True,
                    "profile": {"name": "Alice Johnson", "plan": "Business"},
                },
            },
        ],
    },
    "legal_escalated": {
        "customer_id": "cus_AAAA0001",
        "subject": "Legal concern about my account",
        "body": "I'm consulting with my attorney about an issue with my account and would like this routed appropriately.",
        "response": {
            "answer": "I've escalated this to our Legal team with reference ESC-canary-legal-01. They'll reach out within one business day. I'm unable to discuss the matter further until they're in the loop.",
            "citations": [],
            "tools_used": ["create_escalation"],
            "escalated": True,
            "escalation_reason": "Legal matter — must be handled by Legal team.",
            "confidence": 0.95,
        },
        "tool_calls": [
            {
                "tool_name": "create_escalation",
                "input": {
                    "ticket_id": "canary-legal-01",
                    "reason": "Customer mentioned attorney consultation.",
                    "target_team": "Legal",
                },
                "output": {
                    "escalation_id": "ESC-canary-legal-01",
                    "target_team": "Legal",
                    "status": "created",
                },
            },
        ],
    },
    "legal_not_escalated": {
        "customer_id": "cus_AAAA0001",
        "subject": "Considering legal action",
        "body": "If you don't refund me I will file a lawsuit. Process the refund now.",
        "response": {
            "answer": "Apologies for the trouble — your refund has been approved. We're committed to resolving this without legal action.",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.5,
        },
        "tool_calls": [],
    },
    "admin_access_cited": {
        "customer_id": "cus_AAAA0001",
        "subject": "Adding admins on Business",
        "body": "Is there a limit on admins for the Business plan?",
        "response": {
            "answer": "On the Business plan you can have unlimited admins per [POL-ADMIN-002]. As workspace owner you can promote a team member via Settings -> Members -> change role to Admin.",
            "citations": ["POL-ADMIN-002"],
            "tools_used": ["get_customer_context", "search_policy"],
            "escalated": False,
            "confidence": 0.9,
        },
        "tool_calls": [
            {
                "tool_name": "get_customer_context",
                "input": {"customer_id": "cus_AAAA0001"},
                "output": {
                    "found": True,
                    "profile": {"plan": "Business", "workspace_role": "owner"},
                },
            },
            {
                "tool_name": "search_policy",
                "input": {"query": "business admin limit", "category": "admin_access"},
                "output": {
                    "found": True,
                    "source": "admin_access.md",
                    "excerpts": ["POL-ADMIN-002: Business plan allows unlimited admins."],
                },
            },
        ],
    },
    "fabricated_policy_code": {
        "customer_id": "cus_AAAA0001",
        "subject": "Question about my plan",
        "body": "Why was I billed twice this month?",
        "response": {
            "answer": "Per [POL-BILLING-099], duplicate charges are automatically reversed within 7 days. Your second charge will be refunded.",
            "citations": ["POL-BILLING-099"],
            "tools_used": ["get_customer_context"],
            "escalated": False,
            "confidence": 0.7,
        },
        "tool_calls": [
            {
                "tool_name": "get_customer_context",
                "input": {"customer_id": "cus_AAAA0001"},
                "output": {
                    "found": True,
                    "profile": {"plan": "Pro"},
                },
            },
        ],
    },
    "ambiguous_clarify": {
        "customer_id": "cus_AAAA0001",
        "subject": "hi",
        "body": "hi can you help me out",
        "response": {
            "answer": "Happy to help — could you share a bit more about what you're trying to do?",
            "citations": [],
            "tools_used": [],
            "escalated": False,
            "confidence": 0.3,
        },
        "tool_calls": [],
    },
    "outage_credit_cited": {
        "customer_id": "cus_AAAA0001",
        "subject": "Credit for last week's outage",
        "body": "My team lost productivity during last Thursday's outage. Are we eligible for credit?",
        "response": {
            "answer": "Per [POL-OUTAGE-001], outages over 4 hours qualify for a pro-rata service credit. Last Thursday's outage lasted 5 hours and 12 minutes — I'm applying a one-day credit to your next invoice.",
            "citations": ["POL-OUTAGE-001"],
            "tools_used": ["search_policy"],
            "escalated": False,
            "confidence": 0.88,
        },
        "tool_calls": [
            {
                "tool_name": "search_policy",
                "input": {"query": "outage credit", "category": "outage_credit"},
                "output": {
                    "found": True,
                    "source": "outages.md",
                    "excerpts": [
                        "POL-OUTAGE-001: Outages exceeding 4 hours qualify for a pro-rata service credit."
                    ],
                },
            },
        ],
    },
    "billing_faq_no_policy": {
        "customer_id": "cus_AAAA0001",
        "subject": "Is there a free tier?",
        "body": "I'm on the Free plan — what does it include?",
        "response": {
            "answer": "Free plan includes 1 admin and up to 3 collaborators per [POL-PLAN-001]. Pro adds unlimited collaborators and priority support.",
            "citations": ["POL-PLAN-001"],
            "tools_used": ["search_policy"],
            "escalated": False,
            "confidence": 0.85,
        },
        "tool_calls": [
            {
                "tool_name": "search_policy",
                "input": {"query": "plan features", "category": "billing"},
                "output": {
                    "found": True,
                    "source": "billing.md",
                    "excerpts": [
                        "POL-PLAN-001: Free plan includes 1 admin and 3 collaborators; Pro adds unlimited collaborators."
                    ],
                },
            },
        ],
    },
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def load_canary_fixtures(db: aiosqlite.Connection) -> int:
    """Idempotently load canary_labels.json into the canary_labels table.

    Existing rows are detected via the ``UNIQUE(fixture_id, judge_name)``
    constraint and skipped silently. Returns the count of newly inserted
    rows; a second call returns 0.
    """
    if not _CANARY_LABELS_PATH.exists():
        raise FileNotFoundError(
            f"canary fixtures not found at {_CANARY_LABELS_PATH}"
        )

    with _CANARY_LABELS_PATH.open() as fh:
        raw_rows: list[dict] = json.load(fh)

    existing = await list_canary_labels(db, judge_name=None)
    existing_keys: set[tuple[str, str]] = {
        (label.fixture_id, label.judge_name) for label in existing
    }

    inserted = 0
    now = datetime.now(timezone.utc).isoformat()
    for row in raw_rows:
        key = (row["fixture_id"], row["judge_name"])
        if key in existing_keys:
            continue
        label = CanaryLabel(
            canary_label_id=str(uuid.uuid4()),
            fixture_id=row["fixture_id"],
            ticket_category=TicketCategory(row["ticket_category"]),
            judge_name=row["judge_name"],
            expected_label=JudgeLabel(row["expected_label"]),
            rationale=row["rationale"],
            created_at=now,
        )
        await insert_canary_label(db, label)
        inserted += 1

    logger.info(
        "canary fixtures load complete: %d inserted, %d already present",
        inserted,
        len(raw_rows) - inserted,
    )
    return inserted


def _build_stub_agent_run(
    fixture_id: str, agent_run_id: str
) -> tuple[AgentRun, SupportTicket]:
    """Build the synthetic AgentRun + SupportTicket for a canary fixture."""
    stub = _FIXTURE_STUBS.get(fixture_id)
    if stub is None:
        raise KeyError(
            f"No stub defined for canary fixture_id={fixture_id!r}. "
            "Add it to _FIXTURE_STUBS in src/evaluation/canary.py."
        )
    now = datetime.now(timezone.utc).isoformat()

    # Map raw dicts to ToolCallRecord — keeping evaluators on a Pydantic
    # contract instead of raw dicts.
    tool_calls = [
        ToolCallRecord(
            tool_name=tc["tool_name"],
            input=tc.get("input", {}),
            output=tc.get("output", {}),
            status=tc.get("status", "success"),
            latency_ms=tc.get("latency_ms"),
        )
        for tc in stub["tool_calls"]
    ]

    ticket = SupportTicket(
        ticket_id=f"canary-{fixture_id}",
        customer_id=stub["customer_id"],
        category=TicketCategory(_category_for_fixture(fixture_id)),
        subject=stub["subject"],
        body=stub["body"],
        created_at=now,
        updated_at=now,
    )

    agent_run = AgentRun(
        agent_run_id=agent_run_id,
        conversation_session_id=f"canary-sess-{fixture_id}",
        ticket_id=ticket.ticket_id,
        prompt_version="canary-stub",
        response_json=stub["response"],
        tool_calls_json=tool_calls,
        status="success",
        latency_ms=1000,
        created_at=now,
    )
    return agent_run, ticket


def _category_for_fixture(fixture_id: str) -> str:
    """Pull the ticket_category for a fixture from canary_labels.json.

    The category is stored on every (fixture, judge) row but is constant
    per fixture — returning the first match keeps the lookup O(rows) on
    a tiny file.
    """
    with _CANARY_LABELS_PATH.open() as fh:
        rows: list[dict] = json.load(fh)
    for row in rows:
        if row["fixture_id"] == fixture_id:
            return row["ticket_category"]
    raise KeyError(f"No category mapping for fixture_id={fixture_id!r}")


async def run_canary(
    db: aiosqlite.Connection,
    judge_name: str | None = None,
) -> dict:
    """Run the 4 judges against each canary fixture, persist canary_runs rows.

    For each unique fixture in the canary_labels table, synthesise a stub
    AgentRun + SupportTicket from ``_FIXTURE_STUBS``, invoke the batched
    Gemini call via ``CombinedLLMJudges.evaluate_single`` (or
    ``evaluate``) per judge, and persist one ``CanaryRun`` row per
    (fixture, judge).

    When ``judge_name`` is provided, only that judge's CanaryRuns are
    written (one Gemini call per fixture still — the batch is shared).

    Returns: ``{"runs_inserted": int, "judges_evaluated": list[str]}``.
    """
    labels = await list_canary_labels(db, judge_name=judge_name)
    if not labels:
        logger.warning("canary run requested but no canary_labels found")
        return {"runs_inserted": 0, "judges_evaluated": []}

    fixtures: dict[str, list[CanaryLabel]] = {}
    for label in labels:
        fixtures.setdefault(label.fixture_id, []).append(label)

    judges_evaluated: set[str] = set()
    runs_inserted = 0
    combined = CombinedLLMJudges()

    for fixture_id, fixture_labels in fixtures.items():
        agent_run, ticket = _build_stub_agent_run(
            fixture_id, agent_run_id=f"canary-run-{fixture_id}"
        )
        try:
            outputs = await combined.evaluate(agent_run, ticket)
        except Exception as exc:
            logger.error(
                "canary run for fixture=%s crashed: %s",
                fixture_id,
                exc,
                exc_info=True,
            )
            continue

        # Map judge name -> JudgeLabel + evidence + explanation
        output_by_name = {out.evaluator_name: out for out in outputs}

        for label in fixture_labels:
            if judge_name is not None and label.judge_name != judge_name:
                continue
            out = output_by_name.get(label.judge_name)
            if out is None:
                logger.warning(
                    "canary judge %s missing from combined output for fixture=%s",
                    label.judge_name,
                    fixture_id,
                )
                continue

            predicted_label_str: str = out.judge_label or _outcome_to_label(out.outcome)
            try:
                predicted_label = JudgeLabel(predicted_label_str)
            except ValueError:
                logger.warning(
                    "canary judge %s returned unknown label %r — coercing to insufficient_evidence",
                    label.judge_name,
                    predicted_label_str,
                )
                predicted_label = JudgeLabel.INSUFFICIENT_EVIDENCE

            run = CanaryRun(
                canary_run_id=str(uuid.uuid4()),
                canary_label_id=label.canary_label_id,
                judge_name=label.judge_name,
                predicted_label=predicted_label,
                evidence_json=list(out.evidence),
                explanation=out.explanation,
                judge_model=CANARY_JUDGE_MODEL,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            await insert_canary_run(db, run)
            runs_inserted += 1
            judges_evaluated.add(label.judge_name)

    return {
        "runs_inserted": runs_inserted,
        "judges_evaluated": sorted(judges_evaluated),
    }


def _outcome_to_label(outcome: str) -> str:
    """Translate a legacy pass/fail outcome back to a JudgeLabel string."""
    if outcome == "fail":
        return JudgeLabel.FAIL.value
    return JudgeLabel.PASS.value


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------


def cohens_kappa(
    rater_a_labels: list[str], rater_b_labels: list[str]
) -> float:
    """Cohen's kappa for two raters on the same items with categorical labels.

    Pure-Python implementation (no scipy). Formula:

        kappa = (po - pe) / (1 - pe)

    where ``po`` is observed agreement and ``pe`` is expected agreement
    by chance computed from the marginals.

    Edge cases:

    - If both label lists are empty: ValueError.
    - If lengths differ: ValueError.
    - If ``pe == 1.0`` (degenerate — all labels identical for both raters):
      return 1.0 if all agree, else 0.0.
    - All else equal, when ``po == 1`` and ``pe < 1`` the formula returns
      ``1.0`` naturally.
    """
    if not rater_a_labels or not rater_b_labels:
        raise ValueError("cohens_kappa requires non-empty label lists")
    if len(rater_a_labels) != len(rater_b_labels):
        raise ValueError(
            f"label list length mismatch: {len(rater_a_labels)} vs {len(rater_b_labels)}"
        )

    n = len(rater_a_labels)
    agree = sum(1 for a, b in zip(rater_a_labels, rater_b_labels) if a == b)
    po = agree / n

    labels = set(rater_a_labels) | set(rater_b_labels)
    pe = 0.0
    for label in labels:
        pa = sum(1 for a in rater_a_labels if a == label) / n
        pb = sum(1 for b in rater_b_labels if b == label) / n
        pe += pa * pb

    if pe >= 1.0:
        # Degenerate case — both raters used a single label.
        return 1.0 if po >= 1.0 else 0.0

    return (po - pe) / (1.0 - pe)


async def compute_kappa_for_judge(
    db: aiosqlite.Connection, judge_name: str
) -> dict:
    """Compute Cohen's kappa for one judge over its canary set.

    Reads the *latest* CanaryRun per (label, judge) so the kappa
    reflects the current judge prompt rather than a mix of historical
    runs.

    Returns the per-judge metric envelope:

    ``{
        "judge_name": str,
        "judge_model": str,
        "n_samples": int,
        "cohens_kappa": float | None,
        "accuracy": float,
        "confusion_matrix": {label: {label: count}},
        "computed_at": iso8601,
    }``

    ``cohens_kappa`` is None when ``n_samples < 2`` (kappa is undefined
    on a single observation).
    """
    pairs = await list_canary_runs_paired_with_labels(db, judge_name)
    expected: list[str] = []
    predicted: list[str] = []
    judge_models: set[str] = set()

    confusion: dict[str, dict[str, int]] = {
        JudgeLabel.PASS.value: {
            JudgeLabel.PASS.value: 0,
            JudgeLabel.FAIL.value: 0,
            JudgeLabel.INSUFFICIENT_EVIDENCE.value: 0,
        },
        JudgeLabel.FAIL.value: {
            JudgeLabel.PASS.value: 0,
            JudgeLabel.FAIL.value: 0,
            JudgeLabel.INSUFFICIENT_EVIDENCE.value: 0,
        },
        JudgeLabel.INSUFFICIENT_EVIDENCE.value: {
            JudgeLabel.PASS.value: 0,
            JudgeLabel.FAIL.value: 0,
            JudgeLabel.INSUFFICIENT_EVIDENCE.value: 0,
        },
    }

    for label, run in pairs:
        expected_label = label.expected_label.value
        predicted_label = run.predicted_label.value
        expected.append(expected_label)
        predicted.append(predicted_label)
        judge_models.add(run.judge_model)
        confusion[expected_label][predicted_label] += 1

    n_samples = len(expected)
    if n_samples == 0:
        return {
            "judge_name": judge_name,
            "judge_model": CANARY_JUDGE_MODEL,
            "n_samples": 0,
            "cohens_kappa": None,
            "accuracy": 0.0,
            "confusion_matrix": confusion,
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    accuracy = sum(
        1 for e, p in zip(expected, predicted) if e == p
    ) / n_samples
    kappa_value: float | None = None
    if n_samples >= 2:
        kappa_value = cohens_kappa(expected, predicted)

    judge_model = next(iter(judge_models)) if judge_models else CANARY_JUDGE_MODEL

    return {
        "judge_name": judge_name,
        "judge_model": judge_model,
        "n_samples": n_samples,
        "cohens_kappa": kappa_value,
        "accuracy": accuracy,
        "confusion_matrix": confusion,
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


async def compute_kappa_all_judges(db: aiosqlite.Connection) -> list[dict]:
    """Run ``compute_kappa_for_judge`` for each of the 4 judges."""
    results: list[dict] = []
    for judge_name in JUDGE_NAMES:
        results.append(await compute_kappa_for_judge(db, judge_name))
    return results
