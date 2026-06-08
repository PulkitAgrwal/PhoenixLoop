"""Test the diagnosis agent's system prompt declares the expanded MCP toolset."""

from src.agent.diagnosis_agent import DIAGNOSIS_INSTRUCTION
from src.agent.mcp_tools import DIAGNOSIS_ALLOWED_TOOLS


def test_prompt_lists_all_five_phoenix_mcp_tools() -> None:
    """All five Phoenix MCP tools the diagnosis agent may call must appear by name."""
    required = [
        "get-spans",
        "get-span-annotations",
        "list-traces",
        "list-sessions",
        "list-experiments-for-dataset",
    ]
    for tool in required:
        assert tool in DIAGNOSIS_INSTRUCTION, (
            f"Diagnosis prompt is missing {tool!r}; "
            "the Arize-track audit (P1-1) requires it"
        )


def test_prompt_cap_is_four_not_two() -> None:
    """Cap was raised from 2 to 4 per audit P1-1."""
    assert "AT MOST 4 MCP tool calls" in DIAGNOSIS_INSTRUCTION
    assert "AT MOST 2 MCP tool calls" not in DIAGNOSIS_INSTRUCTION


def test_prompt_forbids_list_projects() -> None:
    """The prompt must explicitly forbid list-projects (P1-1 follow-up regression fix).

    Without this, Gemini calls list-projects opportunistically, which requires a
    projectIdentifier this pipeline doesn't supply and fails outright, dropping
    diagnosis confidence to 0.0. Reproduced locally on 2026-06-07.
    """
    assert "list-projects" in DIAGNOSIS_INSTRUCTION
    assert "Forbidden calls" in DIAGNOSIS_INSTRUCTION
    assert "projectIdentifier" in DIAGNOSIS_INSTRUCTION


def test_diagnosis_allowed_tools_matches_prompt() -> None:
    """The runtime tool_filter list and the prompt's allow-list must stay in sync."""
    assert DIAGNOSIS_ALLOWED_TOOLS == [
        "get-spans",
        "get-span-annotations",
        "list-traces",
        "list-sessions",
        "list-experiments-for-dataset",
    ]
    for tool in DIAGNOSIS_ALLOWED_TOOLS:
        assert tool in DIAGNOSIS_INSTRUCTION
