"""Experiment orchestrator — runs baseline vs candidate prompts end-to-end.

This used to be a placeholder that called ``phoenix_client.experiments.run_experiment``
with ``dry_run=True`` and returned simulated metrics. The UI showed zeros.

The real flow now:
  1. Resolve the baseline and candidate prompt texts (from the trigger's
     patch proposal + the local prompts table).
  2. Load up to ``MAX_EXAMPLES`` dataset examples — Phoenix dataset
     ``regression-{failure_key}`` first, the trigger's example tickets next,
     a generic recent-tickets sample last. 5 is the cap because each example
     costs two agent runs; at 5 you spend 10 Gemini calls per experiment.
  3. Run the support agent against each example TWICE — once with the
     baseline prompt, once with the candidate. Tag each invocation's
     ``gemini_call_purpose`` so the seed-phase token audit can grep by
     purpose and verify the budget.
  4. Score each run with the DETERMINISTIC code-eval stack only.
     LLM judges are intentionally skipped here — at 5 examples per side the
     judges' noise dominates the signal AND they would double the experiment
     Gemini call count from 10 to 20. The release_score is the mean of
     per-evaluator pass scores, averaged across tickets.
  5. Persist the per-evaluator breakdown in ``eval_summary_json`` so the
     UI's scoreboard has real numbers to render.
"""

import asyncio
import logging
import statistics
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol

from phoenix.client import Client
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    import aiosqlite

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
from src.models import (
    AgentRun,
    ExperimentRecord,
    ExperimentStatus,
    ImprovementTrigger,
    RegressionExample,
    SupportTicket,
)

logger = logging.getLogger(__name__)


# At 5 examples per side the experiment costs ~10 Gemini calls; doubling
# this would blow past the seed-phase budget. The cap is enforced both
# here and in the dataset-loading helper.
MAX_EXAMPLES = 5

CODE_EVALUATOR_CLASSES: list[type[BaseEvaluator]] = [
    SchemaValidityEvaluator,
    ToolSequenceEvaluator,
    RefundGuardEvaluator,
    PrivacyGuardEvaluator,
    EscalationGuardEvaluator,
    CitationPresenceEvaluator,
    LatencyBudgetEvaluator,
]

# Evaluators whose failure indicates a CRITICAL outcome — used for the
# critical_failure_rate metric. Latency / schema regressions are real but
# not show-stoppers in the same way refund/privacy/escalation breaches are.
CRITICAL_EVALUATOR_NAMES = {"refund_guard", "privacy_guard", "escalation_guard"}


# ---------------------------------------------------------------------------
# Protocols — duck-typing interfaces per CLAUDE.md (no bare ``Any`` types)
# ---------------------------------------------------------------------------


class PhoenixMCPProtocol(Protocol):
    """Duck-typing protocol for the PhoenixMCPClient dependency."""

    async def read_production_prompt(self) -> object | None: ...

    async def get_dataset(self, dataset_name: str) -> list[object]: ...

    async def read_experiment_results(
        self, experiment_id: str
    ) -> object | None: ...

    async def log_experiment_runs(
        self,
        *,
        phoenix_experiment_id: str,
        per_example: list[dict],
    ) -> bool: ...


# ---------------------------------------------------------------------------
# Typed metrics container
# ---------------------------------------------------------------------------


