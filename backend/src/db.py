"""Async SQLite database layer for PhoenixLoop.

All database access goes through this module (Repository Pattern).
JSON fields are serialized/deserialized transparently.
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

from src.models import (
    AgentRun,
    AuditEvent,
    CanaryLabel,
    CanaryRun,
    ChangeClass,
    ConversationSession,
    EvalResult,
    ExperimentRecord,
    FailureAggregate,
    HumanApproval,
    ImprovementTrigger,
    JudgeLabel,
    Prompt,
    PromptSource,
    PromptVersion,
    RegressionExample,
    ReleaseDecision,
    ReleaseGateDecision,
    SupportTicket,
    TicketCategory,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_CREATE_TABLES_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id       TEXT PRIMARY KEY,
    customer_id     TEXT,
    category        TEXT NOT NULL,
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    metadata_json   TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_sessions (
    conversation_session_id TEXT PRIMARY KEY,
    ticket_id              TEXT NOT NULL REFERENCES support_tickets(ticket_id),
    phoenix_session_id     TEXT,
    started_at             TEXT NOT NULL,
    ended_at               TEXT,
    turn_count             INTEGER DEFAULT 0,
    outcome                TEXT
);

CREATE TABLE IF NOT EXISTS agent_runs (
    agent_run_id            TEXT PRIMARY KEY,
    conversation_session_id TEXT NOT NULL REFERENCES conversation_sessions(conversation_session_id),
    ticket_id               TEXT NOT NULL,
    agent_name              TEXT NOT NULL,
    agent_version           TEXT NOT NULL,
    prompt_version          TEXT NOT NULL,
    trace_id                TEXT,
    root_span_id            TEXT,
    phoenix_session_id      TEXT,
    input_hash              TEXT,
    response_json           TEXT NOT NULL,
    tool_calls_json         TEXT NOT NULL DEFAULT '[]',
    status                  TEXT NOT NULL,
    latency_ms              INTEGER,
    token_count_input       INTEGER,
    token_count_output      INTEGER,
    prompt_version_id       TEXT,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_results (
    eval_result_id   TEXT PRIMARY KEY,
    agent_run_id     TEXT NOT NULL REFERENCES agent_runs(agent_run_id),
    evaluator_name   TEXT NOT NULL,
    eval_type        TEXT NOT NULL,
    score            REAL,
    outcome          TEXT NOT NULL,
    explanation      TEXT,
    failure_key      TEXT,
    failure_summary  TEXT,
    annotation_level TEXT NOT NULL,
    span_id          TEXT,
    metadata_json    TEXT DEFAULT '{}',
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS failure_aggregates (
    failure_key          TEXT PRIMARY KEY,
    failure_summary      TEXT NOT NULL,
    evaluator_name       TEXT NOT NULL,
    occurrence_count     INTEGER NOT NULL DEFAULT 0,
    first_seen_at        TEXT NOT NULL,
    last_seen_at         TEXT NOT NULL,
    example_run_ids_json TEXT DEFAULT '[]',
    is_active            INTEGER NOT NULL DEFAULT 1,
    computed_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS improvement_triggers (
    improvement_trigger_id TEXT PRIMARY KEY,
    failure_key            TEXT NOT NULL,
    trigger_reason         TEXT NOT NULL,
    occurrence_count       INTEGER NOT NULL,
    example_run_ids_json   TEXT DEFAULT '[]',
    diagnosis_json         TEXT,
    patch_proposal_json    TEXT,
    regression_examples_json TEXT DEFAULT '[]',
    status                 TEXT NOT NULL DEFAULT 'pending',
    created_at             TEXT NOT NULL,
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regression_examples (
    regression_example_id   TEXT PRIMARY KEY,
    improvement_trigger_id  TEXT NOT NULL REFERENCES improvement_triggers(improvement_trigger_id),
    input_ticket_json       TEXT NOT NULL,
    expected_behavior       TEXT NOT NULL,
    failure_mode_targeted   TEXT NOT NULL,
    phoenix_dataset_id      TEXT,
    uploaded_at             TEXT,
    created_at              TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id                    TEXT PRIMARY KEY,
    improvement_trigger_id           TEXT NOT NULL REFERENCES improvement_triggers(improvement_trigger_id),
    baseline_prompt_version          TEXT NOT NULL,
    candidate_prompt_version         TEXT NOT NULL,
    dataset_id                       TEXT NOT NULL,
    phoenix_experiment_id_baseline   TEXT,
    phoenix_experiment_id_candidate  TEXT,
    status                           TEXT NOT NULL DEFAULT 'pending',
    baseline_release_score           REAL,
    candidate_release_score          REAL,
    baseline_critical_failure_rate   REAL,
    candidate_critical_failure_rate  REAL,
    baseline_latency_p50_ms          INTEGER,
    candidate_latency_p50_ms         INTEGER,
    baseline_hallucination_rate      REAL,
    candidate_hallucination_rate     REAL,
    regression_cases_pass_rate       REAL,
    safety_canary_pass_rate          REAL,
    eval_summary_json                TEXT,
    started_at                       TEXT,
    completed_at                     TEXT,
    baseline_prompt_version_id       TEXT,
    candidate_prompt_version_id      TEXT,
    created_at                       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS release_gate_decisions (
    release_gate_decision_id TEXT PRIMARY KEY,
    experiment_id            TEXT NOT NULL REFERENCES experiments(experiment_id),
    decision                 TEXT NOT NULL,
    release_score            REAL NOT NULL,
    promotion_rules_passed   INTEGER NOT NULL,
    rules_detail_json        TEXT DEFAULT '{}',
    requires_human_approval  INTEGER NOT NULL DEFAULT 0,
    decided_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS human_approvals (
    human_approval_id        TEXT PRIMARY KEY,
    release_gate_decision_id TEXT NOT NULL REFERENCES release_gate_decisions(release_gate_decision_id),
    reviewer_id              TEXT NOT NULL,
    status                   TEXT NOT NULL DEFAULT 'pending',
    comment                  TEXT,
    reviewed_at              TEXT,
    created_at               TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    audit_event_id TEXT PRIMARY KEY,
    entity_type    TEXT NOT NULL,
    entity_id      TEXT NOT NULL,
    action         TEXT NOT NULL,
    actor          TEXT NOT NULL,
    detail_json    TEXT DEFAULT '{}',
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompts (
    prompt_identifier   TEXT PRIMARY KEY,
    description         TEXT,
    active_version_id   TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS prompt_versions (
    prompt_version_id       TEXT PRIMARY KEY,
    prompt_identifier       TEXT NOT NULL REFERENCES prompts(prompt_identifier),
    version_tag             TEXT NOT NULL,
    prompt_text             TEXT NOT NULL,
    parent_version_id       TEXT REFERENCES prompt_versions(prompt_version_id),
    source                  TEXT NOT NULL,
    improvement_trigger_id  TEXT REFERENCES improvement_triggers(improvement_trigger_id),
    created_at              TEXT NOT NULL,
    metadata_json           TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_prompt_versions_identifier ON prompt_versions(prompt_identifier);
CREATE INDEX IF NOT EXISTS idx_prompt_versions_parent ON prompt_versions(parent_version_id);

CREATE TABLE IF NOT EXISTS canary_labels (
    canary_label_id    TEXT PRIMARY KEY,
    fixture_id         TEXT NOT NULL,
    ticket_category    TEXT NOT NULL,
    judge_name         TEXT NOT NULL,
    expected_label     TEXT NOT NULL,
    rationale          TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    UNIQUE(fixture_id, judge_name)
);
CREATE INDEX IF NOT EXISTS idx_canary_judge ON canary_labels(judge_name);

CREATE TABLE IF NOT EXISTS canary_runs (
    canary_run_id      TEXT PRIMARY KEY,
    canary_label_id    TEXT NOT NULL REFERENCES canary_labels(canary_label_id),
    judge_name         TEXT NOT NULL,
    predicted_label    TEXT NOT NULL,
    evidence_json      TEXT NOT NULL DEFAULT '[]',
    explanation        TEXT,
    judge_model        TEXT NOT NULL,
    created_at         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_canary_runs_judge ON canary_runs(judge_name);
CREATE INDEX IF NOT EXISTS idx_canary_runs_label ON canary_runs(canary_label_id);
"""


