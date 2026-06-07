"""Agent tool functions for the Helios support agent.

The agent has four tools. ``get_customer_context`` consolidates everything
the agent used to ask in three separate round trips (``lookup_customer``,
``lookup_subscription``, ``check_refund_eligibility``) into one call —
returns the profile, the subscription, computed entitlements (including
refund eligibility + reason), and recent ticket history.

``search_policy`` is the policy RAG. ``create_escalation`` is the only
write action. ``retrieve_similar_resolutions`` is the few-shot retrieval
hook — fetches the top-3 closest examples from the
``successful-resolutions`` Phoenix dataset so the model can ground its
response in prior, successfully-resolved tickets.

The agent's structured response (the answer text + citations + escalation
flag) is emitted directly as JSON in the final model turn, not via a tool —
that's why there is no ``draft_customer_response`` here any more. The
older pass-through tool forced a pointless Gemini → tool → Gemini ping-pong
on every single ticket and consumed a tool slot we now spend on
``get_customer_context``.
"""

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.tracing.phoenix_client import get_phoenix_client

logger = logging.getLogger(__name__)

# Resolve project root from this file's location:
# backend/src/agent/tools.py -> parent x4 = project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Category-to-filename mapping for policy search
# ---------------------------------------------------------------------------
CATEGORY_FILE_MAP: dict[str, str] = {
    "refund": "refunds.md",
    "billing": "billing.md",
    "privacy": "privacy.md",
    "admin_access": "admin_access.md",
    "outage_credit": "outage_credit.md",
    "escalation": "escalation.md",
    "legal": "escalation.md",
}

REFUND_WINDOW_DAYS = 30


# ---------------------------------------------------------------------------
# Tool 1: search_policy
# ---------------------------------------------------------------------------

def search_policy(query: str, category: str) -> dict:
    """Search Helios policy documents for relevant excerpts.

    Looks up policy markdown files in the data/policies directory and returns
    paragraphs containing keywords from the query.

    Args:
        query: Free-text search query (e.g. "refund eligibility window").
        category: Policy category to search. One of: refund, billing, privacy,
            admin_access, outage_credit, escalation, legal. If unrecognized,
            all policy files are searched.

    Returns:
        A dict with keys: found (bool), source (str|None), excerpts (list[str]),
        query (str).
    """
    policies_dir = PROJECT_ROOT / "data" / "policies"

    if not policies_dir.exists():
        logger.error("Policies directory not found at %s", policies_dir)
        return {"found": False, "source": None, "excerpts": [], "query": query}

    if category in CATEGORY_FILE_MAP:
        target_files = [policies_dir / CATEGORY_FILE_MAP[category]]
    else:
        target_files = sorted(policies_dir.glob("*.md"))

    keywords = [kw.lower() for kw in query.split() if kw.strip()]

    for filepath in target_files:
        if not filepath.exists():
            logger.warning("Policy file not found: %s", filepath)
            continue

        try:
            content = filepath.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("Failed to read policy file %s: %s", filepath, exc)
            continue

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        matching = [
            p for p in paragraphs
            if any(kw in p.lower() for kw in keywords)
        ]

        if matching:
            logger.info(
                "Policy search hit: query=%r, file=%s, matches=%d",
                query, filepath.name, len(matching),
            )
            return {
                "found": True,
                "source": filepath.name,
                "excerpts": matching,
                "query": query,
            }

    logger.info("Policy search miss: query=%r, category=%r", query, category)
    return {"found": False, "source": None, "excerpts": [], "query": query}


# ---------------------------------------------------------------------------
# Tool 2: get_customer_context (consolidated)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_customers() -> list[dict]:
    path = PROJECT_ROOT / "data" / "customers.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("Customer data file not found at %s", path)
        return []
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in customer data: %s", exc)
        return []


@lru_cache(maxsize=1)
def _load_subscriptions() -> list[dict]:
    path = PROJECT_ROOT / "data" / "subscriptions.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("Subscription data file not found at %s", path)
        return []
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in subscription data: %s", exc)
        return []


@lru_cache(maxsize=1)
def _load_tickets() -> list[dict]:
    path = PROJECT_ROOT / "data" / "tickets" / "tickets_seed.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load seeded tickets from %s: %s", path, exc)
        return []
    return out


