"""Agent response contract and tool schemas."""

from pydantic import BaseModel, Field


class AgentResponseContract(BaseModel):
    """Structured response the agent must return for every ticket.

    The agent emits this as a single JSON object in its final text turn —
    not via a tool call (ADK ``output_schema`` disables tools, and Gemini's
    ``response_schema`` is incompatible with function calling on the same
    turn). The post-hoc parser in ``support_agent.run_agent_events``
    validates the final response against this model; on parse failure we
    synthesize from the tool history instead.
    """

    answer: str = Field(min_length=1)
    citations: list[str] = Field(default_factory=list)
    tools_used: list[str] = Field(default_factory=list)
    escalated: bool = False
    escalation_reason: str | None = None
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    examples_used: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of ``successful-resolutions`` Phoenix dataset examples the "
            "agent retrieved via ``retrieve_similar_resolutions`` and used "
            "as in-context exemplars. Empty when no few-shot retrieval ran."
        ),
    )
