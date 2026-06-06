"""Prompt patch proposal and regression test generation."""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import google.genai as genai
import pandas as pd
from google.genai import types
from pydantic import BaseModel

if TYPE_CHECKING:
    import aiosqlite

from src.config import get_settings
from src.diagnosis.phoenix_mcp import (
    DatasetResult,
    PromptInfo,
    TagResult,
    UpsertResult,
)
from src.models import (
    ImprovementTrigger,
    PatchType,
    PromptSource,
    PromptVersion,
    RegressionExample,
)
from src.utils.retry import retry

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol for MCP client (mirrors PhoenixMCPClient in phoenix_mcp.py)
# ---------------------------------------------------------------------------


@runtime_checkable
class MCPWriteProtocol(Protocol):
    """Duck-typed interface for the read+write side of PhoenixMCPClient."""

    async def read_production_prompt(self) -> PromptInfo | None: ...

    async def upsert_prompt(
        self,
        name: str,
        template_messages: list[dict],
        model_name: str,
    ) -> UpsertResult | None: ...

    async def tag_prompt_version(
        self, prompt_version_id: str, tag_name: str
    ) -> TagResult | None: ...

    async def add_dataset_examples(
        self,
        dataset_name: str,
        examples_df: pd.DataFrame,
        input_keys: list[str],
        output_keys: list[str],
    ) -> DatasetResult | None: ...


# ---------------------------------------------------------------------------
# Pydantic schemas for structured Gemini output
# ---------------------------------------------------------------------------


class PatchProposal(BaseModel):
    """Structured response schema for a prompt patch proposal."""

    patch_type: str
    proposed_change: str
    diff_summary: str
    insertion_point: str


class RegressionTicket(BaseModel):
    """Structured response schema for a single regression test ticket."""

    ticket_body: str
    category: str
    expected_behavior: str
    failure_mode_targeted: str


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

PATCH_PROMPT = """You are proposing a NARROW prompt change to fix a support agent failure pattern.

## Diagnosis
{diagnosis_json}

## Current Production Prompt
{current_prompt}

## Rules
- Make the SMALLEST possible change to fix the issue
- Do NOT rewrite the entire prompt
- Add a specific constraint, tool policy, or clarification
- The change should be a few sentences at most
- Focus on the specific failure pattern, not general improvements

Respond with JSON containing:
- patch_type: one of "tool_policy_rule", "escalation_rule", "prompt_constraint", or "retrieval_routing"
- proposed_change: the new text to add to the prompt
- diff_summary: one-line summary of what changed
- insertion_point: which section of the prompt to add this to
"""

REGRESSION_PROMPT = """Generate {count} synthetic support tickets that specifically test this failure mode.

## Failure Pattern
{failure_pattern}

## Root Cause
{root_cause}

## Suggested Fix
{suggested_fix}

Each ticket should:
1. Target the specific failure mode that was fixed
2. Include a realistic customer message
3. Have a clear expected behavior after the fix

Respond with a JSON array where each element has:
- ticket_body: the customer's message
- category: one of "refund", "billing", "legal", "privacy", "admin_access", "outage_credit", or "ambiguous"
- expected_behavior: what the agent should do correctly
- failure_mode_targeted: which failure mode this tests
"""

# Truncation limit for prompt text to avoid token limits
PROMPT_TRUNCATION_LIMIT = 3000

# Number of regression test tickets to generate
REGRESSION_EXAMPLE_COUNT = 5


# ---------------------------------------------------------------------------
# Gemini call helpers (retried)
# ---------------------------------------------------------------------------


