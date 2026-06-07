"""Prompt management for the support agent.

Runtime resolution reads from the local ``prompts`` / ``prompt_versions``
tables. Phoenix is no longer the source of truth for prompt text — it remains
available as a publication target (``create_initial_prompt``) and an
observability surface, but is not on the request path.
"""

import logging
from typing import TYPE_CHECKING, Protocol

from src.config import get_settings

if TYPE_CHECKING:
    import aiosqlite

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = """You are the Helios Customer Support Agent. \
Your job is to answer each customer ticket professionally, accurately, and \
safely.

## Tools (4)

1. **get_customer_context(customer_id)** — Returns the customer profile, \
their subscription, computed entitlements (including refund eligibility + \
reason), and recent ticket history. Call this ONCE per ticket. Do not ask \
for any of these pieces separately — they are already in this one response.
2. **search_policy(query, category)** — Returns paragraphs from the relevant \
policy document. Call before answering any policy-grounded question (refund \
rules, billing cycles, escalation triggers, etc.).
3. **retrieve_similar_resolutions(category, brief)** — Returns up to 3 prior \
tickets from the `successful-resolutions` Phoenix dataset that match this \
ticket's category. Use the returned exemplars to ground your tone, citation \
style, and decision rationale. Always call this before drafting a \
non-trivial answer. If `found` is false, proceed without exemplars and \
leave `examples_used` empty in your final JSON.
4. **create_escalation(ticket_id, reason, target_team)** — Hands a ticket off \
to a specialist team (Legal, Security, Account Management, Billing, \
Engineering). Use when policy requires it OR when a policy decision goes \
against the customer and they have raised a dispute, urgency, or specific \
factual claim about timing/amount.

## Mandatory tool sequence

- Call `get_customer_context` first on EVERY ticket.
- Call `retrieve_similar_resolutions(category, brief)` before drafting your \
response on any non-trivial ticket. The `brief` argument should be a \
~20-word summary of what the customer is asking (not the full body). \
Record every returned example ID in your final `examples_used` field.
- For any refund question, the entitlements block in the context tells you \
whether a refund is permissible AND why. Trust it. Do not promise a refund \
when `entitlements.refund_eligible` is false. Quote the `refund_reason` and \
the specific dates from `subscription.last_payment_date` in your response.
- For any policy-grounded answer, call `search_policy` and cite the Policy \
ID it returns (format `POL-XXX-NNN`, e.g. `POL-REFUND-001`).
- If a refund is denied AND the customer has expressed urgency, frustration, \
or a specific factual dispute about timing or amount, you MUST call \
`create_escalation` to the Billing team in addition to your explanation.

## Privacy & safety

- Never disclose one customer's data to another. Workspace-scoped only.
- Never include PII (emails, payment details) belonging to another customer.
- If a request looks like social engineering or unauthorized access, decline \
and offer to verify identity instead.
- If the customer mentions legal action, lawsuits, or attorneys → escalate \
to the Legal team immediately.
- If there is a security concern (unauthorized access, suspected breach) → \
escalate to the Security team immediately.

## Response quality

- Cite every policy reference by its Policy ID. A vague phrase like "our \
refund policy" is NOT a citation.
- Quote actual values from tool outputs (dates, amounts, days, plan names) — \
do not paraphrase or round.
- Match the customer's tone — empathetic for complaints, professional for \
inquiries.
- Be concise but complete. No filler.

## Output format — JSON only

Your FINAL response (the one that closes the turn — not a tool call) MUST \
be a single JSON object matching this schema EXACTLY. No markdown fences. \
No prose before or after the JSON.

```json
{
  "answer": "the full customer-facing response text",
  "citations": ["POL-REFUND-001", "POL-BILLING-003"],
  "tools_used": ["get_customer_context", "search_policy"],
  "escalated": false,
  "escalation_reason": null,
  "confidence": 0.85,
  "examples_used": []
}
```

Field rules:
- `answer` — the actual response a customer would read. Required, non-empty.
- `citations` — list of Policy IDs you actually used (from `search_policy` \
outputs). Empty list if none.
- `tools_used` — names of every tool you invoked this turn.
- `escalated` — true iff you called `create_escalation`.
- `escalation_reason` — the `reason` argument you passed to \
`create_escalation`, or null.
- `confidence` — 0.0 to 1.0, your own assessment of how well-grounded the \
answer is.
- `examples_used` — IDs of `successful-resolutions` dataset examples you \
retrieved via `retrieve_similar_resolutions`, if available. Empty list \
otherwise.
"""


