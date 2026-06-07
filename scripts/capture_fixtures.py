#!/usr/bin/env python
"""Capture the most recent live-seed run into the LIGHTWEIGHT_DEMO fixtures.

Opt-in only — nothing on the boot path invokes this. Run after you've done
a successful live seed and want to refresh the deterministic fixtures so
``LIGHTWEIGHT_DEMO=true`` reflects current schema / new tickets / new
diagnosis output.

Usage:
    python scripts/capture_fixtures.py --from-last-seed

What it does:
  1. Opens ``backend/phoenixloop.db``.
  2. Pulls the most-recent improvement trigger and walks its dependency
     graph backwards: experiment, release gate, candidate prompt version,
     regression examples, agent runs, eval results, tickets,
     conversation sessions, failure aggregate.
  3. Serializes each piece to JSON and overwrites the matching fixture
     file under ``backend/tests/fixtures/seed/``.
  4. Prints a one-line summary of what was overwritten.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BACKEND = _PROJECT_ROOT / "backend"
_FIXTURES_DIR = _BACKEND / "tests" / "fixtures" / "seed"

if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

logger = logging.getLogger(__name__)


async def _capture(db_path: Path) -> dict[str, int]:
    import aiosqlite

    from src.db import (
        get_agent_run,
        get_db,
        get_prompt_version,
        get_regression_examples_for_trigger,
        get_release_gate_for_experiment,
        get_ticket,
        list_experiments,
        list_improvement_triggers,
    )

    summary: dict[str, int] = {}
    async with get_db(str(db_path)) as db:
        # Most recent trigger.
        triggers, _ = await list_improvement_triggers(
            db, status=None, page=1, page_size=1
        )
        if not triggers:
            print("No improvement triggers in DB — run a live seed first.")
            return summary
        trigger = triggers[0]

        # Most recent experiment for that trigger.
        experiments, _ = await list_experiments(db, page=1, page_size=20)
        experiment = next(
            (
                e
                for e in experiments
                if e.improvement_trigger_id == trigger.improvement_trigger_id
            ),
            None,
        )
        gate = (
            await get_release_gate_for_experiment(db, experiment.experiment_id)
            if experiment
            else None
        )

        # Candidate prompt version (referenced by experiment OR by proposal).
        candidate_pv_id: str | None = None
        if experiment and experiment.candidate_prompt_version_id:
            candidate_pv_id = experiment.candidate_prompt_version_id
        elif trigger.patch_proposal_json:
            candidate_pv_id = trigger.patch_proposal_json.get(
                "local_prompt_version_id"
            )
        candidate_pv = (
            await get_prompt_version(db, candidate_pv_id) if candidate_pv_id else None
        )

        regression_examples = await get_regression_examples_for_trigger(
            db, trigger.improvement_trigger_id
        )

        # Walk back to runs referenced by the trigger.
        run_ids = list(trigger.example_run_ids_json or [])
        agent_runs = []
        ticket_ids: list[str] = []
        for rid in run_ids:
            run = await get_agent_run(db, rid)
            if run:
                agent_runs.append(run)
                if run.ticket_id not in ticket_ids:
                    ticket_ids.append(run.ticket_id)

        # Also grab the 4 most-recent passing runs so the fixtures retain
        # the "4 demo + 2 fail" shape the LIGHTWEIGHT_DEMO loader expects.
        async with aiosqlite.connect(str(db_path)) as raw:
            raw.row_factory = aiosqlite.Row
            cur = await raw.execute(
                "SELECT agent_run_id FROM agent_runs "
                "WHERE agent_run_id NOT IN "
                "(SELECT agent_run_id FROM eval_results WHERE outcome='fail') "
                "ORDER BY created_at DESC LIMIT 4"
            )
            for row in await cur.fetchall():
                run = await get_agent_run(db, row["agent_run_id"])
                if run and run not in agent_runs:
                    agent_runs.append(run)
                    if run.ticket_id not in ticket_ids:
                        ticket_ids.append(run.ticket_id)

        tickets = []
        for tid in ticket_ids:
            t = await get_ticket(db, tid)
            if t:
                tickets.append(t)

        # Eval results for all captured runs.
        eval_results = []
        for run in agent_runs:
            cur = await db.execute(
                "SELECT * FROM eval_results WHERE agent_run_id = ? ORDER BY created_at",
                (run.agent_run_id,),
            )
            for row in await cur.fetchall():
                eval_results.append(dict(row))

        # Failure aggregate keyed on the trigger's failure_key.
        cur = await db.execute(
            "SELECT * FROM failure_aggregates WHERE failure_key = ?",
            (trigger.failure_key,),
        )
        agg_row = await cur.fetchone()
        agg_dict = dict(agg_row) if agg_row else None

    # Serialize and write fixtures.
    _write_fixture(
        "tickets",
        [_json_safe(t.model_dump()) for t in tickets],
    )
    summary["tickets"] = len(tickets)

    _write_fixture(
        "agent_runs",
        [_json_safe(r.model_dump()) for r in agent_runs],
    )
    summary["agent_runs"] = len(agent_runs)

    _write_fixture(
        "eval_results",
        [_normalize_eval_row(row) for row in eval_results],
    )
    summary["eval_results"] = len(eval_results)

    if agg_dict:
        _write_fixture("failure_aggregate", _normalize_aggregate_row(agg_dict))
        summary["failure_aggregate"] = 1

    _write_fixture(
        "improvement_trigger",
        _json_safe(trigger.model_dump()),
    )
    if trigger.diagnosis_json:
        _write_fixture("diagnosis", trigger.diagnosis_json)
    if trigger.patch_proposal_json:
        _write_fixture("patch_proposal", trigger.patch_proposal_json)
    summary["improvement_trigger"] = 1

    if regression_examples:
        _write_fixture(
            "regression_examples",
            [_json_safe(e.model_dump()) for e in regression_examples],
        )
        summary["regression_examples"] = len(regression_examples)

    if candidate_pv:
        cpv = _json_safe(candidate_pv.model_dump())
        # Replace the prompt_text with a placeholder so we don't ship a
        # multi-thousand-character prompt in JSON — the loader composes
        # it from the live baseline + the patch's proposed_change.
        cpv["prompt_text"] = (
            "(see DEFAULT_SYSTEM_PROMPT plus the patch in patch_proposal.json — "
            "the seed loader composes the full text at insert time from the "
            "active production prompt + the diff)"
        )
        _write_fixture("prompt_version_candidate", cpv)
        summary["prompt_version_candidate"] = 1

    if experiment:
        _write_fixture("experiment", _json_safe(experiment.model_dump()))
        summary["experiment"] = 1

    if gate:
        _write_fixture("release_gate", _json_safe(gate.model_dump()))
        summary["release_gate"] = 1

    return summary


def _write_fixture(name: str, payload: object) -> None:
    path = _FIXTURES_DIR / f"{name}.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
    )


def _json_safe(payload: dict) -> dict:
    """Strip non-JSON-safe values (enum → value, etc.)."""
    out: dict = {}
    for k, v in payload.items():
        if hasattr(v, "value"):
            out[k] = v.value
        else:
            out[k] = v
    return out


def _normalize_eval_row(row: dict) -> dict:
    metadata = row.get("metadata_json")
    return {
        "eval_result_id": row["eval_result_id"],
        "agent_run_id": row["agent_run_id"],
        "evaluator_name": row["evaluator_name"],
        "eval_type": row["eval_type"],
        "score": row["score"],
        "outcome": row["outcome"],
        "explanation": row["explanation"],
        "failure_key": row["failure_key"],
        "failure_summary": row["failure_summary"],
        "annotation_level": row["annotation_level"],
        "span_id": row["span_id"],
        "metadata_json": json.loads(metadata) if isinstance(metadata, str) else (metadata or {}),
        "created_at": row["created_at"],
    }


def _normalize_aggregate_row(row: dict) -> dict:
    example_ids = row.get("example_run_ids_json")
    return {
        "failure_key": row["failure_key"],
        "failure_summary": row["failure_summary"],
        "evaluator_name": row["evaluator_name"],
        "occurrence_count": row["occurrence_count"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
        "example_run_ids_json": (
            json.loads(example_ids) if isinstance(example_ids, str) else (example_ids or [])
        ),
        "is_active": bool(row["is_active"]),
        "computed_at": row["computed_at"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-last-seed",
        action="store_true",
        help="Read the most recent live seed from backend/phoenixloop.db",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_BACKEND / "phoenixloop.db",
        help="Path to the SQLite file (default: backend/phoenixloop.db)",
    )
    args = parser.parse_args()

    if not args.from_last_seed:
        parser.error(
            "Refusing to run without --from-last-seed. This script overwrites "
            "the fixtures under backend/tests/fixtures/seed/."
        )

    if not args.db.exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        return 1

    print(f"Capturing fixtures from {args.db.relative_to(_PROJECT_ROOT)} ...")
    summary = asyncio.run(_capture(args.db))
    if not summary:
        return 1

    print("Overwrote fixtures:")
    for name, count in summary.items():
        print(f"  - {name}: {count}")
    print(f"\nFixture dir: {_FIXTURES_DIR.relative_to(_PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