@retry(max_attempts=3, backoff_base=1.0, retryable_exceptions=(Exception,))
async def _call_gemini_patch(prompt_text: str) -> PatchProposal:
    """Call Gemini for a patch proposal with retry.

    Args:
        prompt_text: Fully formatted patch prompt.

    Returns:
        Parsed PatchProposal from Gemini response.
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=PatchProposal,
        ),
    )
    return PatchProposal.model_validate_json(response.text)


@retry(max_attempts=3, backoff_base=1.0, retryable_exceptions=(Exception,))
async def _call_gemini_regression(prompt_text: str) -> list[RegressionTicket]:
    """Call Gemini for regression test tickets with retry.

    Args:
        prompt_text: Fully formatted regression prompt.

    Returns:
        List of parsed RegressionTicket models.
    """
    settings = get_settings()
    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
        ),
    )
    raw_list = json.loads(response.text)
    return [RegressionTicket.model_validate(item) for item in raw_list]


# ---------------------------------------------------------------------------
# Patch application helper
# ---------------------------------------------------------------------------


def _apply_patch(current_prompt: str, proposal: PatchProposal) -> str:
    """Apply the proposed change to the current prompt.

    If the insertion_point is found in the current prompt, the change is
    inserted immediately after that section header. Otherwise the change
    is appended to the end.

    Args:
        current_prompt: The full current production prompt text.
        proposal: The patch proposal with change and insertion point.

    Returns:
        The modified prompt string.
    """
    change = proposal.proposed_change
    insertion_point = proposal.insertion_point

    if insertion_point and insertion_point in current_prompt:
        idx = current_prompt.index(insertion_point) + len(insertion_point)
        return current_prompt[:idx] + "\n" + change + current_prompt[idx:]

    # Fallback: append to end of prompt
    return current_prompt + "\n\n" + change


def _prompt_text_to_messages(prompt_text: str) -> list[dict]:
    """Convert a plain-text prompt into the template_messages format expected by PhoenixMCPClient.

    Phoenix prompts use a list-of-messages structure (chat-style).
    We wrap the full prompt text as a single system message.

    Args:
        prompt_text: The full prompt string.

    Returns:
        List with a single system-role message dict.
    """
    return [{"role": "system", "content": prompt_text}]


# ---------------------------------------------------------------------------
# Core proposal logic
# ---------------------------------------------------------------------------


async def generate_proposal(
    trigger: ImprovementTrigger,
    diagnosis: dict,
    mcp_client: MCPWriteProtocol,
    current_prompt: str | None = None,
    db: "aiosqlite.Connection | None" = None,
) -> dict:
    """Generate a narrow prompt patch proposal.

    Reads the current production prompt, asks Gemini to propose a minimal
    fix, then creates a candidate prompt version in Phoenix via MCP.

    Args:
        trigger: The improvement trigger.
        diagnosis: Structured diagnosis from root_cause.diagnose().
        mcp_client: PhoenixMCPClient for reading/writing prompts.
        current_prompt: Pre-resolved production prompt text. When provided,
            skips the Phoenix prompt lookup — preferred path post-spec-0
            where the local DB is the source of truth.
        db: Optional DB handle. When provided, the generated candidate text
            is also persisted as a ``prompt_versions`` row (source=
            ``diagnosis_proposal``) so the release-gate approval flow can
            promote it locally without round-tripping through Phoenix.

    Returns:
        Patch proposal dict with keys: patch_type, proposed_change,
        diff_summary, insertion_point, original_text, proposed_text, and
        optionally candidate_prompt_version, local_prompt_version_id.
    """
    if current_prompt is None:
        prompt_info = await mcp_client.read_production_prompt()
        current_prompt = prompt_info.template if prompt_info else ""
    if not current_prompt:
        current_prompt = ""

    prompt = PATCH_PROMPT.format(
        diagnosis_json=json.dumps(diagnosis, indent=2),
        current_prompt=current_prompt[:PROMPT_TRUNCATION_LIMIT],
    )

    try:
        proposal = await _call_gemini_patch(prompt)
        result = proposal.model_dump()

        # Create candidate prompt version via MCP
        new_prompt_text = _apply_patch(current_prompt, proposal)
        # Surface before/after text so the frontend PromptDiff renderer can
        # show an actual side-by-side comparison.
        result["original_text"] = current_prompt
        result["proposed_text"] = new_prompt_text

        # Persist the candidate as a local prompt_version so the release-gate
        # flow has a real FK to flip ``prompts.active_version_id`` to.
        if db is not None:
            from src.db import (
                get_prompt as db_get_prompt,
            )
            from src.db import (
                insert_prompt_version,
            )

            now = datetime.now(timezone.utc).isoformat()
            parent_prompt = await db_get_prompt(db, "support-agent")
            local_version = PromptVersion(
                prompt_version_id=str(uuid.uuid4()),
                prompt_identifier="support-agent",
                version_tag=(
                    f"diagnosis-{trigger.improvement_trigger_id[:8]}-"
                    f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
                ),
                prompt_text=new_prompt_text,
                parent_version_id=(
                    parent_prompt.active_version_id if parent_prompt else None
                ),
                source=PromptSource.DIAGNOSIS_PROPOSAL,
                improvement_trigger_id=trigger.improvement_trigger_id,
                created_at=now,
                metadata_json={
                    "patch_type": proposal.patch_type,
                    "diff_summary": proposal.diff_summary,
                },
            )
            await insert_prompt_version(db, local_version)
            result["local_prompt_version_id"] = local_version.prompt_version_id

        template_messages = _prompt_text_to_messages(new_prompt_text)
        version_result = await mcp_client.upsert_prompt(
            "support-agent", template_messages, get_settings().gemini_model
        )

        if version_result and version_result.version_id:
            await mcp_client.tag_prompt_version(
                version_result.version_id, "candidate"
            )
            result["candidate_prompt_version"] = version_result.version_id

        logger.info(
            "Proposal generated for %s: %s",
            trigger.failure_key,
            proposal.diff_summary,
        )
        return result

    except Exception as exc:
        logger.error(
            "Proposal generation failed for %s: %s",
            trigger.failure_key,
            exc,
            exc_info=True,
        )
        return {
            "patch_type": PatchType.PROMPT_CONSTRAINT.value,
            "proposed_change": f"Generation failed: {exc}",
            "diff_summary": "Failed to generate proposal",
            "insertion_point": "",
        }


async def generate_regression_examples(
    trigger: ImprovementTrigger,
    diagnosis: dict,
    mcp_client: MCPWriteProtocol,
) -> list[RegressionExample]:
    """Generate regression test cases targeting the specific failure mode.

    Calls Gemini to produce synthetic support tickets, converts them to
    RegressionExample models, then uploads to a Phoenix dataset via MCP.

    Args:
        trigger: The improvement trigger.
        diagnosis: Structured diagnosis from root_cause.diagnose().
        mcp_client: PhoenixMCPClient for uploading to Phoenix dataset.

    Returns:
        List of RegressionExample models (empty on failure).
    """
    prompt = REGRESSION_PROMPT.format(
        count=REGRESSION_EXAMPLE_COUNT,
        failure_pattern=diagnosis.get("failure_pattern", ""),
        root_cause=diagnosis.get("root_cause", ""),
        suggested_fix=diagnosis.get("suggested_fix", ""),
    )

    try:
        tickets = await _call_gemini_regression(prompt)

        now = datetime.now(timezone.utc).isoformat()
        examples: list[RegressionExample] = []

        for ticket in tickets:
            example = RegressionExample(
                regression_example_id=str(uuid.uuid4()),
                improvement_trigger_id=trigger.improvement_trigger_id,
                input_ticket_json={
                    "body": ticket.ticket_body,
                    "category": ticket.category,
                },
                expected_behavior=ticket.expected_behavior,
                failure_mode_targeted=ticket.failure_mode_targeted or trigger.failure_key,
                created_at=now,
            )
            examples.append(example)

        # Build a DataFrame for the Phoenix dataset SDK call
        dataset_rows = [
            {
                "ticket_body": ex.input_ticket_json.get("body", ""),
                "expected_behavior": ex.expected_behavior,
                "failure_mode": ex.failure_mode_targeted,
            }
            for ex in examples
        ]
        examples_df = pd.DataFrame(dataset_rows)

        dataset_result = await mcp_client.add_dataset_examples(
            dataset_name=f"regression-{trigger.failure_key}",
            examples_df=examples_df,
            input_keys=["ticket_body"],
            output_keys=["expected_behavior"],
        )

        if dataset_result and dataset_result.dataset_id:
            for ex in examples:
                ex.phoenix_dataset_id = dataset_result.dataset_id
                ex.uploaded_at = now

        logger.info(
            "Generated %d regression examples for %s",
            len(examples),
            trigger.failure_key,
        )
        return examples

    except Exception as exc:
        logger.error(
            "Regression generation failed for %s: %s",
            trigger.failure_key,
            exc,
            exc_info=True,
        )
        return []
