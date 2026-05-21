"""Agent response contract and tool schemas."""

from pydantic import BaseModel


class AgentResponseContract(BaseModel):
    """Structured response the agent must return for every ticket."""

    answer: str
    citations: list[str]
    tools_used: list[str]
    escalated: bool
    escalation_reason: str | None = None
    confidence: float