class ExperimentMetrics(BaseModel):
    """Typed container for experiment comparison metrics.

    Mirrors the columns persisted on ``experiments`` so the orchestrator
    can build the ``ExperimentRecord`` from a single object instead of
    juggling parallel dicts.
    """

    baseline_release_score: float = 0.0
    candidate_release_score: float = 0.0
    baseline_critical_failure_rate: float = 0.0
    candidate_critical_failure_rate: float = 0.0
    baseline_latency_p50_ms: int = 0
    candidate_latency_p50_ms: int = 0
    baseline_hallucination_rate: float | None = None
    candidate_hallucination_rate: float | None = None
    regression_cases_pass_rate: float = 0.0
    safety_canary_pass_rate: float = 0.0
    eval_summary: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def run_experiment(
    trigger: ImprovementTrigger,
    phoenix_client: Client | None,
    mcp_client: PhoenixMCPProtocol,
    db: "aiosqlite.Connection | None" = None,
) -> ExperimentRecord:
    """Run baseline vs candidate end-to-end and return a populated ExperimentRecord.

    Args:
        trigger: The improvement trigger whose patch is being tested.
        phoenix_client: Phoenix Client (instrumentation only — no longer used
            for ``experiments.run_experiment``; agent runs trace themselves).
        mcp_client: PhoenixMCPClient for reading the candidate prompt and the
            regression dataset.
        db: Required. The aiosqlite connection used to read the local
            baseline prompt + the failing tickets and to persist nothing
            (the experiment doesn't write to the main agent_runs table —
            those would pollute the activity feed with synthetic runs).
    """
    experiment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    if db is None:
        raise ValueError(
            "run_experiment requires a db connection — needed to resolve "
            "the active baseline prompt and to load failing tickets."
        )

    baseline_template, baseline_label, baseline_version_id = (
        await _resolve_baseline_prompt(db, mcp_client)
    )
    candidate_template, candidate_label, candidate_version_id = (
        await _resolve_candidate_prompt(db, trigger)
    )

    if not candidate_template:
        logger.warning(
            "Experiment %s has no candidate prompt — running baseline only. "
            "The release gate will reject (score delta = 0).",
            experiment_id,
        )
        candidate_template = baseline_template

    examples = await _load_dataset_examples(trigger, mcp_client, db)
    dataset_name = _dataset_id_for_trigger(trigger)
    logger.info(
        "Experiment %s: %d examples (cap=%d) loaded from %s",
        experiment_id, len(examples), MAX_EXAMPLES, dataset_name,
    )

    if not examples:
        logger.warning(
            "Experiment %s has no dataset examples — recording an empty result",
            experiment_id,
        )
        return _build_empty_record(
            experiment_id=experiment_id,
            trigger=trigger,
            baseline_label=baseline_label,
            candidate_label=candidate_label,
            dataset_name=dataset_name,
            baseline_version_id=baseline_version_id,
            candidate_version_id=candidate_version_id,
            created_at=now,
        )

    baseline_pairs = await _run_agent_on_examples(
        examples=examples,
        prompt_text=baseline_template,
        prompt_label=baseline_label,
        purpose="experiment_baseline",
        db=db,
    )
    candidate_pairs = await _run_agent_on_examples(
        examples=examples,
        prompt_text=candidate_template,
        prompt_label=candidate_label,
        purpose="experiment_candidate",
        db=db,
    )

    baseline_per_eval = await _score_runs(baseline_pairs)
    candidate_per_eval = await _score_runs(candidate_pairs)

    metrics = _aggregate_metrics(
        baseline_runs=[run for _, run in baseline_pairs],
        candidate_runs=[run for _, run in candidate_pairs],
        baseline_per_eval=baseline_per_eval,
        candidate_per_eval=candidate_per_eval,
    )

    baseline_payload = _build_phoenix_payload(
        pairs=baseline_pairs,
        per_eval=baseline_per_eval,
    )
    candidate_payload = _build_phoenix_payload(
        pairs=candidate_pairs,
        per_eval=candidate_per_eval,
    )

    from src.db import get_phoenix_dataset_id_for_trigger

    phoenix_dataset_id = await get_phoenix_dataset_id_for_trigger(
        db, trigger.improvement_trigger_id
    )
    phoenix_baseline_id, phoenix_candidate_id = await _mint_phoenix_experiment_ids(
        phoenix_client=phoenix_client,
        trigger=trigger,
        experiment_id=experiment_id,
        phoenix_dataset_id=phoenix_dataset_id,
        baseline_label=baseline_label,
        candidate_label=candidate_label,
    )

    if not phoenix_baseline_id.startswith("local-"):
        await mcp_client.log_experiment_runs(
            phoenix_experiment_id=phoenix_baseline_id,
            per_example=baseline_payload,
        )
    if not phoenix_candidate_id.startswith("local-"):
        await mcp_client.log_experiment_runs(
            phoenix_experiment_id=phoenix_candidate_id,
            per_example=candidate_payload,
        )

    record = ExperimentRecord(
        experiment_id=experiment_id,
        improvement_trigger_id=trigger.improvement_trigger_id,
        baseline_prompt_version=baseline_label,
        candidate_prompt_version=candidate_label,
        dataset_id=dataset_name,
        phoenix_experiment_id_baseline=phoenix_baseline_id,
        phoenix_experiment_id_candidate=phoenix_candidate_id,
        status=ExperimentStatus.COMPLETED,
        baseline_release_score=metrics.baseline_release_score,
        candidate_release_score=metrics.candidate_release_score,
        baseline_critical_failure_rate=metrics.baseline_critical_failure_rate,
        candidate_critical_failure_rate=metrics.candidate_critical_failure_rate,
        baseline_latency_p50_ms=metrics.baseline_latency_p50_ms,
        candidate_latency_p50_ms=metrics.candidate_latency_p50_ms,
        baseline_hallucination_rate=metrics.baseline_hallucination_rate,
        candidate_hallucination_rate=metrics.candidate_hallucination_rate,
        regression_cases_pass_rate=metrics.regression_cases_pass_rate,
        safety_canary_pass_rate=metrics.safety_canary_pass_rate,
        eval_summary_json=metrics.eval_summary,
        started_at=now,
        completed_at=datetime.now(timezone.utc).isoformat(),
        baseline_prompt_version_id=baseline_version_id,
        candidate_prompt_version_id=candidate_version_id,
        created_at=now,
    )

    logger.info(
        "Experiment %s complete: baseline=%.3f candidate=%.3f delta=%+.3f",
        experiment_id,
        record.baseline_release_score or 0.0,
        record.candidate_release_score or 0.0,
        (record.candidate_release_score or 0.0) - (record.baseline_release_score or 0.0),
    )

    return record


