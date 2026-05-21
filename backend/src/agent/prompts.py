"""Prompt management for the support agent via Phoenix."""

import logging
from typing import Protocol

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

### Privacy and Security Rules
- NEVER disclose one customer's data to another customer
- NEVER share email addresses, payment details, or account information across customers
- NEVER include PII (personally identifiable information) from other customers in your response
- If asked about another user's account, refuse and explain you can only access the requesting customer's data

### Escalation Rules
- If the customer mentions legal action, lawsuits, or attorneys → IMMEDIATELY escalate to the legal team using create_escalation
- If there's a security concern (unauthorized access, data breach) → IMMEDIATELY escalate to the security team
- If the customer requests something you cannot handle → escalate to the appropriate team
- Always acknowledge the escalation and provide a reference number to the customer

### Response Quality Rules
- Cite specific policy documents when referencing policies
- Be specific about amounts, dates, and timelines
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


def get_production_prompt(phoenix_client: PhoenixClientProtocol | None = None) -> str:
    """Load the production prompt from Phoenix, falling back to default.

    Args:
        phoenix_client: Phoenix client instance. If None or if Phoenix
            is unavailable, returns the hardcoded default prompt.

    Returns:
        The system prompt string.
    """
    if phoenix_client is None:
        logger.info("No Phoenix client provided, using default system prompt")
        return DEFAULT_SYSTEM_PROMPT

    try:
        prompt = phoenix_client.prompts.get(
            prompt_identifier="support-agent",
            tag="production",
        )
        if prompt and hasattr(prompt, "template"):
            logger.info("Loaded production prompt from Phoenix")
            return prompt.template
        logger.warning("Phoenix prompt found but no template, using default")
        return DEFAULT_SYSTEM_PROMPT
    except Exception as exc:
        logger.warning("Failed to load prompt from Phoenix: %s, using default", exc)
        return DEFAULT_SYSTEM_PROMPT


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
            model_name="gemini-2.0-flash",
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
