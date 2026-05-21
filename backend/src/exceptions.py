"""Domain exception hierarchy for PhoenixLoop."""


class PhoenixLoopError(Exception):
    """Base exception for all PhoenixLoop errors."""


class AgentRunError(PhoenixLoopError):
    """Agent execution failed."""


class EvaluationError(PhoenixLoopError):
    """Evaluation failed."""


class MCPConnectionError(PhoenixLoopError):
    """MCP server communication failed."""


class ExperimentError(PhoenixLoopError):
    """Experiment execution failed."""


class ReleaseGateError(PhoenixLoopError):
    """Release gate evaluation failed."""


class ConfigurationError(PhoenixLoopError):
    """Missing or invalid configuration."""


class DatabaseError(PhoenixLoopError):
    """Database operation failed."""


class IdempotencyConflictError(PhoenixLoopError):
    """Duplicate idempotency key detected."""
