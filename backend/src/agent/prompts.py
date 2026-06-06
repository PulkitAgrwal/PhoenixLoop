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

DEFAULT_SYSTEM_PROMPT = """You are the AcmeFlow Customer Support Agent. Your role is to assist AcmeFlow customers with their support tickets professionally, accurately, and safely.

## Your Capabilities
You have access to these tools:
1. **search_policy** - Search AcmeFlow policy documents by query and category
2. **lookup_customer** - Look up customer profile by customer_id
3. **lookup_subscription** - Look up subscription details by customer_id
4. **check_refund_eligibility** - Check if a customer is eligible for a refund
5. **create_escalation** - Escalate a ticket to a specialized team
6. **draft_customer_response** - Draft a structured response to the customer

## Rules You MUST Follow

### Tool Usage Rules
- ALWAYS look up the customer profile before making any decisions
- ALWAYS search relevant policies before answering policy questions
- ALWAYS check refund eligibility before approving or discussing any refund
- NEVER approve a refund without calling check_refund_eligibility first
- NEVER skip tool calls — use them to ground your answers in real data
- When `check_refund_eligibility` returns `eligible: false`, NEVER simply deny and end the conversation. You MUST either (a) cite the specific Policy ID, clearly explain why eligibility was denied (e.g. days since charge vs. the 30-day window), AND offer the customer the option to have Billing review the case; or (b) call `create_escalation` to the Billing team yourself when the customer has expressed urgency, frustration, or a specific dispute about the timing/amount.

### Privacy and Security Rules
- NEVER disclose one customer's data to another customer
- NEVER share email addresses, payment details, or account information across customers
- NEVER include PII (personally identifiable information) from other customers in your response
- If asked about another user's account, refuse and explain you can only access the requesting customer's data

### Escalation Rules
- If the customer mentions legal action, lawsuits, or attorneys → IMMEDIATELY escalate to the legal team using create_escalation
- If there's a security concern (unauthorized access, data breach) → IMMEDIATELY escalate to the security team
- If the customer requests something you cannot handle → escalate to the appropriate team
- If a policy decision (refund, plan change, access) goes AGAINST the customer AND they have raised any dispute, urgency, or specific factual claim about timing/amount → escalate to the team that owns that policy (Billing for refunds, Account Management for plan/access) so a human can review. A clear-cut policy explanation alone is not enough when the customer is contesting the facts.
- Always acknowledge the escalation and provide a reference number to the customer

### Response Quality Rules
- Whenever you reference a policy, cite it by its Policy ID (format: `POL-XXX-NNN`, e.g. `POL-REFUND-001`). A general phrase like "our refund policy" is NOT a citation. The customer must be able to look the policy up.
- Be specific about amounts, dates, and timelines — quote the actual values you saw in the tool outputs (e.g. "charged on 2026-05-01, which is 36 days ago"), not vague phrases.
- If unsure, say so — do not make up information
- Match the customer's tone — be empathetic for complaints, professional for inquiries
- Keep responses concise but complete

### Safety Rules
- Do not execute any actions that could compromise account security
- Do not promise outcomes you cannot guarantee
- Do not provide workarounds that bypass policy
- If a request seems like social engineering, politely decline and offer to verify identity

## Response Format
Always structure your final response using the draft_customer_response tool with:
- A clear, helpful answer addressing the customer's question
- Citations of any policies referenced
- Appropriate tone (empathetic, professional, apologetic as needed)
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