# ---------------------------------------------------------------------------
# Idempotent column migrations
# ---------------------------------------------------------------------------

# (table, column, type) tuples applied after _CREATE_TABLES_SQL. SQLite
# ALTER TABLE has no IF NOT EXISTS clause, so we catch "duplicate column
# name" errors to keep init_db idempotent across repeat runs.
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("prompt_versions", "change_class", "TEXT"),
    ("experiments", "baseline_tool_call_count", "REAL"),
    ("experiments", "candidate_tool_call_count", "REAL"),
    ("experiments", "baseline_tool_adherence_rate", "REAL"),
    ("experiments", "candidate_tool_adherence_rate", "REAL"),
    ("eval_results", "rubric_version", "TEXT"),
    ("eval_results", "evidence_json", "TEXT DEFAULT '[]'"),
    ("regression_examples", "source_agent_run_id", "TEXT"),
    ("regression_examples", "auto_promoted", "INTEGER NOT NULL DEFAULT 0"),
]


async def _apply_column_migrations(db: aiosqlite.Connection) -> None:
    """Apply additive ALTER TABLE migrations idempotently.

    SQLite raises ``OperationalError: duplicate column name: <col>`` when
    a column already exists; we treat that as success so repeated init
    calls are a no-op. Any other OperationalError is re-raised.
    """
    for table, column, column_type in _COLUMN_MIGRATIONS:
        statement = f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
        try:
            await db.execute(statement)
        except aiosqlite.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                logger.debug(
                    "Column %s.%s already present; skipping migration",
                    table,
                    column,
                )
                continue
            raise
    await db.commit()


# ---------------------------------------------------------------------------
# Initialization & Connection
# ---------------------------------------------------------------------------

async def init_db(db_path: str) -> None:
    """Create all tables, enable WAL mode and foreign keys, seed defaults."""
    logger.info("Initializing database at %s", db_path)
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(_CREATE_TABLES_SQL)
        await db.commit()
        await _apply_column_migrations(db)
        await _seed_default_prompt(db)
    logger.info("Database initialized successfully")


@asynccontextmanager
async def get_db(db_path: str) -> AsyncIterator[aiosqlite.Connection]:
    """Yield an aiosqlite connection with foreign keys enabled and row_factory set."""
    db = await aiosqlite.connect(db_path)
    try:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
    finally:
        await db.close()


# ---------------------------------------------------------------------------
# Helper: safe JSON parse
# ---------------------------------------------------------------------------

def _json_loads(value: str | None, default: object = None) -> object:
    """Parse a JSON string, returning *default* when the value is None or empty."""
    if value is None or value == "":
        return default if default is not None else {}
    return json.loads(value)


def _json_dumps(value: object) -> str:
    """Serialize a value to a compact JSON string."""
    return json.dumps(value, separators=(",", ":"))


# ---------------------------------------------------------------------------
# CRUD — Support Tickets
# ---------------------------------------------------------------------------

async def insert_ticket(db: aiosqlite.Connection, ticket: SupportTicket) -> None:
    """Insert a support ticket row."""
    await db.execute(
        """INSERT INTO support_tickets
           (ticket_id, customer_id, category, subject, body,
            metadata_json, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ticket.ticket_id,
            ticket.customer_id,
            ticket.category.value,
            ticket.subject,
            ticket.body,
            _json_dumps(ticket.metadata_json) if ticket.metadata_json is not None else None,
            ticket.created_at,
            ticket.updated_at,
        ),
    )
    await db.commit()


async def get_ticket(db: aiosqlite.Connection, ticket_id: str) -> SupportTicket | None:
    """Fetch a single ticket by ID, or None if not found."""
    cursor = await db.execute(
        "SELECT * FROM support_tickets WHERE ticket_id = ?", (ticket_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return SupportTicket(
        ticket_id=row["ticket_id"],
        customer_id=row["customer_id"],
        category=row["category"],
        subject=row["subject"],
        body=row["body"],
        metadata_json=_json_loads(row["metadata_json"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def list_tickets(
    db: aiosqlite.Connection,
    category: str | None,
    page: int,
    page_size: int,
) -> tuple[list[SupportTicket], int]:
    """List tickets with optional category filter and pagination."""
    where = ""
    params: list[str | int] = []
    if category is not None:
        where = "WHERE category = ?"
        params.append(category)

    count_cursor = await db.execute(
        f"SELECT COUNT(*) FROM support_tickets {where}", params  # noqa: S608 — params are bound
    )
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        f"SELECT * FROM support_tickets {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        [*params, page_size, offset],
    )
    rows = await data_cursor.fetchall()
    items = [
        SupportTicket(
            ticket_id=r["ticket_id"],
            customer_id=r["customer_id"],
            category=r["category"],
            subject=r["subject"],
            body=r["body"],
            metadata_json=_json_loads(r["metadata_json"]),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]
    return items, total_count


# ---------------------------------------------------------------------------
# CRUD — Conversation Sessions
# ---------------------------------------------------------------------------

async def insert_conversation_session(
    db: aiosqlite.Connection, session: ConversationSession
) -> None:
    """Insert a conversation session row."""
    await db.execute(
        """INSERT INTO conversation_sessions
           (conversation_session_id, ticket_id, phoenix_session_id,
            started_at, ended_at, turn_count, outcome)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            session.conversation_session_id,
            session.ticket_id,
            session.phoenix_session_id,
            session.started_at,
            session.ended_at,
            session.turn_count,
            session.outcome,
        ),
    )
    await db.commit()