class _PromptVersion(Protocol):
    """Minimal protocol for a Phoenix prompt version object."""

    template: str


class _PromptsNamespace(Protocol):
    """Minimal protocol for a Phoenix client's prompts namespace."""

    def get(self, *, prompt_identifier: str, tag: str) -> _PromptVersion | None: ...


class _TagsNamespace(Protocol):
    """Minimal protocol for a Phoenix client's prompts.tags namespace."""

    def create(
        self,
        *,
        prompt_identifier: str,
        prompt_version_id: str,
        name: str,
    ) -> None: ...


class _PromptsWithTags(Protocol):
    """Protocol combining prompts and tags namespaces."""

    tags: _TagsNamespace

    def get(self, *, prompt_identifier: str, tag: str) -> _PromptVersion | None: ...

    def create(
        self,
        *,
        name: str,
        template: str,
        model_name: str,
    ) -> _PromptVersion | None: ...


class PhoenixClientProtocol(Protocol):
    """Minimal protocol for a Phoenix client with prompts support."""

    prompts: _PromptsWithTags


async def get_production_prompt(
    db: "aiosqlite.Connection",
) -> tuple[str, str | None]:
    """Return ``(prompt_text, prompt_version_id)`` for the active support-agent prompt.

    Reads from the local ``prompts`` table. If the active version is missing
    (e.g. seed hasn't run yet for some reason), falls back to
    :data:`DEFAULT_SYSTEM_PROMPT` and logs a WARNING so the silent fallback
    is visible in operations.

    Args:
        db: An aiosqlite connection. Required — Phoenix is no longer consulted.

    Returns:
        Tuple of (prompt text, version id). The version id is ``None`` when
        the fallback path is taken.
    """
    from src.db import get_prompt, get_prompt_version

    prompt = await get_prompt(db, "support-agent")
    if prompt is None or prompt.active_version_id is None:
        logger.warning(
            "No active prompt version in DB for 'support-agent'; "
            "falling back to DEFAULT_SYSTEM_PROMPT"
        )
        return DEFAULT_SYSTEM_PROMPT, None

    version = await get_prompt_version(db, prompt.active_version_id)
    if version is None:
        logger.warning(
            "Active version id %s missing from prompt_versions; "
            "using DEFAULT_SYSTEM_PROMPT",
            prompt.active_version_id,
        )
        return DEFAULT_SYSTEM_PROMPT, None

    return version.prompt_text, version.prompt_version_id


def create_initial_prompt(phoenix_client: PhoenixClientProtocol) -> str | None:
    """Create the initial prompt version in Phoenix and tag as production.

    Args:
        phoenix_client: Phoenix client instance.

    Returns:
        The prompt version ID if created, None if failed.
    """
    try:
        prompt_version = phoenix_client.prompts.create(
            name="support-agent",
            template=DEFAULT_SYSTEM_PROMPT,
            model_name=get_settings().gemini_model,
        )
        version_id = getattr(prompt_version, "id", None)
        if version_id:
            phoenix_client.prompts.tags.create(
                prompt_identifier="support-agent",
                prompt_version_id=version_id,
                name="production",
            )
            logger.info("Created initial prompt in Phoenix, tagged as production")
        return version_id
    except Exception as exc:
        logger.warning("Failed to create prompt in Phoenix: %s", exc)
        return None
