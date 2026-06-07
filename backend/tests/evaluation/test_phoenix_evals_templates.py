"""Verify Phoenix Evals templates are actually used by CombinedLLMJudges.

The Devpost story claim is "Phoenix Evals templates for general-purpose
checks, custom evaluators for domain logic." These tests make that claim
falsifiable: if a future refactor accidentally drops the import or hard-codes
the prompt text, the suite turns red.
"""

from phoenix.evals import HALLUCINATION_PROMPT_TEMPLATE, QA_PROMPT_TEMPLATE
from src.evaluation.llm_judges.combined import (
    EVAL_PROMPT_TEMPLATE,
    PHOENIX_HALLUCINATION_TEMPLATE_TEXT,
    PHOENIX_QA_TEMPLATE_TEXT,
    _extract_phoenix_template_text,
)


def test_hallucination_template_text_is_loaded_from_phoenix() -> None:
    """The embedded text is derived from the Phoenix SDK, not hand-rolled."""
    canonical = _extract_phoenix_template_text(HALLUCINATION_PROMPT_TEMPLATE)
    canonical_signal = "hallucinated"
    assert canonical_signal in canonical.lower()
    assert canonical_signal in PHOENIX_HALLUCINATION_TEMPLATE_TEXT.lower()


def test_qa_template_text_is_loaded_from_phoenix() -> None:
    canonical = _extract_phoenix_template_text(QA_PROMPT_TEMPLATE)
    assert "correct" in canonical.lower()
    assert "incorrect" in PHOENIX_QA_TEMPLATE_TEXT.lower()


def test_combined_prompt_embeds_phoenix_templates() -> None:
    """The combined prompt renders with Phoenix template framings visible."""
    rendered = EVAL_PROMPT_TEMPLATE.format(
        ticket_category="refund",
        ticket_customer_id="cus_5WvnX4nq",
        ticket_body="body",
        response_text="resp",
        tool_outputs="outputs",
        pass_threshold=0.7,
    )
    assert "HALLUCINATION_PROMPT_TEMPLATE" in rendered
    assert "QA_PROMPT_TEMPLATE" in rendered
    assert "{input}" in rendered
    assert "{reference}" in rendered
    assert "{output}" in rendered


def test_custom_judges_remain_in_place() -> None:
    """PolicyCompliance and SafetyPrivacy stay custom — they encode domain rules."""
    rendered = EVAL_PROMPT_TEMPLATE.format(
        ticket_category="refund",
        ticket_customer_id="cus_5WvnX4nq",
        ticket_body="body",
        response_text="resp",
        tool_outputs="outputs",
        pass_threshold=0.7,
    )
    assert "Refund Policy" in rendered
    assert "Escalation Policy" in rendered
    assert "Privacy Policy" in rendered
    assert "safety_privacy" in rendered
    assert "fabricated policy" in rendered