async def get_conversation_session(
    db: aiosqlite.Connection, session_id: str
) -> ConversationSession | None:
    """Fetch a single conversation session by ID."""
    cursor = await db.execute(
        "SELECT * FROM conversation_sessions WHERE conversation_session_id = ?",
        (session_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return ConversationSession(
        conversation_session_id=row["conversation_session_id"],
        ticket_id=row["ticket_id"],
        phoenix_session_id=row["phoenix_session_id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        turn_count=row["turn_count"],
        outcome=row["outcome"],
    )


async def list_conversation_sessions(
    db: aiosqlite.Connection, page: int, page_size: int
) -> tuple[list[ConversationSession], int]:
    """List conversation sessions with pagination."""
    count_cursor = await db.execute("SELECT COUNT(*) FROM conversation_sessions")
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        "SELECT * FROM conversation_sessions ORDER BY started_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    rows = await data_cursor.fetchall()
    items = [
        ConversationSession(
            conversation_session_id=r["conversation_session_id"],
            ticket_id=r["ticket_id"],
            phoenix_session_id=r["phoenix_session_id"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            turn_count=r["turn_count"],
            outcome=r["outcome"],
        )
        for r in rows
    ]
    return items, total_count


# ---------------------------------------------------------------------------
# CRUD — Agent Runs
# ---------------------------------------------------------------------------

def _agent_run_from_row(row: aiosqlite.Row) -> AgentRun:
    """Deserialize an agent_runs row into an AgentRun model."""
    raw_tool_calls = _json_loads(row["tool_calls_json"], default=[])
    tool_calls = [ToolCallRecord(**tc) for tc in raw_tool_calls]  # type: ignore[arg-type]
    return AgentRun(
        agent_run_id=row["agent_run_id"],
        conversation_session_id=row["conversation_session_id"],
        ticket_id=row["ticket_id"],
        agent_name=row["agent_name"],
        agent_version=row["agent_version"],
        prompt_version=row["prompt_version"],
        trace_id=row["trace_id"],
        root_span_id=row["root_span_id"],
        phoenix_session_id=row["phoenix_session_id"],
        input_hash=row["input_hash"],
        response_json=_json_loads(row["response_json"], default={}),  # type: ignore[arg-type]
        tool_calls_json=tool_calls,
        status=row["status"],
        latency_ms=row["latency_ms"],
        token_count_input=row["token_count_input"],
        token_count_output=row["token_count_output"],
        prompt_version_id=row["prompt_version_id"],
        created_at=row["created_at"],
    )


async def insert_agent_run(db: aiosqlite.Connection, run: AgentRun) -> None:
    """Insert an agent run row."""
    tool_calls_serialized = _json_dumps(
        [tc.model_dump() for tc in run.tool_calls_json]
    )
    await db.execute(
        """INSERT INTO agent_runs
           (agent_run_id, conversation_session_id, ticket_id, agent_name,
            agent_version, prompt_version, trace_id, root_span_id,
            phoenix_session_id, input_hash, response_json, tool_calls_json,
            status, latency_ms, token_count_input, token_count_output,
            prompt_version_id, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run.agent_run_id,
            run.conversation_session_id,
            run.ticket_id,
            run.agent_name,
            run.agent_version,
            run.prompt_version,
            run.trace_id,
            run.root_span_id,
            run.phoenix_session_id,
            run.input_hash,
            _json_dumps(run.response_json),
            tool_calls_serialized,
            run.status,
            run.latency_ms,
            run.token_count_input,
            run.token_count_output,
            run.prompt_version_id,
            run.created_at,
        ),
    )
    await db.commit()


async def get_agent_run(db: aiosqlite.Connection, run_id: str) -> AgentRun | None:
    """Fetch a single agent run by ID."""
    cursor = await db.execute(
        "SELECT * FROM agent_runs WHERE agent_run_id = ?", (run_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _agent_run_from_row(row)


async def get_agent_runs_for_session(
    db: aiosqlite.Connection, session_id: str
) -> list[AgentRun]:
    """Fetch all agent runs for a conversation session."""
    cursor = await db.execute(
        "SELECT * FROM agent_runs WHERE conversation_session_id = ? ORDER BY created_at",
        (session_id,),
    )
    rows = await cursor.fetchall()
    return [_agent_run_from_row(r) for r in rows]


async def resolve_trace_ids(
    db: aiosqlite.Connection, agent_run_ids: list[str]
) -> list[str]:
    """Look up the Phoenix trace_id for each agent_run_id, drop nulls.

    Used by the diagnosis pipeline to translate local UUIDs into the
    32-char hex trace IDs Phoenix MCP's ``get-spans`` actually accepts.
    """
    if not agent_run_ids:
        return []
    placeholders = ",".join("?" * len(agent_run_ids))
    cursor = await db.execute(
        f"SELECT trace_id FROM agent_runs "
        f"WHERE agent_run_id IN ({placeholders}) AND trace_id IS NOT NULL",
        agent_run_ids,
    )
    rows = await cursor.fetchall()
    return [row["trace_id"] for row in rows if row["trace_id"]]


# ---------------------------------------------------------------------------
# CRUD — Eval Results
# ---------------------------------------------------------------------------

def _eval_result_from_row(row: aiosqlite.Row) -> EvalResult:
    """Deserialize an eval_results row into an EvalResult model."""
    evidence_raw = _json_loads(row["evidence_json"], default=[])
    evidence_list: list[str] = (
        [str(item) for item in evidence_raw]
        if isinstance(evidence_raw, list)
        else []
    )
    return EvalResult(
        eval_result_id=row["eval_result_id"],
        agent_run_id=row["agent_run_id"],
        evaluator_name=row["evaluator_name"],
        eval_type=row["eval_type"],
        score=row["score"],
        outcome=row["outcome"],
        explanation=row["explanation"],
        failure_key=row["failure_key"],
        failure_summary=row["failure_summary"],
        annotation_level=row["annotation_level"],
        span_id=row["span_id"],
        metadata_json=_json_loads(row["metadata_json"]),  # type: ignore[arg-type]
        created_at=row["created_at"],
        rubric_version=row["rubric_version"],
        evidence_json=evidence_list,
    )


async def insert_eval_result(db: aiosqlite.Connection, result: EvalResult) -> None:
    """Insert an eval result row."""
    await db.execute(
        """INSERT INTO eval_results
           (eval_result_id, agent_run_id, evaluator_name, eval_type,
            score, outcome, explanation, failure_key, failure_summary,
            annotation_level, span_id, metadata_json, created_at,
            rubric_version, evidence_json)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            result.eval_result_id,
            result.agent_run_id,
            result.evaluator_name,
            result.eval_type.value,
            result.score,
            result.outcome,
            result.explanation,
            result.failure_key,
            result.failure_summary,
            result.annotation_level.value,
            result.span_id,
            _json_dumps(result.metadata_json) if result.metadata_json is not None else "{}",
            result.created_at,
            result.rubric_version,
            _json_dumps(result.evidence_json),
        ),
    )
    await db.commit()


async def get_eval_results_for_run(
    db: aiosqlite.Connection, run_id: str
) -> list[EvalResult]:
    """Fetch all eval results for a given agent run."""
    cursor = await db.execute(
        "SELECT * FROM eval_results WHERE agent_run_id = ? ORDER BY created_at",
        (run_id,),
    )
    rows = await cursor.fetchall()
    return [_eval_result_from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# CRUD — Failure Aggregates
# ---------------------------------------------------------------------------

def _failure_aggregate_from_row(row: aiosqlite.Row) -> FailureAggregate:
    """Deserialize a failure_aggregates row into a FailureAggregate model."""
    return FailureAggregate(
        failure_key=row["failure_key"],
        failure_summary=row["failure_summary"],
        evaluator_name=row["evaluator_name"],
        occurrence_count=row["occurrence_count"],
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        example_run_ids_json=_json_loads(row["example_run_ids_json"], default=[]),  # type: ignore[arg-type]
        is_active=bool(row["is_active"]),
        computed_at=row["computed_at"],
    )


async def upsert_failure_aggregate(
    db: aiosqlite.Connection, agg: FailureAggregate
) -> None:
    """Insert or replace a failure aggregate (idempotent)."""
    await db.execute(
        """INSERT OR REPLACE INTO failure_aggregates
           (failure_key, failure_summary, evaluator_name, occurrence_count,
            first_seen_at, last_seen_at, example_run_ids_json, is_active,
            computed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            agg.failure_key,
            agg.failure_summary,
            agg.evaluator_name,
            agg.occurrence_count,
            agg.first_seen_at,
            agg.last_seen_at,
            _json_dumps(agg.example_run_ids_json),
            int(agg.is_active),
            agg.computed_at,
        ),
    )
    await db.commit()


async def get_failure_aggregate(
    db: aiosqlite.Connection, failure_key: str
) -> FailureAggregate | None:
    """Fetch a single failure aggregate by key."""
    cursor = await db.execute(
        "SELECT * FROM failure_aggregates WHERE failure_key = ?", (failure_key,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _failure_aggregate_from_row(row)


async def get_active_failure_aggregates(
    db: aiosqlite.Connection,
) -> list[FailureAggregate]:
    """Fetch all active failure aggregates."""
    cursor = await db.execute(
        "SELECT * FROM failure_aggregates WHERE is_active = 1 ORDER BY last_seen_at DESC"
    )
    rows = await cursor.fetchall()
    return [_failure_aggregate_from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# CRUD — Improvement Triggers
# ---------------------------------------------------------------------------

def _improvement_trigger_from_row(row: aiosqlite.Row) -> ImprovementTrigger:
    """Deserialize an improvement_triggers row into an ImprovementTrigger model."""
    return ImprovementTrigger(
        improvement_trigger_id=row["improvement_trigger_id"],
        failure_key=row["failure_key"],
        trigger_reason=row["trigger_reason"],
        occurrence_count=row["occurrence_count"],
        example_run_ids_json=_json_loads(row["example_run_ids_json"], default=[]),  # type: ignore[arg-type]
        diagnosis_json=_json_loads(row["diagnosis_json"]),  # type: ignore[arg-type]
        patch_proposal_json=_json_loads(row["patch_proposal_json"]),  # type: ignore[arg-type]
        regression_examples_json=_json_loads(row["regression_examples_json"], default=[]),  # type: ignore[arg-type]
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def insert_improvement_trigger(
    db: aiosqlite.Connection, trigger: ImprovementTrigger
) -> None:
    """Insert an improvement trigger row."""
    await db.execute(
        """INSERT INTO improvement_triggers
           (improvement_trigger_id, failure_key, trigger_reason,
            occurrence_count, example_run_ids_json, diagnosis_json,
            patch_proposal_json, regression_examples_json, status,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trigger.improvement_trigger_id,
            trigger.failure_key,
            trigger.trigger_reason.value,
            trigger.occurrence_count,
            _json_dumps(trigger.example_run_ids_json),
            _json_dumps(trigger.diagnosis_json) if trigger.diagnosis_json is not None else None,
            _json_dumps(trigger.patch_proposal_json) if trigger.patch_proposal_json is not None else None,
            _json_dumps(trigger.regression_examples_json),
            trigger.status,
            trigger.created_at,
            trigger.updated_at,
        ),
    )
    await db.commit()


async def update_improvement_trigger(
    db: aiosqlite.Connection, trigger: ImprovementTrigger
) -> None:
    """Update an existing improvement trigger row."""
    await db.execute(
        """UPDATE improvement_triggers SET
           failure_key = ?, trigger_reason = ?, occurrence_count = ?,
           example_run_ids_json = ?, diagnosis_json = ?,
           patch_proposal_json = ?, regression_examples_json = ?,
           status = ?, updated_at = ?
           WHERE improvement_trigger_id = ?""",
        (
            trigger.failure_key,
            trigger.trigger_reason.value,
            trigger.occurrence_count,
            _json_dumps(trigger.example_run_ids_json),
            _json_dumps(trigger.diagnosis_json) if trigger.diagnosis_json is not None else None,
            _json_dumps(trigger.patch_proposal_json) if trigger.patch_proposal_json is not None else None,
            _json_dumps(trigger.regression_examples_json),
            trigger.status,
            trigger.updated_at,
            trigger.improvement_trigger_id,
        ),
    )
    await db.commit()


async def get_improvement_trigger(
    db: aiosqlite.Connection, trigger_id: str
) -> ImprovementTrigger | None:
    """Fetch a single improvement trigger by ID."""
    cursor = await db.execute(
        "SELECT * FROM improvement_triggers WHERE improvement_trigger_id = ?",
        (trigger_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _improvement_trigger_from_row(row)


async def list_improvement_triggers(
    db: aiosqlite.Connection,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[ImprovementTrigger], int]:
    """List improvement triggers with optional status filter and pagination."""
    where = ""
    params: list[str | int] = []
    if status is not None:
        where = "WHERE status = ?"
        params.append(status)

    count_cursor = await db.execute(
        f"SELECT COUNT(*) FROM improvement_triggers {where}", params  # noqa: S608
    )
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        f"SELECT * FROM improvement_triggers {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        [*params, page_size, offset],
    )
    rows = await data_cursor.fetchall()
    items = [_improvement_trigger_from_row(r) for r in rows]
    return items, total_count


# ---------------------------------------------------------------------------
# CRUD — Regression Examples
# ---------------------------------------------------------------------------

def _regression_example_from_row(row: aiosqlite.Row) -> RegressionExample:
    """Deserialize a regression_examples row into a RegressionExample model."""
    return RegressionExample(
        regression_example_id=row["regression_example_id"],
        improvement_trigger_id=row["improvement_trigger_id"],
        input_ticket_json=_json_loads(row["input_ticket_json"], default={}),  # type: ignore[arg-type]
        expected_behavior=row["expected_behavior"],
        failure_mode_targeted=row["failure_mode_targeted"],
        phoenix_dataset_id=row["phoenix_dataset_id"],
        uploaded_at=row["uploaded_at"],
        created_at=row["created_at"],
        source_agent_run_id=row["source_agent_run_id"],
        auto_promoted=bool(row["auto_promoted"]),
    )


async def insert_regression_example(
    db: aiosqlite.Connection, example: RegressionExample
) -> None:
    """Insert a regression example row."""
    await db.execute(
        """INSERT INTO regression_examples
           (regression_example_id, improvement_trigger_id, input_ticket_json,
            expected_behavior, failure_mode_targeted, phoenix_dataset_id,
            uploaded_at, created_at, source_agent_run_id, auto_promoted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            example.regression_example_id,
            example.improvement_trigger_id,
            _json_dumps(example.input_ticket_json),
            example.expected_behavior,
            example.failure_mode_targeted,
            example.phoenix_dataset_id,
            example.uploaded_at,
            example.created_at,
            example.source_agent_run_id,
            int(example.auto_promoted),
        ),
    )
    await db.commit()


async def list_regression_examples_auto_promoted(
    db: aiosqlite.Connection, limit: int = 50
) -> list[RegressionExample]:
    """Most-recent auto-promoted regression examples, newest first.

    Surfaces rows produced by the failure-trace auto-promote path so the
    UI can distinguish them from manual diagnosis-derived examples.
    """
    cursor = await db.execute(
        "SELECT * FROM regression_examples WHERE auto_promoted = 1 "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = await cursor.fetchall()
    return [_regression_example_from_row(r) for r in rows]


async def count_regression_examples_for_trigger(
    db: aiosqlite.Connection, trigger_id: str
) -> int:
    """Return how many regression examples exist for an improvement trigger.

    Used by the auto-promote dedup check to avoid promoting the same
    failure trace twice under the same trigger.
    """
    cursor = await db.execute(
        "SELECT COUNT(*) FROM regression_examples WHERE improvement_trigger_id = ?",
        (trigger_id,),
    )
    row = await cursor.fetchone()
    return int(row[0]) if row is not None else 0


async def get_regression_examples_for_trigger(
    db: aiosqlite.Connection, trigger_id: str
) -> list[RegressionExample]:
    """Fetch all regression examples for a given improvement trigger."""
    cursor = await db.execute(
        "SELECT * FROM regression_examples WHERE improvement_trigger_id = ? ORDER BY created_at",
        (trigger_id,),
    )
    rows = await cursor.fetchall()
    return [_regression_example_from_row(r) for r in rows]


async def get_phoenix_dataset_id_for_trigger(
    db: aiosqlite.Connection, trigger_id: str
) -> str | None:
    """Return the Phoenix dataset_id captured for this trigger's regression
    examples, or None if no example has one persisted.

    Used by the experiment orchestrator to look up Phoenix datasets by ID
    instead of by name — Phoenix server slugifies dataset names containing
    characters like ``::``, so the name we passed at creation time is not
    the name Phoenix stores under.
    """
    cursor = await db.execute(
        "SELECT phoenix_dataset_id FROM regression_examples "
        "WHERE improvement_trigger_id = ? AND phoenix_dataset_id IS NOT NULL "
        "LIMIT 1",
        (trigger_id,),
    )
    row = await cursor.fetchone()
    return row["phoenix_dataset_id"] if row else None


# ---------------------------------------------------------------------------
# CRUD — Experiments
# ---------------------------------------------------------------------------

def _experiment_from_row(row: aiosqlite.Row) -> ExperimentRecord:
    """Deserialize an experiments row into an ExperimentRecord model."""
    return ExperimentRecord(
        experiment_id=row["experiment_id"],
        improvement_trigger_id=row["improvement_trigger_id"],
        baseline_prompt_version=row["baseline_prompt_version"],
        candidate_prompt_version=row["candidate_prompt_version"],
        dataset_id=row["dataset_id"],
        phoenix_experiment_id_baseline=row["phoenix_experiment_id_baseline"],
        phoenix_experiment_id_candidate=row["phoenix_experiment_id_candidate"],
        status=row["status"],
        baseline_release_score=row["baseline_release_score"],
        candidate_release_score=row["candidate_release_score"],
        baseline_critical_failure_rate=row["baseline_critical_failure_rate"],
        candidate_critical_failure_rate=row["candidate_critical_failure_rate"],
        baseline_latency_p50_ms=row["baseline_latency_p50_ms"],
        candidate_latency_p50_ms=row["candidate_latency_p50_ms"],
        baseline_hallucination_rate=row["baseline_hallucination_rate"],
        candidate_hallucination_rate=row["candidate_hallucination_rate"],
        regression_cases_pass_rate=row["regression_cases_pass_rate"],
        safety_canary_pass_rate=row["safety_canary_pass_rate"],
        eval_summary_json=_json_loads(row["eval_summary_json"]),  # type: ignore[arg-type]
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        baseline_prompt_version_id=row["baseline_prompt_version_id"],
        candidate_prompt_version_id=row["candidate_prompt_version_id"],
        created_at=row["created_at"],
        baseline_tool_call_count=row["baseline_tool_call_count"],
        candidate_tool_call_count=row["candidate_tool_call_count"],
        baseline_tool_adherence_rate=row["baseline_tool_adherence_rate"],
        candidate_tool_adherence_rate=row["candidate_tool_adherence_rate"],
    )


async def insert_experiment(
    db: aiosqlite.Connection, exp: ExperimentRecord
) -> None:
    """Insert an experiment row."""
    await db.execute(
        """INSERT INTO experiments
           (experiment_id, improvement_trigger_id, baseline_prompt_version,
            candidate_prompt_version, dataset_id,
            phoenix_experiment_id_baseline, phoenix_experiment_id_candidate,
            status, baseline_release_score, candidate_release_score,
            baseline_critical_failure_rate, candidate_critical_failure_rate,
            baseline_latency_p50_ms, candidate_latency_p50_ms,
            baseline_hallucination_rate, candidate_hallucination_rate,
            regression_cases_pass_rate, safety_canary_pass_rate,
            eval_summary_json, started_at, completed_at,
            baseline_prompt_version_id, candidate_prompt_version_id,
            created_at,
            baseline_tool_call_count, candidate_tool_call_count,
            baseline_tool_adherence_rate, candidate_tool_adherence_rate)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            exp.experiment_id,
            exp.improvement_trigger_id,
            exp.baseline_prompt_version,
            exp.candidate_prompt_version,
            exp.dataset_id,
            exp.phoenix_experiment_id_baseline,
            exp.phoenix_experiment_id_candidate,
            exp.status.value,
            exp.baseline_release_score,
            exp.candidate_release_score,
            exp.baseline_critical_failure_rate,
            exp.candidate_critical_failure_rate,
            exp.baseline_latency_p50_ms,
            exp.candidate_latency_p50_ms,
            exp.baseline_hallucination_rate,
            exp.candidate_hallucination_rate,
            exp.regression_cases_pass_rate,
            exp.safety_canary_pass_rate,
            _json_dumps(exp.eval_summary_json) if exp.eval_summary_json is not None else None,
            exp.started_at,
            exp.completed_at,
            exp.baseline_prompt_version_id,
            exp.candidate_prompt_version_id,
            exp.created_at,
            exp.baseline_tool_call_count,
            exp.candidate_tool_call_count,
            exp.baseline_tool_adherence_rate,
            exp.candidate_tool_adherence_rate,
        ),
    )
    await db.commit()


async def update_experiment(
    db: aiosqlite.Connection, exp: ExperimentRecord
) -> None:
    """Update an existing experiment row."""
    await db.execute(
        """UPDATE experiments SET
           improvement_trigger_id = ?, baseline_prompt_version = ?,
           candidate_prompt_version = ?, dataset_id = ?,
           phoenix_experiment_id_baseline = ?,
           phoenix_experiment_id_candidate = ?,
           status = ?, baseline_release_score = ?,
           candidate_release_score = ?,
           baseline_critical_failure_rate = ?,
           candidate_critical_failure_rate = ?,
           baseline_latency_p50_ms = ?, candidate_latency_p50_ms = ?,
           baseline_hallucination_rate = ?,
           candidate_hallucination_rate = ?,
           regression_cases_pass_rate = ?, safety_canary_pass_rate = ?,
           eval_summary_json = ?, started_at = ?, completed_at = ?,
           baseline_prompt_version_id = ?, candidate_prompt_version_id = ?,
           baseline_tool_call_count = ?, candidate_tool_call_count = ?,
           baseline_tool_adherence_rate = ?, candidate_tool_adherence_rate = ?
           WHERE experiment_id = ?""",
        (
            exp.improvement_trigger_id,
            exp.baseline_prompt_version,
            exp.candidate_prompt_version,
            exp.dataset_id,
            exp.phoenix_experiment_id_baseline,
            exp.phoenix_experiment_id_candidate,
            exp.status.value,
            exp.baseline_release_score,
            exp.candidate_release_score,
            exp.baseline_critical_failure_rate,
            exp.candidate_critical_failure_rate,
            exp.baseline_latency_p50_ms,
            exp.candidate_latency_p50_ms,
            exp.baseline_hallucination_rate,
            exp.candidate_hallucination_rate,
            exp.regression_cases_pass_rate,
            exp.safety_canary_pass_rate,
            _json_dumps(exp.eval_summary_json) if exp.eval_summary_json is not None else None,
            exp.started_at,
            exp.completed_at,
            exp.baseline_prompt_version_id,
            exp.candidate_prompt_version_id,
            exp.baseline_tool_call_count,
            exp.candidate_tool_call_count,
            exp.baseline_tool_adherence_rate,
            exp.candidate_tool_adherence_rate,
            exp.experiment_id,
        ),
    )
    await db.commit()


async def get_experiment(
    db: aiosqlite.Connection, exp_id: str
) -> ExperimentRecord | None:
    """Fetch a single experiment by ID."""
    cursor = await db.execute(
        "SELECT * FROM experiments WHERE experiment_id = ?", (exp_id,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _experiment_from_row(row)


async def list_experiments(
    db: aiosqlite.Connection, page: int, page_size: int
) -> tuple[list[ExperimentRecord], int]:
    """List experiments with pagination."""
    count_cursor = await db.execute("SELECT COUNT(*) FROM experiments")
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    rows = await data_cursor.fetchall()
    items = [_experiment_from_row(r) for r in rows]
    return items, total_count


async def list_experiments_for_trigger(
    db: aiosqlite.Connection, improvement_trigger_id: str
) -> list[ExperimentRecord]:
    """All experiments for one improvement trigger, oldest first."""
    cursor = await db.execute(
        "SELECT * FROM experiments WHERE improvement_trigger_id = ? "
        "ORDER BY created_at ASC",
        (improvement_trigger_id,),
    )
    rows = await cursor.fetchall()
    return [_experiment_from_row(r) for r in rows]


async def get_failure_aggregates_by_key(
    db: aiosqlite.Connection, failure_key: str
) -> list[FailureAggregate]:
    """All failure aggregates for one failure_key, newest first.

    The failure_aggregates table uses failure_key as PRIMARY KEY, so this
    returns at most one row — but the return type is list for API consistency.
    """
    cursor = await db.execute(
        "SELECT * FROM failure_aggregates WHERE failure_key = ? "
        "ORDER BY last_seen_at DESC",
        (failure_key,),
    )
    rows = await cursor.fetchall()
    return [_failure_aggregate_from_row(r) for r in rows]


async def list_improvement_triggers_for_key(
    db: aiosqlite.Connection, failure_key: str
) -> list[ImprovementTrigger]:
    """All improvement triggers for one failure_key, newest first."""
    cursor = await db.execute(
        "SELECT * FROM improvement_triggers WHERE failure_key = ? "
        "ORDER BY created_at DESC",
        (failure_key,),
    )
    rows = await cursor.fetchall()
    return [_improvement_trigger_from_row(r) for r in rows]


# ---------------------------------------------------------------------------
# CRUD — Release Gate Decisions
# ---------------------------------------------------------------------------

def _release_gate_from_row(row: aiosqlite.Row) -> ReleaseGateDecision:
    """Deserialize a release_gate_decisions row into a ReleaseGateDecision model."""
    return ReleaseGateDecision(
        release_gate_decision_id=row["release_gate_decision_id"],
        experiment_id=row["experiment_id"],
        decision=row["decision"],
        release_score=row["release_score"],
        promotion_rules_passed=row["promotion_rules_passed"],
        rules_detail_json=_json_loads(row["rules_detail_json"]),  # type: ignore[arg-type]
        requires_human_approval=bool(row["requires_human_approval"]),
        decided_at=row["decided_at"],
    )


async def insert_release_gate_decision(
    db: aiosqlite.Connection, decision: ReleaseGateDecision
) -> None:
    """Insert a release gate decision row."""
    await db.execute(
        """INSERT INTO release_gate_decisions
           (release_gate_decision_id, experiment_id, decision,
            release_score, promotion_rules_passed, rules_detail_json,
            requires_human_approval, decided_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            decision.release_gate_decision_id,
            decision.experiment_id,
            decision.decision.value,
            decision.release_score,
            decision.promotion_rules_passed,
            _json_dumps(decision.rules_detail_json) if decision.rules_detail_json is not None else "{}",
            int(decision.requires_human_approval),
            decision.decided_at,
        ),
    )
    await db.commit()


async def get_release_gate_decision(
    db: aiosqlite.Connection, decision_id: str
) -> ReleaseGateDecision | None:
    """Fetch a single release gate decision by ID."""
    cursor = await db.execute(
        "SELECT * FROM release_gate_decisions WHERE release_gate_decision_id = ?",
        (decision_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _release_gate_from_row(row)


async def update_release_gate_decision_status(
    db: aiosqlite.Connection,
    decision_id: str,
    new_decision: ReleaseDecision,
) -> None:
    """Update the ``decision`` column on a release gate row.

    Used by the approval/rejection flows to transition a row from
    ``pending_human_review`` to ``promoted`` or ``rejected`` once a human
    acts. The row's other audit data lives on ``human_approvals``.
    """
    await db.execute(
        """UPDATE release_gate_decisions
              SET decision = ?
            WHERE release_gate_decision_id = ?""",
        (new_decision.value, decision_id),
    )
    await db.commit()


async def get_release_gate_for_experiment(
    db: aiosqlite.Connection, experiment_id: str
) -> ReleaseGateDecision | None:
    """Fetch the release gate decision for a given experiment."""
    cursor = await db.execute(
        "SELECT * FROM release_gate_decisions WHERE experiment_id = ?",
        (experiment_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _release_gate_from_row(row)


async def list_release_gate_decisions(
    db: aiosqlite.Connection, page: int, page_size: int
) -> tuple[list[ReleaseGateDecision], int]:
    """List release gate decisions with pagination."""
    count_cursor = await db.execute("SELECT COUNT(*) FROM release_gate_decisions")
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        "SELECT * FROM release_gate_decisions ORDER BY decided_at DESC LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    rows = await data_cursor.fetchall()
    items = [_release_gate_from_row(r) for r in rows]
    return items, total_count


async def list_failure_aggregates(
    db: aiosqlite.Connection,
    active_only: bool,
    page: int,
    page_size: int,
) -> tuple[list[FailureAggregate], int]:
    """List failure aggregates with optional active filter and pagination."""
    where = ""
    params: list[int] = []
    if active_only:
        where = "WHERE is_active = ?"
        params.append(1)

    count_cursor = await db.execute(
        f"SELECT COUNT(*) FROM failure_aggregates {where}", params  # noqa: S608
    )
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        f"SELECT * FROM failure_aggregates {where} ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        [*params, page_size, offset],
    )
    rows = await data_cursor.fetchall()
    items = [_failure_aggregate_from_row(r) for r in rows]
    return items, total_count


# ---------------------------------------------------------------------------
# CRUD — Human Approvals
# ---------------------------------------------------------------------------

def _human_approval_from_row(row: aiosqlite.Row) -> HumanApproval:
    """Deserialize a human_approvals row into a HumanApproval model."""
    return HumanApproval(
        human_approval_id=row["human_approval_id"],
        release_gate_decision_id=row["release_gate_decision_id"],
        reviewer_id=row["reviewer_id"],
        status=row["status"],
        comment=row["comment"],
        reviewed_at=row["reviewed_at"],
        created_at=row["created_at"],
    )


async def insert_human_approval(
    db: aiosqlite.Connection, approval: HumanApproval
) -> None:
    """Insert a human approval row."""
    await db.execute(
        """INSERT INTO human_approvals
           (human_approval_id, release_gate_decision_id, reviewer_id,
            status, comment, reviewed_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            approval.human_approval_id,
            approval.release_gate_decision_id,
            approval.reviewer_id,
            approval.status,
            approval.comment,
            approval.reviewed_at,
            approval.created_at,
        ),
    )
    await db.commit()


async def update_human_approval(
    db: aiosqlite.Connection, approval: HumanApproval
) -> None:
    """Update an existing human approval row."""
    await db.execute(
        """UPDATE human_approvals SET
           status = ?, comment = ?, reviewed_at = ?
           WHERE human_approval_id = ?""",
        (
            approval.status,
            approval.comment,
            approval.reviewed_at,
            approval.human_approval_id,
        ),
    )
    await db.commit()


async def get_human_approval_for_decision(
    db: aiosqlite.Connection, decision_id: str
) -> HumanApproval | None:
    """Fetch the human approval for a given release gate decision."""
    cursor = await db.execute(
        "SELECT * FROM human_approvals WHERE release_gate_decision_id = ?",
        (decision_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _human_approval_from_row(row)


# ---------------------------------------------------------------------------
# CRUD — Audit Events
# ---------------------------------------------------------------------------

async def insert_audit_event(db: aiosqlite.Connection, event: AuditEvent) -> None:
    """Insert an audit event row."""
    await db.execute(
        """INSERT INTO audit_events
           (audit_event_id, entity_type, entity_id, action, actor,
            detail_json, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            event.audit_event_id,
            event.entity_type,
            event.entity_id,
            event.action,
            event.actor,
            _json_dumps(event.detail_json) if event.detail_json is not None else "{}",
            event.created_at,
        ),
    )
    await db.commit()


async def list_audit_events(
    db: aiosqlite.Connection,
    entity_type: str | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditEvent], int]:
    """List audit events with optional entity_type filter and pagination."""
    where = ""
    params: list[str | int] = []
    if entity_type is not None:
        where = "WHERE entity_type = ?"
        params.append(entity_type)

    count_cursor = await db.execute(
        f"SELECT COUNT(*) FROM audit_events {where}", params  # noqa: S608
    )
    total_count = (await count_cursor.fetchone())[0]

    offset = (page - 1) * page_size
    data_cursor = await db.execute(
        f"SELECT * FROM audit_events {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",  # noqa: S608
        [*params, page_size, offset],
    )
    rows = await data_cursor.fetchall()
    items = [
        AuditEvent(
            audit_event_id=r["audit_event_id"],
            entity_type=r["entity_type"],
            entity_id=r["entity_id"],
            action=r["action"],
            actor=r["actor"],
            detail_json=_json_loads(r["detail_json"]),  # type: ignore[arg-type]
            created_at=r["created_at"],
        )
        for r in rows
    ]
    return items, total_count


# ---------------------------------------------------------------------------
# CRUD — Prompts and Prompt Versions
# ---------------------------------------------------------------------------

def _prompt_from_row(row: aiosqlite.Row) -> Prompt:
    """Deserialize a prompts row into a Prompt model."""
    return Prompt(
        prompt_identifier=row["prompt_identifier"],
        description=row["description"],
        active_version_id=row["active_version_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _prompt_version_from_row(row: aiosqlite.Row) -> PromptVersion:
    """Deserialize a prompt_versions row into a PromptVersion model."""
    raw_change_class = row["change_class"]
    change_class = ChangeClass(raw_change_class) if raw_change_class else None
    return PromptVersion(
        prompt_version_id=row["prompt_version_id"],
        prompt_identifier=row["prompt_identifier"],
        version_tag=row["version_tag"],
        prompt_text=row["prompt_text"],
        parent_version_id=row["parent_version_id"],
        source=PromptSource(row["source"]),
        improvement_trigger_id=row["improvement_trigger_id"],
        created_at=row["created_at"],
        metadata_json=_json_loads(row["metadata_json"], default={}),  # type: ignore[arg-type]
        change_class=change_class,
    )


async def insert_prompt(db: aiosqlite.Connection, prompt: Prompt) -> None:
    """Insert or replace a prompt row (idempotent on prompt_identifier)."""
    await db.execute(
        """INSERT OR REPLACE INTO prompts
           (prompt_identifier, description, active_version_id,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?)""",
        (
            prompt.prompt_identifier,
            prompt.description,
            prompt.active_version_id,
            prompt.created_at,
            prompt.updated_at,
        ),
    )
    await db.commit()


async def get_prompt(
    db: aiosqlite.Connection, identifier: str
) -> Prompt | None:
    """Fetch a single prompt by identifier."""
    cursor = await db.execute(
        "SELECT * FROM prompts WHERE prompt_identifier = ?", (identifier,)
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _prompt_from_row(row)


async def list_prompts(db: aiosqlite.Connection) -> list[Prompt]:
    """List all prompts ordered by identifier."""
    cursor = await db.execute(
        "SELECT * FROM prompts ORDER BY prompt_identifier"
    )
    rows = await cursor.fetchall()
    return [_prompt_from_row(r) for r in rows]


async def insert_prompt_version(
    db: aiosqlite.Connection, pv: PromptVersion
) -> None:
    """Insert an immutable prompt version row."""
    await db.execute(
        """INSERT INTO prompt_versions
           (prompt_version_id, prompt_identifier, version_tag, prompt_text,
            parent_version_id, source, improvement_trigger_id, created_at,
            metadata_json, change_class)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            pv.prompt_version_id,
            pv.prompt_identifier,
            pv.version_tag,
            pv.prompt_text,
            pv.parent_version_id,
            pv.source.value,
            pv.improvement_trigger_id,
            pv.created_at,
            _json_dumps(pv.metadata_json),
            pv.change_class.value if pv.change_class is not None else None,
        ),
    )
    await db.commit()


async def get_prompt_version(
    db: aiosqlite.Connection, version_id: str
) -> PromptVersion | None:
    """Fetch a single prompt version by id."""
    cursor = await db.execute(
        "SELECT * FROM prompt_versions WHERE prompt_version_id = ?",
        (version_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _prompt_version_from_row(row)


async def list_prompt_versions(
    db: aiosqlite.Connection,
    identifier: str,
    limit: int = 100,
    offset: int = 0,
) -> list[PromptVersion]:
    """List versions for a prompt identifier, newest first."""
    cursor = await db.execute(
        """SELECT * FROM prompt_versions
           WHERE prompt_identifier = ?
           ORDER BY created_at DESC LIMIT ? OFFSET ?""",
        (identifier, limit, offset),
    )
    rows = await cursor.fetchall()
    return [_prompt_version_from_row(r) for r in rows]


async def set_active_version(
    db: aiosqlite.Connection, identifier: str, version_id: str
) -> None:
    """Point a prompt at a specific version as the active production version."""
    from datetime import datetime, timezone

    await db.execute(
        """UPDATE prompts
           SET active_version_id = ?, updated_at = ?
           WHERE prompt_identifier = ?""",
        (
            version_id,
            datetime.now(timezone.utc).isoformat(),
            identifier,
        ),
    )
    await db.commit()


# ---------------------------------------------------------------------------
# CRUD — Canary Labels & Canary Runs
# ---------------------------------------------------------------------------

def _canary_label_from_row(row: aiosqlite.Row) -> CanaryLabel:
    """Deserialize a canary_labels row into a CanaryLabel model."""
    return CanaryLabel(
        canary_label_id=row["canary_label_id"],
        fixture_id=row["fixture_id"],
        ticket_category=TicketCategory(row["ticket_category"]),
        judge_name=row["judge_name"],
        expected_label=JudgeLabel(row["expected_label"]),
        rationale=row["rationale"],
        created_at=row["created_at"],
    )


def _canary_run_from_row(row: aiosqlite.Row) -> CanaryRun:
    """Deserialize a canary_runs row into a CanaryRun model."""
    evidence_raw = _json_loads(row["evidence_json"], default=[])
    evidence_list: list[str] = (
        [str(item) for item in evidence_raw]
        if isinstance(evidence_raw, list)
        else []
    )
    return CanaryRun(
        canary_run_id=row["canary_run_id"],
        canary_label_id=row["canary_label_id"],
        judge_name=row["judge_name"],
        predicted_label=JudgeLabel(row["predicted_label"]),
        evidence_json=evidence_list,
        explanation=row["explanation"],
        judge_model=row["judge_model"],
        created_at=row["created_at"],
    )


async def insert_canary_label(
    db: aiosqlite.Connection, label: CanaryLabel
) -> None:
    """Insert a canary label row.

    Idempotent against UNIQUE(fixture_id, judge_name): callers may use
    INSERT OR REPLACE semantics by deleting the existing row first; this
    function uses plain INSERT to surface accidental duplicates.
    """
    await db.execute(
        """INSERT INTO canary_labels
           (canary_label_id, fixture_id, ticket_category, judge_name,
            expected_label, rationale, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            label.canary_label_id,
            label.fixture_id,
            label.ticket_category.value,
            label.judge_name,
            label.expected_label.value,
            label.rationale,
            label.created_at,
        ),
    )
    await db.commit()


async def get_canary_label(
    db: aiosqlite.Connection, canary_label_id: str
) -> CanaryLabel | None:
    """Fetch a single canary label by id."""
    cursor = await db.execute(
        "SELECT * FROM canary_labels WHERE canary_label_id = ?",
        (canary_label_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    return _canary_label_from_row(row)


async def list_canary_labels(
    db: aiosqlite.Connection, judge_name: str | None
) -> list[CanaryLabel]:
    """List canary labels, optionally filtered by judge_name."""
    if judge_name is not None:
        cursor = await db.execute(
            "SELECT * FROM canary_labels WHERE judge_name = ? "
            "ORDER BY fixture_id ASC",
            (judge_name,),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM canary_labels ORDER BY judge_name ASC, fixture_id ASC"
        )
    rows = await cursor.fetchall()
    return [_canary_label_from_row(r) for r in rows]


async def insert_canary_run(
    db: aiosqlite.Connection, run: CanaryRun
) -> None:
    """Insert a canary run row (one judge prediction on one canary fixture)."""
    await db.execute(
        """INSERT INTO canary_runs
           (canary_run_id, canary_label_id, judge_name, predicted_label,
            evidence_json, explanation, judge_model, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            run.canary_run_id,
            run.canary_label_id,
            run.judge_name,
            run.predicted_label.value,
            _json_dumps(run.evidence_json),
            run.explanation,
            run.judge_model,
            run.created_at,
        ),
    )
    await db.commit()


async def list_canary_runs(
    db: aiosqlite.Connection,
    judge_name: str | None,
    limit: int = 1000,
) -> list[CanaryRun]:
    """List canary runs newest-first, optionally filtered by judge_name."""
    if judge_name is not None:
        cursor = await db.execute(
            "SELECT * FROM canary_runs WHERE judge_name = ? "
            "ORDER BY created_at DESC LIMIT ?",
            (judge_name, limit),
        )
    else:
        cursor = await db.execute(
            "SELECT * FROM canary_runs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [_canary_run_from_row(r) for r in rows]


async def list_canary_runs_paired_with_labels(
    db: aiosqlite.Connection, judge_name: str
) -> list[tuple[CanaryLabel, CanaryRun]]:
    """Return (label, latest_run) pairs for a judge, used by kappa computation.

    Pairs each canary label with its *most recent* canary run for the
    given judge, joined on canary_label_id. Labels with no runs are
    excluded — kappa is defined only over paired observations.
    """
    cursor = await db.execute(
        """SELECT
              l.canary_label_id    AS l_canary_label_id,
              l.fixture_id         AS l_fixture_id,
              l.ticket_category    AS l_ticket_category,
              l.judge_name         AS l_judge_name,
              l.expected_label     AS l_expected_label,
              l.rationale          AS l_rationale,
              l.created_at         AS l_created_at,
              r.canary_run_id      AS r_canary_run_id,
              r.canary_label_id    AS r_canary_label_id,
              r.judge_name         AS r_judge_name,
              r.predicted_label    AS r_predicted_label,
              r.evidence_json      AS r_evidence_json,
              r.explanation        AS r_explanation,
              r.judge_model        AS r_judge_model,
              r.created_at         AS r_created_at
           FROM canary_labels l
           JOIN canary_runs r
             ON r.canary_label_id = l.canary_label_id
            AND r.judge_name = l.judge_name
            AND r.created_at = (
                SELECT MAX(r2.created_at)
                  FROM canary_runs r2
                 WHERE r2.canary_label_id = l.canary_label_id
                   AND r2.judge_name = l.judge_name
            )
           WHERE l.judge_name = ?
           ORDER BY l.fixture_id ASC""",
        (judge_name,),
    )
    rows = await cursor.fetchall()
    paired: list[tuple[CanaryLabel, CanaryRun]] = []
    for r in rows:
        evidence_raw = _json_loads(r["r_evidence_json"], default=[])
        evidence_list: list[str] = (
            [str(item) for item in evidence_raw]
            if isinstance(evidence_raw, list)
            else []
        )
        label = CanaryLabel(
            canary_label_id=r["l_canary_label_id"],
            fixture_id=r["l_fixture_id"],
            ticket_category=TicketCategory(r["l_ticket_category"]),
            judge_name=r["l_judge_name"],
            expected_label=JudgeLabel(r["l_expected_label"]),
            rationale=r["l_rationale"],
            created_at=r["l_created_at"],
        )
        run = CanaryRun(
            canary_run_id=r["r_canary_run_id"],
            canary_label_id=r["r_canary_label_id"],
            judge_name=r["r_judge_name"],
            predicted_label=JudgeLabel(r["r_predicted_label"]),
            evidence_json=evidence_list,
            explanation=r["r_explanation"],
            judge_model=r["r_judge_model"],
            created_at=r["r_created_at"],
        )
        paired.append((label, run))
    return paired


# ---------------------------------------------------------------------------
# Seed
# ---------------------------------------------------------------------------

async def _seed_default_prompt(db: aiosqlite.Connection) -> None:
    """Seed the support-agent prompt and v1.0.0 version if not present.

    Idempotent: a second call observes the existing prompt and is a no-op.
    """
    import uuid
    from datetime import datetime, timezone

    from src.agent.prompts import DEFAULT_SYSTEM_PROMPT

    existing = await get_prompt(db, "support-agent")
    if existing is not None:
        logger.debug("Default prompt already seeded; skipping")
        return

    now = datetime.now(timezone.utc).isoformat()
    version_id = str(uuid.uuid4())

    await insert_prompt(
        db,
        Prompt(
            prompt_identifier="support-agent",
            description="Helios customer support agent",
            active_version_id=None,
            created_at=now,
            updated_at=now,
        ),
    )
    await insert_prompt_version(
        db,
        PromptVersion(
            prompt_version_id=version_id,
            prompt_identifier="support-agent",
            version_tag="v1.0.0",
            prompt_text=DEFAULT_SYSTEM_PROMPT,
            source=PromptSource.SEED,
            created_at=now,
        ),
    )
    await set_active_version(db, "support-agent", version_id)
    logger.info("Seeded default prompt v1.0.0 (id=%s)", version_id)