def _compute_entitlements(subscription: dict | None) -> dict:
    """Compute refund eligibility + reason from a subscription record.

    Returns a dict with refund_eligible (bool), refund_reason (str), and —
    when eligible — refund_type ("full" | "pro_rata"), refund_amount (float),
    days_since_last_payment (int). Lives next to the subscription lookup so
    the agent gets one consistent view instead of asking three times.
    """
    if subscription is None:
        return {
            "refund_eligible": False,
            "refund_reason": "No subscription on file for this customer.",
            "refund_type": None,
            "refund_amount": None,
            "days_since_last_payment": None,
        }

    plan = (subscription.get("plan") or "").lower()
    status = subscription.get("status") or ""

    if plan == "enterprise":
        return {
            "refund_eligible": False,
            "refund_reason": (
                "Enterprise refunds are handled exclusively by the Account "
                "Management team — escalate via create_escalation rather "
                "than promising a refund directly."
            ),
            "refund_type": None,
            "refund_amount": None,
            "days_since_last_payment": None,
        }

    if plan == "free":
        return {
            "refund_eligible": False,
            "refund_reason": "Free plan has no charges to refund.",
            "refund_type": None,
            "refund_amount": None,
            "days_since_last_payment": None,
        }

    if status not in ("active", "past_due", "canceled"):
        return {
            "refund_eligible": False,
            "refund_reason": (
                f"Subscription status '{status}' is not eligible for refund."
            ),
            "refund_type": None,
            "refund_amount": None,
            "days_since_last_payment": None,
        }

    last_payment_str = subscription.get("last_payment_date")
    if not last_payment_str:
        return {
            "refund_eligible": False,
            "refund_reason": "No payment history found for this subscription.",
            "refund_type": None,
            "refund_amount": None,
            "days_since_last_payment": None,
        }

    last_payment = datetime.strptime(last_payment_str, "%Y-%m-%d")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    days_since = (now - last_payment).days

    if status == "canceled":
        canceled_at_str = subscription.get("canceled_at")
        if canceled_at_str:
            canceled_at = datetime.strptime(canceled_at_str, "%Y-%m-%d")
            if (now - canceled_at).days > REFUND_WINDOW_DAYS:
                return {
                    "refund_eligible": False,
                    "refund_reason": (
                        f"Cancellation on {canceled_at_str} is outside the "
                        f"{REFUND_WINDOW_DAYS}-day refund window."
                    ),
                    "refund_type": None,
                    "refund_amount": None,
                    "days_since_last_payment": days_since,
                }

    if days_since > REFUND_WINDOW_DAYS:
        return {
            "refund_eligible": False,
            "refund_reason": (
                f"Last payment was {days_since} days ago — outside the "
                f"{REFUND_WINDOW_DAYS}-day refund window."
            ),
            "refund_type": None,
            "refund_amount": None,
            "days_since_last_payment": days_since,
        }

    billing_cycle = subscription.get("billing_cycle", "monthly")
    monthly_amount = subscription.get("monthly_amount", 0)

    if billing_cycle == "annual":
        months_used = max(1, days_since // 30)
        remaining_months = max(0, 12 - months_used)
        amount = round(float(monthly_amount) * remaining_months, 2)
        refund_type = "pro_rata"
    else:
        refund_type = "full"
        amount = float(monthly_amount)

    return {
        "refund_eligible": True,
        "refund_reason": (
            f"Within {REFUND_WINDOW_DAYS}-day refund window "
            f"(last payment {days_since} days ago)."
        ),
        "refund_type": refund_type,
        "refund_amount": amount,
        "days_since_last_payment": days_since,
    }


def get_customer_context(customer_id: str) -> dict:
    """Return everything you need to know about a customer in one call.

    Folds the previous lookup_customer + lookup_subscription +
    check_refund_eligibility chain into a single tool span. The agent should
    call this ONCE per ticket — there is no reason to ask for any of these
    pieces separately. The returned ``entitlements`` block already tells you
    whether a refund is permissible and *why*; you should not re-derive
    that logic in the answer.

    Args:
        customer_id: Helios customer identifier (e.g. ``"cus_5WvnX4nq"``).

    Returns:
        A dict with the keys below. Always returns a dict — never raises.
            - ``found`` (bool): True iff a profile row exists.
            - ``customer_id`` (str): echoed back for logging.
            - ``profile`` (dict | None): {name, email, plan, signup_date,
              workspace_role}, or None if not found.
            - ``subscription`` (dict | None): full subscription record, or
              None if not found.
            - ``entitlements`` (dict): {refund_eligible, refund_reason,
              refund_type, refund_amount, days_since_last_payment}. Always
              present, even for unknown customers (so the agent never has
              to handle a missing field).
            - ``recent_tickets`` (list[dict]): up to 5 prior tickets for
              this customer (ticket_id, subject, category only — body
              omitted to keep token cost flat).
            - ``error`` (str, optional): present only when the customer
              wasn't found.
    """
    customers = _load_customers()
    profile = next(
        (c for c in customers if c.get("customer_id") == customer_id),
        None,
    )

    if profile is None:
        logger.info("Customer not found: %s", customer_id)
        return {
            "found": False,
            "customer_id": customer_id,
            "profile": None,
            "subscription": None,
            "entitlements": _compute_entitlements(None),
            "recent_tickets": [],
            "error": "Customer not found",
        }

    subscriptions = _load_subscriptions()
    subscription = next(
        (s for s in subscriptions if s.get("customer_id") == customer_id),
        None,
    )

    tickets = _load_tickets()
    recent = [
        {
            "ticket_id": t["ticket_id"],
            "subject": t["subject"],
            "category": t["category"],
        }
        for t in tickets
        if t.get("customer_id") == customer_id
    ][-5:]

    entitlements = _compute_entitlements(subscription)

    logger.info(
        "Customer context resolved: %s (plan=%s, refund_eligible=%s)",
        customer_id,
        profile.get("plan"),
        entitlements["refund_eligible"],
    )

    return {
        "found": True,
        "customer_id": customer_id,
        "profile": {
            "name": profile.get("name"),
            "email": profile.get("email"),
            "plan": profile.get("plan"),
            "signup_date": profile.get("signup_date"),
            "workspace_role": profile.get("workspace_role"),
        },
        "subscription": subscription,
        "entitlements": entitlements,
        "recent_tickets": recent,
    }


# ---------------------------------------------------------------------------
# Tool 3: retrieve_similar_resolutions (Phoenix dataset few-shot retrieval)
# ---------------------------------------------------------------------------

SUCCESSFUL_RESOLUTIONS_DATASET = "successful-resolutions"
RETRIEVAL_TOP_K = 3
_RETRIEVAL_CACHE_TTL_SECONDS = 300.0
_retrieval_cache: dict[str, tuple[float, dict]] = {}


def _score_example_for_query(
    example_metadata: dict, category: str, brief_lower: str
) -> int:
    """Cheap deterministic relevance score for picking the top-3.

    Same-category examples win; among those, keyword overlap with the brief
    breaks ties. The agent does the real ranking once it sees the examples;
    this is just the floor that keeps us from returning hopelessly off-topic
    prior tickets.
    """
    score = 0
    if (example_metadata.get("category") or "").lower() == category.lower():
        score += 1000
    tags = example_metadata.get("tags") or []
    if isinstance(tags, (list, tuple)):
        for tag in tags:
            if isinstance(tag, str) and tag.lower() in brief_lower:
                score += 10
    return score


def _summarize_example(example: dict) -> dict:
    """Trim a Phoenix DatasetExample down to what fits in a Flash prompt."""
    input_payload = example.get("input") or {}
    output_payload = example.get("output") or {}
    metadata = example.get("metadata") or {}

    subject = (
        input_payload.get("subject")
        or input_payload.get("title")
        or ""
    )
    body = (
        input_payload.get("body")
        or input_payload.get("question")
        or ""
    )
    answer = (
        output_payload.get("answer")
        or output_payload.get("response")
        or ""
    )
    citations = output_payload.get("citations") or []

    # Cap text fields to keep token cost flat — three full-length tickets
    # would dominate the prompt otherwise.
    return {
        "id": example.get("id"),
        "category": metadata.get("category"),
        "subject": subject[:200],
        "input_summary": body[:400],
        "exemplar_answer": answer[:600],
        "exemplar_citations": citations if isinstance(citations, list) else [],
    }


def retrieve_similar_resolutions(category: str, brief: str) -> dict:
    """Fetch up to 3 prior successfully-resolved tickets from Phoenix.

    Reads the ``successful-resolutions`` Phoenix dataset (seeded by
    ``demo.full_loop_seed``), filters to examples whose metadata.category
    matches ``category``, ranks by category match + keyword overlap with
    ``brief``, and returns the top 3 trimmed into a Flash-friendly shape.

    Call this BEFORE drafting any non-trivial response. The returned IDs
    must appear in the final response's ``examples_used`` field so the
    eval pipeline can attribute which examples helped.

    Degrades gracefully when:
    - ``PHOENIX_API_KEY`` is unset (local dev without credentials)
    - The dataset hasn't been seeded yet (first cold start)
    - The Phoenix call fails (network, auth)
    In all those cases ``found`` is ``False`` and ``examples`` is ``[]``; the
    agent should answer from its own knowledge and leave ``examples_used``
    empty in its final JSON.

    Args:
        category: The ticket category (e.g. ``"refund"``, ``"admin_access"``).
        brief: A short free-text summary of the customer's question — used
            for keyword-overlap ranking.

    Returns:
        ``{"found": bool, "dataset": str, "examples": list[dict], "reason": str | None}``.
        Each example dict has ``id``, ``category``, ``subject``,
        ``input_summary``, ``exemplar_answer``, ``exemplar_citations``.
    """
    cache_key = f"{category.lower()}|{brief.lower()[:200]}"
    cached = _retrieval_cache.get(cache_key)
    if cached is not None and (time.monotonic() - cached[0]) < _RETRIEVAL_CACHE_TTL_SECONDS:
        return cached[1]

    settings = get_settings()
    if not settings.phoenix_api_key:
        result = {
            "found": False,
            "dataset": SUCCESSFUL_RESOLUTIONS_DATASET,
            "examples": [],
            "reason": "PHOENIX_API_KEY not set — running without few-shot exemplars.",
        }
        _retrieval_cache[cache_key] = (time.monotonic(), result)
        return result

    phoenix = get_phoenix_client()
    if phoenix is None:
        result = {
            "found": False,
            "dataset": SUCCESSFUL_RESOLUTIONS_DATASET,
            "examples": [],
            "reason": "Phoenix client unavailable.",
        }
        _retrieval_cache[cache_key] = (time.monotonic(), result)
        return result

    try:
        dataset = phoenix.datasets.get_dataset(
            dataset=SUCCESSFUL_RESOLUTIONS_DATASET
        )
    except Exception as exc:
        # Dataset doesn't exist yet, network error, auth error — all
        # treated the same: degrade silently, log loudly.
        logger.warning(
            "Phoenix dataset %r unavailable (%s); few-shot retrieval skipped",
            SUCCESSFUL_RESOLUTIONS_DATASET,
            exc,
        )
        result = {
            "found": False,
            "dataset": SUCCESSFUL_RESOLUTIONS_DATASET,
            "examples": [],
            "reason": f"Dataset lookup failed: {exc.__class__.__name__}",
        }
        _retrieval_cache[cache_key] = (time.monotonic(), result)
        return result

    raw_examples: list[Any] = list(getattr(dataset, "examples", []) or [])

    # Phoenix returns DatasetExample TypedDicts; normalize via .get on dicts.
    scored: list[tuple[int, dict]] = []
    brief_lower = brief.lower()
    for ex in raw_examples:
        if isinstance(ex, dict):
            metadata = ex.get("metadata") or {}
            score = _score_example_for_query(metadata, category, brief_lower)
            scored.append((score, ex))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = [_summarize_example(ex) for score, ex in scored[:RETRIEVAL_TOP_K] if score > 0]

    if not top:
        result = {
            "found": False,
            "dataset": SUCCESSFUL_RESOLUTIONS_DATASET,
            "examples": [],
            "reason": (
                f"No examples in {SUCCESSFUL_RESOLUTIONS_DATASET} matched "
                f"category '{category}'."
            ),
        }
        _retrieval_cache[cache_key] = (time.monotonic(), result)
        return result

    result = {
        "found": True,
        "dataset": SUCCESSFUL_RESOLUTIONS_DATASET,
        "examples": top,
        "reason": None,
    }
    _retrieval_cache[cache_key] = (time.monotonic(), result)
    logger.info(
        "Few-shot retrieval hit: category=%s, returned=%d (cap=%d)",
        category, len(top), RETRIEVAL_TOP_K,
    )
    return result


# ---------------------------------------------------------------------------
# Tool 4: create_escalation
# ---------------------------------------------------------------------------

def create_escalation(ticket_id: str, reason: str, target_team: str) -> dict:
    """Create an escalation record for a support ticket.

    Generates a unique escalation ID and returns a confirmation record.
    No database write is performed — the record is returned for the agent
    to reference in its response.

    Args:
        ticket_id: The support ticket being escalated.
        reason: Human-readable reason for escalation.
        target_team: The team to escalate to (e.g. "Legal", "Security",
            "Account Management", "Engineering", "Billing").

    Returns:
        A dict with escalation_id, ticket_id, target_team, reason, status.
    """
    escalation_id = f"ESC-{uuid.uuid4().hex[:8]}"
    logger.info(
        "Escalation created: id=%s, ticket=%s, team=%s",
        escalation_id, ticket_id, target_team,
    )
    return {
        "escalation_id": escalation_id,
        "ticket_id": ticket_id,
        "target_team": target_team,
        "reason": reason,
        "status": "created",
    }
