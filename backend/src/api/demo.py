"""Demo, health, and audit API routes."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import httpx
from fastapi import APIRouter, Depends

from src.api.dependencies import PaginationParams, get_db_session, get_request_id
from src.config import Settings
from src.models import (
    ApiResponse,
    AuditEvent,
    HealthCheck,
    HealthResponse,
    PaginatedData,
    SupportTicket,
    TicketCategory,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["demo"])

# Resolve project root from this file's location:
# backend/src/api/demo.py -> parent x4 = project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_TICKETS_SEED_PATH = _PROJECT_ROOT / "data" / "tickets" / "tickets_seed.jsonl"

# Map categories from the seed file that don't exist in TicketCategory to a valid value.
_CATEGORY_FALLBACK: dict[str, TicketCategory] = {
    "safety_canary": TicketCategory.AMBIGUOUS,
}


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

_SEED_TICKETS = [
    SupportTicket(
        ticket_id="demo-ticket-001",
        customer_id="cust-100",
        category=TicketCategory.REFUND,
        subject="Refund for duplicate charge",
        body=(
            "Hi, I was charged twice for my subscription this month. "
            "Order ID: ORD-9981. Please refund the duplicate charge of $49.99. "
            "I've been a customer for 3 years and this has never happened before."
        ),
        metadata_json={"order_id": "ORD-9981", "amount": 49.99},
        created_at="2026-05-01T10:00:00Z",
        updated_at="2026-05-01T10:00:00Z",
    ),
    SupportTicket(
        ticket_id="demo-ticket-002",
        customer_id="cust-200",
        category=TicketCategory.BILLING,
        subject="Upgrade to enterprise plan",
        body=(
            "We'd like to upgrade from the Team plan to Enterprise. "
            "We have 150 users currently. Can you walk me through the pricing "
            "and what features we get? Also, will our data be migrated automatically?"
        ),
        metadata_json={"current_plan": "team", "user_count": 150},
        created_at="2026-05-02T14:30:00Z",
        updated_at="2026-05-02T14:30:00Z",
    ),
    SupportTicket(
        ticket_id="demo-ticket-003",
        customer_id="cust-300",
        category=TicketCategory.PRIVACY,
        subject="GDPR data deletion request",
        body=(
            "Under GDPR Article 17, I request complete deletion of all my personal "
            "data from your systems. My account email is user@example.com. "
            "Please confirm within 30 days as required by law."
        ),
        metadata_json={"regulation": "GDPR", "article": "17"},
        created_at="2026-05-03T09:15:00Z",
        updated_at="2026-05-03T09:15:00Z",
    ),
    SupportTicket(
        ticket_id="demo-ticket-004",
        customer_id="cust-400",
        category=TicketCategory.ADMIN_ACCESS,
        subject="Need admin access for new team lead",
        body=(
            "Our new team lead Sarah (sarah@acme.com) needs admin access to the "
            "dashboard. She's replacing John who left last week. Please also "
            "revoke John's access (john@acme.com)."
        ),
        metadata_json={
            "new_admin": "sarah@acme.com",
            "revoke_admin": "john@acme.com",
        },
        created_at="2026-05-04T11:00:00Z",
        updated_at="2026-05-04T11:00:00Z",
    ),
    SupportTicket(
        ticket_id="demo-ticket-005",
        customer_id="cust-500",
        category=TicketCategory.OUTAGE_CREDIT,
        subject="Credit request for Monday outage",
        body=(
            "Our team was unable to use the platform for 4 hours during Monday's "
            "outage (May 5, 2026, 2pm-6pm UTC). This affected our sprint delivery. "
            "We'd like a credit applied to our next invoice."
        ),
        metadata_json={
            "outage_date": "2026-05-05",
            "duration_hours": 4,
        },
        created_at="2026-05-06T08:00:00Z",
        updated_at="2026-05-06T08:00:00Z",
    ),
    SupportTicket(
        ticket_id="demo-ticket-006",
        customer_id="cust-600",
        category=TicketCategory.LEGAL,
        subject="DPA and SOC 2 compliance documents",
        body=(
            "Our legal team needs your Data Processing Agreement and SOC 2 Type II "
            "report before we can proceed with the enterprise contract. "
            "Can you share these documents?"
        ),
        metadata_json={"documents_needed": ["DPA", "SOC2"]},
        created_at="2026-05-07T16:45:00Z",
        updated_at="2026-05-07T16:45:00Z",
    ),
    SupportTicket(
        ticket_id="demo-ticket-007",
        customer_id="cust-700",
        category=TicketCategory.AMBIGUOUS,
        subject="Having issues",
        body=(
            "Things aren't working right. Can someone help?"
        ),
        metadata_json={},
        created_at="2026-05-08T13:20:00Z",
        updated_at="2026-05-08T13:20:00Z",
    ),
]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _load_jsonl_tickets() -> list[SupportTicket]:
    """Load supplementary tickets from the JSONL seed file.

    Returns an empty list (with a warning) if the file does not exist so the
    seed endpoint still works in environments that lack the data directory.
    """
    if not _TICKETS_SEED_PATH.exists():
        logger.warning("Tickets seed file not found at %s — skipping JSONL load", _TICKETS_SEED_PATH)
        return []

    tickets: list[SupportTicket] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    with _TICKETS_SEED_PATH.open(encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                logger.warning("Skipping malformed JSON on line %d of seed file", line_no)
                continue

            raw_category = data.get("category", "ambiguous")
            try:
                category = TicketCategory(raw_category)
            except ValueError:
                category = _CATEGORY_FALLBACK.get(raw_category, TicketCategory.AMBIGUOUS)
                logger.debug(
                    "Unmapped category %r on line %d — using %s",
                    raw_category,
                    line_no,
                    category,
                )

            tickets.append(
                SupportTicket(
                    ticket_id=data["ticket_id"],
                    customer_id=data.get("customer_id", "cust-unknown"),
                    category=category,
                    subject=data.get("subject", ""),
                    body=data.get("body", ""),
                    metadata_json={
                        k: v
                        for k, v in data.items()
                        if k not in {
                            "ticket_id", "customer_id", "category",
                            "subject", "body", "created_at", "updated_at",
                        }
                    },
                    created_at=data.get("created_at", now_iso),
                    updated_at=data.get("updated_at", now_iso),
                )
            )

    logger.info("Loaded %d tickets from JSONL seed file", len(tickets))
    return tickets


@router.post("/demo/seed")
async def seed_demo_data(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Seed demo data. Fully idempotent -- safe to call repeatedly.

    Seeds the 7 primary demo tickets (hardcoded) plus up to 61 supplementary
    tickets from ``data/tickets/tickets_seed.jsonl``.
    """
    from src.db import get_ticket, insert_audit_event, insert_ticket

    seeded_count = 0
    skipped_count = 0

    # Build the full list: primary demo tickets + JSONL supplementary tickets.
    jsonl_tickets = _load_jsonl_tickets()
    all_tickets = _SEED_TICKETS + jsonl_tickets
    total_count = len(all_tickets)

    logger.info("Demo seed: processing %d total tickets (%d primary, %d from JSONL)",
                total_count, len(_SEED_TICKETS), len(jsonl_tickets))

    for ticket in all_tickets:
        existing = await get_ticket(db, ticket.ticket_id)
        if existing:
            skipped_count += 1
            continue
        await insert_ticket(db, ticket)
        seeded_count += 1

    # Audit the seed operation
    await insert_audit_event(
        db,
        AuditEvent(
            audit_event_id=str(uuid.uuid4()),
            entity_type="demo",
            entity_id="seed",
            action="seed_data",
            actor="system",
            detail_json={
                "tickets_seeded": seeded_count,
                "tickets_skipped": skipped_count,
                "total_tickets": total_count,
                "primary_tickets": len(_SEED_TICKETS),
                "jsonl_tickets": len(jsonl_tickets),
            },
            created_at=datetime.now(timezone.utc).isoformat(),
        ),
    )

    logger.info(
        "Demo seed complete: %d seeded, %d skipped (total %d)",
        seeded_count,
        skipped_count,
        total_count,
    )

    return ApiResponse(
        ok=True,
        data={
            "tickets_seeded": seeded_count,
            "tickets_skipped": skipped_count,
            "total_tickets": total_count,
        },
        request_id=request_id,
    )


