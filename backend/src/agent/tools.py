"""Agent tool functions for the AcmeFlow support agent.

Each function is a plain Python function that Google ADK wraps as a tool.
Tools load data from the ``data/`` directory using pathlib for path resolution.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

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


# ---------------------------------------------------------------------------
# Tool 1: search_policy
# ---------------------------------------------------------------------------

def search_policy(query: str, category: str) -> dict:
    """Search AcmeFlow policy documents for relevant excerpts.

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

    # Determine which files to search
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

        # Split into paragraphs (double-newline separated)
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
# Tool 2: lookup_customer
# ---------------------------------------------------------------------------

def lookup_customer(customer_id: str) -> dict:
    """Look up an AcmeFlow customer by their customer ID.

    Loads the customer database and returns the matching customer record.

    Args:
        customer_id: The unique customer identifier (e.g. "CUST-001").

    Returns:
        The customer dict if found, or an error dict with customer_id.
    """
    customers_path = PROJECT_ROOT / "data" / "customers.json"

    try:
        customers: list[dict] = json.loads(customers_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.error("Customer data file not found at %s", customers_path)
        return {"error": "Customer data unavailable", "customer_id": customer_id}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in customer data: %s", exc)
        return {"error": "Customer data corrupted", "customer_id": customer_id}

    for customer in customers:
        if customer.get("customer_id") == customer_id:
            logger.info("Customer found: %s", customer_id)
            return customer

    logger.info("Customer not found: %s", customer_id)
    return {"error": "Customer not found", "customer_id": customer_id}


# ---------------------------------------------------------------------------
# Tool 3: lookup_subscription
# ---------------------------------------------------------------------------

def lookup_subscription(customer_id: str) -> dict:
    """Look up the subscription record for an AcmeFlow customer.

    Loads the subscription database and returns the matching subscription.

    Args:
        customer_id: The unique customer identifier (e.g. "CUST-001").

    Returns:
        The subscription dict if found, or an error dict with customer_id.
    """
    subscriptions_path = PROJECT_ROOT / "data" / "subscriptions.json"

    try:
        subscriptions: list[dict] = json.loads(
            subscriptions_path.read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        logger.error("Subscription data file not found at %s", subscriptions_path)
        return {"error": "Subscription data unavailable", "customer_id": customer_id}
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in subscription data: %s", exc)
        return {"error": "Subscription data corrupted", "customer_id": customer_id}

    for subscription in subscriptions:
        if subscription.get("customer_id") == customer_id:
            logger.info("Subscription found for customer: %s", customer_id)
            return subscription

    logger.info("Subscription not found for customer: %s", customer_id)
    return {"error": "Subscription not found", "customer_id": customer_id}


# ---------------------------------------------------------------------------
# Tool 4: check_refund_eligibility
# ---------------------------------------------------------------------------

def check_refund_eligibility(customer_id: str, charge_id: str) -> dict:
    """Check whether a customer is eligible for a refund.

    Evaluates refund eligibility based on the customer's plan type,
    subscription status, and the 30-day refund window.

    Args:
        customer_id: The unique customer identifier (e.g. "CUST-001").
        charge_id: The charge identifier to evaluate for refund.

    Returns:
        A dict indicating eligibility (eligible, reason) and, when eligible,
        refund_type and amount.
    """
    customer = lookup_customer(customer_id)
    if "error" in customer:
        logger.warning(
            "Refund eligibility check failed — customer lookup error: %s",
            customer["error"],
        )
        return {
            "eligible": False,
            "reason": f"Customer lookup failed: {customer['error']}",
            "charge_id": charge_id,
        }

    subscription = lookup_subscription(customer_id)
    if "error" in subscription:
        logger.warning(
            "Refund eligibility check failed — subscription lookup error: %s",
            subscription["error"],
        )
        return {
            "eligible": False,
            "reason": f"Subscription lookup failed: {subscription['error']}",
            "charge_id": charge_id,
        }

    plan = subscription.get("plan", "").lower()
    status = subscription.get("status", "")

    # Enterprise plans — handled by account management
    if plan == "enterprise":
        logger.info("Enterprise refund request for %s — routing to account mgmt", customer_id)
        return {
            "eligible": False,
            "reason": "Enterprise refunds handled by account management team",
            "charge_id": charge_id,
        }

    # Free plans — no charges to refund
    if plan == "free":
        logger.info("Free plan refund request for %s — no charges", customer_id)
        return {
            "eligible": False,
            "reason": "Free plan has no charges to refund",
            "charge_id": charge_id,
        }

    # Must be active, past_due, or recently canceled
    if status not in ("active", "past_due", "canceled"):
        logger.info("Ineligible subscription status %r for %s", status, customer_id)
        return {
            "eligible": False,
            "reason": f"Subscription status '{status}' is not eligible for refund",
            "charge_id": charge_id,
        }

    # Determine the reference date for the 30-day window
    reference_date_str = subscription.get("last_payment_date")
    if not reference_date_str:
        logger.info("No payment date found for %s", customer_id)
        return {
            "eligible": False,
            "reason": "No payment history found for this subscription",
            "charge_id": charge_id,
        }

    reference_date = datetime.strptime(reference_date_str, "%Y-%m-%d")
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # For canceled subscriptions, also check that cancellation was recent
    if status == "canceled":
        canceled_at_str = subscription.get("canceled_at")
        if canceled_at_str:
            canceled_at = datetime.strptime(canceled_at_str, "%Y-%m-%d")
            if (now - canceled_at).days > 30:
                logger.info("Canceled subscription for %s outside 30-day window", customer_id)
                return {
                    "eligible": False,
                    "reason": "Outside 30-day refund window",
                    "charge_id": charge_id,
                }

    # Check 30-day window from last payment
    days_since_payment = (now - reference_date).days
    if days_since_payment > 30:
        logger.info(
            "Payment date for %s is %d days ago — outside window",
            customer_id, days_since_payment,
        )
        return {
            "eligible": False,
            "reason": "Outside 30-day refund window",
            "charge_id": charge_id,
        }

    # Eligible — determine refund type
    billing_cycle = subscription.get("billing_cycle", "monthly")
    monthly_amount = subscription.get("monthly_amount", 0)

    if billing_cycle == "annual":
        refund_type = "pro_rata"
        # Pro-rata: unused months remaining
        months_used = max(1, days_since_payment // 30)
        remaining_months = max(0, 12 - months_used)
        amount = round(monthly_amount * remaining_months, 2)
    else:
        refund_type = "full"
        amount = monthly_amount

    logger.info(
        "Refund eligible for %s: type=%s, amount=%s",
        customer_id, refund_type, amount,
    )
    return {
        "eligible": True,
        "reason": "Within 30-day refund window",
        "refund_type": refund_type,
        "amount": amount,
        "charge_id": charge_id,
    }


# ---------------------------------------------------------------------------
# Tool 5: create_escalation
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


# ---------------------------------------------------------------------------
# Tool 6: draft_customer_response
# ---------------------------------------------------------------------------

def draft_customer_response(draft: str, tone: str) -> dict:
    """Draft a customer-facing response with a specified tone.

    Pass-through tool for structured output. The agent provides the draft
    text and desired tone, and the tool returns them in a structured format
    ready for delivery.

    Args:
        draft: The draft response text to send to the customer.
        tone: The desired tone (e.g. "empathetic", "professional", "apologetic").

    Returns:
        A dict with draft, tone, and status.
    """
    logger.info("Customer response drafted: tone=%s, length=%d", tone, len(draft))
    return {
        "draft": draft,
        "tone": tone,
        "status": "ready",
    }