# ---------------------------------------------------------------------------
# Phoenix experiment record minting
# ---------------------------------------------------------------------------


async def _mint_phoenix_experiment_ids(
    *,
    phoenix_client: Client | None,
    trigger: ImprovementTrigger,
    experiment_id: str,
    phoenix_dataset_id: str | None,
    baseline_label: str,
    candidate_label: str,
) -> tuple[str, str]:
    """Create real Phoenix experiment records for the baseline and candidate sides.

    The local harness above already ran the agent against each example and
    scored it deterministically — those AgentRun spans are emitted to Phoenix
    via OpenInference and carry the ticket_id/category/prompt_version_id
    business attributes set in support_agent.run_agent_events. This helper
    additionally creates two Phoenix-side ``Experiment`` records via
    ``client.experiments.create(dataset_id=...)`` so the experiment shows up
    in the Phoenix Cloud UI's Experiments tab with the dataset linkage and a
    metadata blob pointing back to the local experiment_id / trigger.

    The caller passes the Phoenix dataset_id captured at dataset-creation
    time (persisted on ``regression_examples.phoenix_dataset_id``). Looking
    the dataset up by name is unsafe: Phoenix slugifies names containing
    characters like ``::`` so ``regression-{failure_key}`` round-trips to a
    hex slug we cannot derive client-side.

    Falls back to ``local-*`` stub IDs when:
      - the Phoenix client is missing (offline or PHOENIX_API_KEY unset),
      - the regression dataset hasn't been promoted to Phoenix yet
        (``phoenix_dataset_id is None``),
      - the SDK doesn't expose ``experiments.create`` on the pinned version,
      - any network or HTTP error surfaces.
    """
    fallback = (
        f"local-baseline-{experiment_id[:8]}",
        f"local-candidate-{experiment_id[:8]}",
    )

    if phoenix_client is None or not phoenix_dataset_id:
        return fallback

    def _create() -> tuple[str, str] | None:
        base_metadata = {
            "phoenixloop_experiment_id": experiment_id,
            "improvement_trigger_id": trigger.improvement_trigger_id,
            "failure_key": trigger.failure_key,
        }

        try:
            baseline_exp = phoenix_client.experiments.create(
                dataset_id=phoenix_dataset_id,
                experiment_name=f"phoenixloop-baseline-{experiment_id[:8]}",
                experiment_description=(
                    f"Baseline run for trigger {trigger.improvement_trigger_id}"
                ),
                experiment_metadata={
                    **base_metadata,
                    "side": "baseline",
                    "prompt_version": baseline_label,
                },
            )
            candidate_exp = phoenix_client.experiments.create(
                dataset_id=phoenix_dataset_id,
                experiment_name=f"phoenixloop-candidate-{experiment_id[:8]}",
                experiment_description=(
                    f"Candidate run for trigger {trigger.improvement_trigger_id}"
                ),
                experiment_metadata={
                    **base_metadata,
                    "side": "candidate",
                    "prompt_version": candidate_label,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to create Phoenix experiment records (%s) — using local stubs",
                exc,
            )
            return None

        baseline_id = str(baseline_exp.get("id") if isinstance(baseline_exp, dict) else getattr(baseline_exp, "id", "") or "")
        candidate_id = str(candidate_exp.get("id") if isinstance(candidate_exp, dict) else getattr(candidate_exp, "id", "") or "")
        if not baseline_id or not candidate_id:
            return None
        return baseline_id, candidate_id

    try:
        result = await asyncio.to_thread(_create)
    except Exception as exc:
        logger.warning(
            "asyncio.to_thread(_create) failed for Phoenix experiment minting: %s",
            exc,
        )
        return fallback

    if result is None:
        return fallback
    logger.info(
        "Created Phoenix experiments: baseline=%s candidate=%s (dataset_id=%s)",
        result[0],
        result[1],
        phoenix_dataset_id,
    )
    return result


# ---------------------------------------------------------------------------
# Prompt resolution
# ---------------------------------------------------------------------------


async def _resolve_baseline_prompt(
    db: "aiosqlite.Connection",
    mcp_client: PhoenixMCPProtocol,
) -> tuple[str, str, str | None]:
    """Return (prompt_text, label, version_id) for the current production prompt."""
    from src.agent.prompts import get_production_prompt
    from src.db import get_prompt

    prompt_text, prompt_version_id = await get_production_prompt(db)
    active = await get_prompt(db, "support-agent")
    version_label = "production"
    if active and active.active_version_id:
        from src.db import get_prompt_version

        version = await get_prompt_version(db, active.active_version_id)
        if version:
            version_label = version.version_tag

    if prompt_text:
        return prompt_text, version_label, prompt_version_id

    # Last-resort fallback via MCP — only fires if the local DB is empty,
    # which would itself be a seed bug. Logged loudly so it doesn't hide.
    logger.warning("Local production prompt is empty — falling back to MCP")
    mcp_prompt = await mcp_client.read_production_prompt()
    template = str(getattr(mcp_prompt, "template", "") or "")
    return template, version_label, prompt_version_id


async def _resolve_candidate_prompt(
    db: "aiosqlite.Connection",
    trigger: ImprovementTrigger,
) -> tuple[str, str, str | None]:
    """Return (prompt_text, label, version_id) for the trigger's candidate.

    The candidate prompt comes from ``generate_proposal()`` which writes a
    new ``prompt_versions`` row and stamps its id onto
    ``trigger.patch_proposal_json['local_prompt_version_id']``.
    """
    from src.db import get_prompt_version

    proposal = trigger.patch_proposal_json or {}
    # ``candidate_prompt_version`` from the proposal carries the *Phoenix*
    # prompt-version id (base64-encoded) when generate_proposal succeeded
    # in upserting to Phoenix. We want to preserve that for the release-gate
    # approve path so it can tag the right Phoenix version as ``production``.
    # The local ``version_tag`` (human-readable slug) is only useful for UI
    # display and is the wrong identifier for the Phoenix tags API.
    phoenix_candidate_version = str(
        proposal.get("candidate_prompt_version") or ""
    ).strip()
    candidate_label = phoenix_candidate_version or "candidate"
    candidate_version_id = proposal.get("local_prompt_version_id")

    if candidate_version_id:
        version = await get_prompt_version(db, str(candidate_version_id))
        if version:
            label = phoenix_candidate_version or version.version_tag
            return version.prompt_text, label, version.prompt_version_id

    # If the proposal embedded the full text (older shape), use that.
    candidate_text = (
        proposal.get("candidate_prompt_text")
        or proposal.get("proposed_change")
        or ""
    )
    return str(candidate_text), candidate_label, candidate_version_id


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------


def _dataset_id_for_trigger(trigger: ImprovementTrigger) -> str:
    return f"regression-{trigger.failure_key}"


async def _load_dataset_examples(
    trigger: ImprovementTrigger,
    mcp_client: PhoenixMCPProtocol,
    db: "aiosqlite.Connection",
) -> list[SupportTicket]:
    """Return up to MAX_EXAMPLES SupportTickets to run the experiment against.

    Resolution order:
      1. Local ``regression_examples`` rows for this trigger (preferred — these
         are the synthesized tickets generated by ``generate_regression_examples``
         specifically targeting the failure mode under repair).
      2. Phoenix dataset ``regression-{failure_key}`` (legacy path; Phoenix
         server slugifies names containing ``::`` so this only works for
         simple failure_keys, but kept for completeness).
      3. The tickets referenced by the trigger's ``example_run_ids_json``
         (the actual failing examples).
      4. The 5 most-recent tickets in the local DB (generic sample).
    """
    from src.db import get_regression_examples_for_trigger

    regression_examples = await get_regression_examples_for_trigger(
        db, trigger.improvement_trigger_id
    )
    tickets = [
        _ticket_from_regression_example(ex)
        for ex in regression_examples[:MAX_EXAMPLES]
    ]
    if tickets:
        return tickets

    dataset_name = _dataset_id_for_trigger(trigger)
    try:
        phoenix_examples = await mcp_client.get_dataset(dataset_name)
    except Exception as exc:
        logger.warning(
            "Phoenix dataset %s lookup failed (%s) — trying local fallbacks",
            dataset_name, exc,
        )
        phoenix_examples = []

    for ex in (phoenix_examples or [])[:MAX_EXAMPLES]:
        ticket = _ticket_from_dataset_example(ex)
        if ticket is not None:
            tickets.append(ticket)
    if tickets:
        return tickets

    if trigger.example_run_ids_json:
        tickets_from_runs = await _tickets_for_run_ids(
            db, trigger.example_run_ids_json[:MAX_EXAMPLES]
        )
        if tickets_from_runs:
            return tickets_from_runs

    return await _recent_tickets(db, MAX_EXAMPLES)


def _ticket_from_regression_example(ex: RegressionExample) -> SupportTicket:
    """Convert a stored RegressionExample row into a SupportTicket the
    agent runner can consume."""
    from src.models import TicketCategory

    payload = ex.input_ticket_json or {}
    body = str(payload.get("body", ""))
    category_raw = str(payload.get("category", "ambiguous")).lower()
    try:
        category = TicketCategory(category_raw)
    except ValueError:
        category = TicketCategory.AMBIGUOUS

    now_iso = datetime.now(timezone.utc).isoformat()
    return SupportTicket(
        ticket_id=f"exp-{ex.regression_example_id[:8]}",
        customer_id="cust-exp",
        category=category,
        subject="",
        body=body,
        metadata_json={
            "experiment_example_id": ex.regression_example_id,
            "expected_behavior": ex.expected_behavior,
            "failure_mode_targeted": ex.failure_mode_targeted,
        },
        created_at=now_iso,
        updated_at=now_iso,
    )


def _ticket_from_dataset_example(example: object) -> SupportTicket | None:
    """Best-effort coerce a Phoenix DatasetExample-shaped object into a ticket."""
    from src.models import TicketCategory

    inp = getattr(example, "input", None) or {}
    if isinstance(inp, dict):
        ticket_id = (
            inp.get("ticket_id")
            or str(getattr(example, "example_id", "") or uuid.uuid4().hex[:8])
        )
        category_raw = (inp.get("category") or "ambiguous").lower()
        try:
            category = TicketCategory(category_raw)
        except ValueError:
            category = TicketCategory.AMBIGUOUS

        now_iso = datetime.now(timezone.utc).isoformat()
        return SupportTicket(
            ticket_id=f"exp-{ticket_id}",
            customer_id=str(inp.get("customer_id", "cust-exp")),
            category=category,
            subject=str(inp.get("subject", "")),
            body=str(inp.get("body", "")),
            metadata_json={"experiment_example_id": str(ticket_id)},
            created_at=now_iso,
            updated_at=now_iso,
        )
    return None


async def _tickets_for_run_ids(
    db: "aiosqlite.Connection", run_ids: list[str]
) -> list[SupportTicket]:
    """Resolve a list of agent_run_ids to their underlying tickets."""
    from src.db import get_agent_run, get_ticket

    seen_ticket_ids: set[str] = set()
    tickets: list[SupportTicket] = []
    for run_id in run_ids:
        run = await get_agent_run(db, run_id)
        if run is None or run.ticket_id in seen_ticket_ids:
            continue
        seen_ticket_ids.add(run.ticket_id)
        ticket = await get_ticket(db, run.ticket_id)
        if ticket is not None:
            tickets.append(ticket)
        if len(tickets) >= MAX_EXAMPLES:
            break
    return tickets


async def _recent_tickets(
    db: "aiosqlite.Connection", limit: int
) -> list[SupportTicket]:
    from src.db import list_tickets

    tickets, _ = await list_tickets(db, category=None, page=1, page_size=limit)
    return tickets


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


async def _run_agent_on_examples(
    examples: list[SupportTicket],
    prompt_text: str,
    prompt_label: str,
    purpose: str,
    db: "aiosqlite.Connection",
) -> list[tuple[SupportTicket, AgentRun]]:
    """Run the support agent on each ticket with the given prompt.

    Each run is tagged ``gemini_call_purpose=purpose`` for the token audit.
    Runs are NOT persisted to the main agent_runs table — these are synthetic
    experiment runs and would clutter the activity feed.

    Returns ``(ticket, agent_run)`` pairs so the downstream eval scoring can
    use the ticket's real category instead of a stub.
    """
    from src.agent.support_agent import run_agent

    pairs: list[tuple[SupportTicket, AgentRun]] = []
    for idx, ticket in enumerate(examples):
        session_id = f"exp-{purpose}-{uuid.uuid4().hex[:8]}"
        try:
            run = await run_agent(
                ticket,
                session_id,
                db,
                phoenix_client=None,
                mcp_toolset=None,
                prompt_override=prompt_text,
                prompt_version_label=prompt_label,
                gemini_call_purpose=purpose,
            )
            pairs.append((ticket, run))
        except Exception as exc:
            logger.warning(
                "Experiment run failed (%s, example %d/%d): %s",
                purpose, idx + 1, len(examples), exc,
            )
    return pairs


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


async def _score_runs(
    pairs: list[tuple[SupportTicket, AgentRun]],
) -> dict[str, list[EvalOutput]]:
    """Score every run against the deterministic code-eval stack only.

    Returns ``{evaluator_name: [EvalOutput per run]}`` for downstream
    aggregation. Skips LLM judges and Phoenix tool evals — at the 5-example
    cap their variance dominates the signal and doubling Gemini cost is
    not worth it.
    """
    from src.evaluation.runner import _run_code_eval

    aggregated: dict[str, list[EvalOutput]] = {}
    for ticket, run in pairs:
        for eval_cls in CODE_EVALUATOR_CLASSES:
            evaluator = eval_cls()
            outputs = await _run_code_eval(evaluator, run, ticket)
            for out in outputs:
                aggregated.setdefault(out.evaluator_name, []).append(out)
    return aggregated


def _aggregate_metrics(
    *,
    baseline_runs: list[AgentRun],
    candidate_runs: list[AgentRun],
    baseline_per_eval: dict[str, list[EvalOutput]],
    candidate_per_eval: dict[str, list[EvalOutput]],
) -> ExperimentMetrics:
    """Roll up per-run code-eval outputs into the experiment metrics."""
    baseline_eval_summary = _per_eval_pass_rates(baseline_per_eval)
    candidate_eval_summary = _per_eval_pass_rates(candidate_per_eval)

    baseline_score = _mean(list(baseline_eval_summary.values()))
    candidate_score = _mean(list(candidate_eval_summary.values()))

    baseline_critical = _critical_failure_rate(baseline_per_eval, len(baseline_runs))
    candidate_critical = _critical_failure_rate(candidate_per_eval, len(candidate_runs))

    baseline_latency = _latency_p50(baseline_runs)
    candidate_latency = _latency_p50(candidate_runs)

    safety = _safety_canary_pass_rate(candidate_per_eval, len(candidate_runs))

    summary: dict[str, object] = {
        name: {
            "baseline": round(baseline_eval_summary.get(name, 0.0), 4),
            "candidate": round(candidate_eval_summary.get(name, 0.0), 4),
        }
        for name in sorted(set(baseline_eval_summary) | set(candidate_eval_summary))
    }
    summary["_meta"] = {
        "scoring": "code_evals_only",
        "examples_baseline": len(baseline_runs),
        "examples_candidate": len(candidate_runs),
        "hallucination_judging": (
            "skipped — code evals only in experiment hot path"
        ),
    }

    return ExperimentMetrics(
        baseline_release_score=round(baseline_score, 4),
        candidate_release_score=round(candidate_score, 4),
        baseline_critical_failure_rate=round(baseline_critical, 4),
        candidate_critical_failure_rate=round(candidate_critical, 4),
        baseline_latency_p50_ms=baseline_latency,
        candidate_latency_p50_ms=candidate_latency,
        baseline_hallucination_rate=None,
        candidate_hallucination_rate=None,
        regression_cases_pass_rate=round(candidate_score, 4),
        safety_canary_pass_rate=round(safety, 4),
        eval_summary=summary,
    )


def _build_phoenix_payload(
    *,
    pairs: list[tuple[SupportTicket, AgentRun]],
    per_eval: dict[str, list[EvalOutput]],
) -> list[dict]:
    """Shape the per-example results for ``log_experiment_runs``.

    The order of ``per_eval[name]`` mirrors the order of ``pairs`` — both are
    produced by walking ``pairs`` in the same loop in ``_score_runs``. We
    index into each evaluator's list by row position to assemble per-example
    evaluation rows.
    """
    rows: list[dict] = []
    for idx, (ticket, run) in enumerate(pairs):
        evals: list[dict] = []
        for name, outputs in per_eval.items():
            if idx >= len(outputs):
                continue
            out = outputs[idx]
            evals.append({
                "name": name,
                "score": out.score,
                "label": out.outcome,
                "explanation": out.explanation,
            })
        rows.append({
            "example_id": (
                ticket.metadata_json.get("experiment_example_id")
                if ticket.metadata_json
                else ticket.ticket_id
            ),
            "input": {
                "ticket_id": ticket.ticket_id,
                "subject": ticket.subject,
                "body": ticket.body,
                "category": ticket.category.value,
            },
            "output": run.response_json,
            "evaluations": evals,
            "latency_ms": run.latency_ms,
        })
    return rows


def _per_eval_pass_rates(
    per_eval: dict[str, list[EvalOutput]],
) -> dict[str, float]:
    rates: dict[str, float] = {}
    for name, outputs in per_eval.items():
        if not outputs:
            continue
        rates[name] = sum(1 for o in outputs if o.outcome == "pass") / len(outputs)
    return rates


def _critical_failure_rate(
    per_eval: dict[str, list[EvalOutput]], total_runs: int
) -> float:
    if total_runs == 0:
        return 0.0
    failures: set[int] = set()
    for name, outputs in per_eval.items():
        if name not in CRITICAL_EVALUATOR_NAMES:
            continue
        for idx, out in enumerate(outputs):
            if out.outcome != "pass":
                failures.add(idx)
    return len(failures) / total_runs


def _safety_canary_pass_rate(
    per_eval: dict[str, list[EvalOutput]], total_runs: int
) -> float:
    if total_runs == 0:
        return 1.0
    privacy = per_eval.get("privacy_guard", [])
    escalation = per_eval.get("escalation_guard", [])
    if not privacy and not escalation:
        return 1.0
    passes = 0
    for idx in range(total_runs):
        p_ok = idx >= len(privacy) or privacy[idx].outcome == "pass"
        e_ok = idx >= len(escalation) or escalation[idx].outcome == "pass"
        if p_ok and e_ok:
            passes += 1
    return passes / total_runs


def _latency_p50(runs: list[AgentRun]) -> int:
    values = [r.latency_ms for r in runs if r.latency_ms is not None]
    if not values:
        return 0
    return int(statistics.median(values))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# Empty-result shortcut
# ---------------------------------------------------------------------------


def _build_empty_record(
    *,
    experiment_id: str,
    trigger: ImprovementTrigger,
    baseline_label: str,
    candidate_label: str,
    dataset_name: str,
    baseline_version_id: str | None,
    candidate_version_id: str | None,
    created_at: str,
) -> ExperimentRecord:
    return ExperimentRecord(
        experiment_id=experiment_id,
        improvement_trigger_id=trigger.improvement_trigger_id,
        baseline_prompt_version=baseline_label,
        candidate_prompt_version=candidate_label,
        dataset_id=dataset_name,
        phoenix_experiment_id_baseline=None,
        phoenix_experiment_id_candidate=None,
        status=ExperimentStatus.COMPLETED,
        baseline_release_score=0.0,
        candidate_release_score=0.0,
        eval_summary_json={
            "_meta": {
                "scoring": "code_evals_only",
                "examples_baseline": 0,
                "examples_candidate": 0,
                "reason": "no dataset examples available",
            },
        },
        started_at=created_at,
        completed_at=created_at,
        baseline_prompt_version_id=baseline_version_id,
        candidate_prompt_version_id=candidate_version_id,
        created_at=created_at,
    )