@router.post("/demo/run-all")
async def run_all_demo(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Run the agent on the first 5 seeded tickets to prime the system with data.

    Errors on individual tickets are captured and reported rather than aborting
    the entire batch, so partial results are always returned.
    """
    from src.agent.support_agent import run_agent
    from src.db import (
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
    )
    from src.db import (
        list_tickets as db_list_tickets,
    )
    from src.diagnosis.failure_aggregator import check_thresholds, update_aggregates
    from src.evaluation.runner import run_all_evals
    from src.models import ConversationSession
    from src.tracing.phoenix_client import get_phoenix_client

    BATCH_SIZE = 5

    # Fetch the first BATCH_SIZE tickets (ordered by created_at DESC inside
    # list_tickets, so we use a large page_size and take the first slice).
    tickets, _ = await db_list_tickets(db, category=None, page=1, page_size=BATCH_SIZE)

    if not tickets:
        return ApiResponse(
            ok=False,
            error="No tickets found. Call POST /demo/seed first.",
            request_id=request_id,
        )

    phoenix = get_phoenix_client()
    results: list[dict] = []
    errors: list[dict] = []

    for ticket in tickets:
        ticket_id = ticket.ticket_id
        try:
            now = datetime.now(timezone.utc).isoformat()
            session_id = str(uuid.uuid4())

            session = ConversationSession(
                conversation_session_id=session_id,
                ticket_id=ticket_id,
                started_at=now,
                turn_count=1,
            )
            await insert_conversation_session(db, session)

            agent_run = await run_agent(ticket, session_id, db, phoenix)
            await insert_agent_run(db, agent_run)

            eval_results = await run_all_evals(agent_run, ticket, phoenix)
            for result in eval_results:
                await insert_eval_result(db, result)

            await update_aggregates(eval_results, db)
            triggers = await check_thresholds(db, eval_results)

            results.append({
                "ticket_id": ticket_id,
                "agent_run_id": agent_run.agent_run_id,
                "status": agent_run.status,
                "eval_count": len(eval_results),
                "triggers_created": len(triggers),
            })

            logger.info(
                "run-all: ticket %s processed — run=%s, evals=%d, triggers=%d",
                ticket_id,
                agent_run.agent_run_id,
                len(eval_results),
                len(triggers),
            )

        except Exception:
            logger.exception("run-all: error processing ticket %s", ticket_id)
            errors.append({"ticket_id": ticket_id, "error": "processing failed — see server logs"})

    logger.info(
        "run-all complete: %d succeeded, %d failed (of %d attempted)",
        len(results),
        len(errors),
        len(tickets),
    )

    return ApiResponse(
        ok=True,
        data={
            "attempted": len(tickets),
            "succeeded": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        },
        request_id=request_id,
    )


@router.get("/audit")
async def list_audit_events(
    entity_type: str | None = None,
    pagination: PaginationParams = Depends(),
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Query audit events with optional entity_type filter and pagination."""
    from src.db import list_audit_events as db_list_audit_events

    items, total = await db_list_audit_events(
        db, entity_type, pagination.page, pagination.page_size
    )
    return ApiResponse(
        ok=True,
        data=PaginatedData(
            items=items,
            total_count=total,
            page=pagination.page,
            page_size=pagination.page_size,
            has_next=(pagination.page * pagination.page_size) < total,
        ),
        request_id=request_id,
    )


@router.post("/demo/full-loop")
async def full_loop_demo(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Synthesize 5 failure-cluster runs to walk the healing loop in <90s.

    Designed for the demo video and the "Watch it heal" CTA. Synthesizes
    repeated failures with a shared ``failure_key`` so the threshold logic
    creates a ``pending_diagnosis`` trigger deterministically.
    """
    from src.db import (
        get_ticket,
        insert_agent_run,
        insert_conversation_session,
        insert_eval_result,
        insert_ticket,
    )
    from src.diagnosis.failure_aggregator import check_thresholds, update_aggregates
    from src.models import (
        AgentRun,
        AnnotationLevel,
        ConversationSession,
        EvalResult,
        EvalType,
        ToolCallRecord,
    )

    SYNTHESIZED_RUNS = 5
    SYNTHETIC_FAILURE_KEY = "citation_presence::demo-synthetic-cluster"
    DEMO_TICKET_ID = "demo-ticket-001"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Ensure the demo ticket exists (full-loop is safe to call before /seed too).
    if await get_ticket(db, DEMO_TICKET_ID) is None:
        await insert_ticket(
            db,
            SupportTicket(
                ticket_id=DEMO_TICKET_ID,
                customer_id="cust-100",
                category=TicketCategory.REFUND,
                subject="Refund for duplicate charge",
                body="Demo ticket for full-loop synthesis.",
                metadata_json={},
                created_at=now_iso,
                updated_at=now_iso,
            ),
        )

    synthesized_run_ids: list[str] = []
    all_eval_results: list[EvalResult] = []

    for i in range(SYNTHESIZED_RUNS):
        session_id = str(uuid.uuid4())
        await insert_conversation_session(
            db,
            ConversationSession(
                conversation_session_id=session_id,
                ticket_id=DEMO_TICKET_ID,
                started_at=now_iso,
                turn_count=1,
            ),
        )

        run_id = str(uuid.uuid4())
        agent_run = AgentRun(
            agent_run_id=run_id,
            conversation_session_id=session_id,
            ticket_id=DEMO_TICKET_ID,
            agent_name="helios_support_agent",
            agent_version="1.0.0",
            prompt_version="production",
            trace_id=None,
            root_span_id=None,
            phoenix_session_id=None,
            response_json={
                "answer": f"[synthetic demo failure #{i + 1}] No citation provided",
                "citations": [],
                "tools_used": ["search_policy"],
                "escalated": False,
                "escalation_reason": None,
                "confidence": 0.4,
            },
            tool_calls_json=[
                ToolCallRecord(
                    tool_name="search_policy",
                    input={"query": "refund window"},
                    output={"found": False, "excerpts": [], "source": None},
                    status="success",
                    latency_ms=42,
                )
            ],
            status="success",
            latency_ms=120,
            token_count_input=None,
            token_count_output=None,
            prompt_version_id=None,
            created_at=now_iso,
        )
        await insert_agent_run(db, agent_run)
        synthesized_run_ids.append(run_id)

        eval_result = EvalResult(
            eval_result_id=str(uuid.uuid4()),
            agent_run_id=run_id,
            evaluator_name="citation_presence",
            eval_type=EvalType.CODE,
            outcome="fail",
            score=0.0,
            explanation="Synthetic demo failure: missing citation",
            failure_key=SYNTHETIC_FAILURE_KEY,
            failure_summary="Demo cluster: citation missing on policy answer",
            annotation_level=AnnotationLevel.SPAN,
            created_at=now_iso,
        )
        await insert_eval_result(db, eval_result)
        all_eval_results.append(eval_result)

    await update_aggregates(all_eval_results, db)
    triggers = await check_thresholds(db, all_eval_results)

    logger.info(
        "full-loop demo: synthesized %d runs, created %d trigger(s)",
        SYNTHESIZED_RUNS,
        len(triggers),
    )

    return ApiResponse(
        ok=True,
        data={
            "synthesized_runs": SYNTHESIZED_RUNS,
            "synthesized_run_ids": synthesized_run_ids,
            "failure_key": SYNTHETIC_FAILURE_KEY,
            "trigger_created": len(triggers) > 0,
            "trigger_ids": [t.improvement_trigger_id for t in triggers],
        },
        request_id=request_id,
    )


async def _probe_phoenix(settings: Settings) -> HealthCheck:
    """Probe Phoenix Cloud via a lightweight authenticated GET."""
    if not settings.phoenix_api_key:
        logger.warning("Phoenix probe skipped: PHOENIX_API_KEY not set")
        return HealthCheck(ok=False, detail="PHOENIX_API_KEY not set")
    url = f"{settings.phoenix_base_url}/v1/annotation_configs"
    headers = {"Authorization": f"Bearer {settings.phoenix_api_key}"}
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url, headers=headers)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if res.status_code == 200:
            logger.debug("Phoenix probe ok in %d ms", elapsed_ms)
            return HealthCheck(ok=True, detail="200 OK", response_ms=elapsed_ms)
        logger.warning("Phoenix probe HTTP %d (%d ms)", res.status_code, elapsed_ms)
        return HealthCheck(
            ok=False, detail=f"HTTP {res.status_code}", response_ms=elapsed_ms
        )
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Phoenix probe failed: %s", exc)
        return HealthCheck(ok=False, detail=str(exc)[:120])


async def _probe_gemini(settings: Settings) -> HealthCheck:
    """Probe the Gemini API via models.list."""
    if not settings.google_api_key:
        logger.warning("Gemini probe skipped: GOOGLE_API_KEY not set")
        return HealthCheck(ok=False, detail="GOOGLE_API_KEY not set")
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models"
        f"?key={settings.google_api_key}&pageSize=1"
    )
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.get(url)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        if res.status_code == 200:
            logger.debug("Gemini probe ok in %d ms", elapsed_ms)
            return HealthCheck(
                ok=True, detail="models.list 200", response_ms=elapsed_ms
            )
        logger.warning("Gemini probe HTTP %d (%d ms)", res.status_code, elapsed_ms)
        return HealthCheck(
            ok=False, detail=f"HTTP {res.status_code}", response_ms=elapsed_ms
        )
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("Gemini probe failed: %s", exc)
        return HealthCheck(ok=False, detail=str(exc)[:120])


@router.get("/health")
async def health_check(
    request_id: str = Depends(get_request_id),
    db: aiosqlite.Connection = Depends(get_db_session),
) -> ApiResponse:
    """Health check endpoint with parallel probes for Phoenix and Gemini."""
    from src.config import get_settings

    settings = get_settings()

    # Database check — reaching this handler proves the dependency-injected
    # connection is open. Run a trivial query to confirm responsiveness.
    try:
        await db.execute("SELECT 1")
        db_check = HealthCheck(ok=True, detail="SQLite WAL mode, reachable")
    except aiosqlite.Error as exc:
        logger.error("Database probe failed: %s", exc)
        db_check = HealthCheck(ok=False, detail=str(exc)[:120])

    phoenix_check, gemini_check = await asyncio.gather(
        _probe_phoenix(settings), _probe_gemini(settings)
    )

    all_ok = all([db_check.ok, phoenix_check.ok, gemini_check.ok])
    response = HealthResponse(
        status="healthy" if all_ok else "degraded",
        service="phoenixloop",
        version="0.1.0",
        checks={
            "database": db_check,
            "phoenix": phoenix_check,
            "gemini": gemini_check,
        },
    )
    return ApiResponse(ok=True, data=response, request_id=request_id)
