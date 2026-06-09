"""Pydantic models and enums for PhoenixLoop domain entities."""

from enum import Enum
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TicketCategory(str, Enum):
    REFUND = "refund"
    BILLING = "billing"
    ADMIN_ACCESS = "admin_access"
    DATA_EXPORT = "data_export"
    PRIVACY = "privacy"
    LEGAL = "legal"
    OUTAGE_CREDIT = "outage_credit"
    AMBIGUOUS = "ambiguous"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FailureType(str, Enum):
    MISSING_REQUIRED_TOOL = "missing_required_tool"
    UNSUPPORTED_CLAIM = "unsupported_claim"
    PRIVACY_LEAK = "privacy_leak"
    WRONG_ESCALATION = "wrong_escalation"
    MALFORMED_OUTPUT = "malformed_output"
    RETRIEVAL_MISS = "retrieval_miss"
    INCORRECT_RESOLUTION = "incorrect_resolution"
    LATENCY_REGRESSION = "latency_regression"
    TOKEN_BUDGET_EXCEEDED = "token_budget_exceeded"
    TOOL_ERROR = "tool_error"


class PatchType(str, Enum):
    TOOL_POLICY_RULE = "tool_policy_rule"
    ESCALATION_RULE = "escalation_rule"
    PROMPT_CONSTRAINT = "prompt_constraint"
    RETRIEVAL_ROUTING = "retrieval_routing"


class TriggerReason(str, Enum):
    THRESHOLD_REPEATED_FAILURE = "threshold_repeated_failure"
    CRITICAL_FAILURE = "critical_failure"
    MANUAL_DEMO_TRIGGER = "manual_demo_trigger"


class ReleaseDecision(str, Enum):
    PROMOTED = "promoted"
    REJECTED = "rejected"
    PENDING_HUMAN_REVIEW = "pending_human_review"
    BLOCKED_CRITICAL_FAILURE = "blocked_critical_failure"


class ExperimentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvalType(str, Enum):
    CODE = "code"
    LLM_JUDGE = "llm_judge"
    PHOENIX_TOOL_EVAL = "phoenix_tool_eval"


class AnnotationLevel(str, Enum):
    SESSION = "session"
    SPAN = "span"


class PromptSource(str, Enum):
    SEED = "seed"
    DIAGNOSIS_PROPOSAL = "diagnosis_proposal"
    MANUAL = "manual"


class ChangeClass(str, Enum):
    """Taxonomy of change types proposed by the diagnosis pipeline.

    Tagged onto ``prompt_versions.change_class`` so the UI can roll up
    healing cycles by the kind of remediation applied.
    """

    PROMPT_ADDITION = "prompt_addition"
    TOOL_POLICY = "tool_policy"
    ROUTING = "routing"
    DATA_SOURCE = "data_source"
    EVAL_DEFINITION = "eval_definition"
    MANUAL_EDIT = "manual_edit"
    SEED = "seed"


class JudgeLabel(str, Enum):
    """Structured verdict emitted by every LLM judge.

    Used for both ground-truth canary labels and per-run judge predictions
    so Cohen's kappa can be computed on a fixed three-way label space.
    """

    PASS = "pass"
    FAIL = "fail"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ActivityEventKind(str, Enum):
    AGENT_RUN = "agent_run"
    FAILURE = "failure"
    IMPROVEMENT_TRIGGER = "improvement_trigger"
    EXPERIMENT = "experiment"
    RELEASE_DECISION = "release_decision"


# ---------------------------------------------------------------------------
# Pydantic Models — Prompts
# ---------------------------------------------------------------------------

class Prompt(BaseModel):
    """A logical prompt identity (one row per named prompt)."""

    prompt_identifier: str = Field(min_length=1, max_length=128)
    description: str | None = None
    active_version_id: str | None = None
    created_at: str
    updated_at: str


class PromptVersion(BaseModel):
    """An immutable snapshot of a prompt's text at a point in time."""

    prompt_version_id: str
    prompt_identifier: str = Field(min_length=1, max_length=128)
    version_tag: str = Field(min_length=1, max_length=200)
    prompt_text: str = Field(min_length=1, max_length=200_000)
    parent_version_id: str | None = None
    source: PromptSource
    improvement_trigger_id: str | None = None
    created_at: str
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    change_class: ChangeClass | None = None


# ---------------------------------------------------------------------------
# Pydantic Models — Ticket
# ---------------------------------------------------------------------------

class SupportTicket(BaseModel):
    ticket_id: str
    customer_id: str
    category: TicketCategory
    subject: str
    body: str
    metadata_json: dict | None = None
    created_at: str
    updated_at: str


# ---------------------------------------------------------------------------
# Pydantic Models — Run
# ---------------------------------------------------------------------------

class ToolCallRecord(BaseModel):
    tool_name: str
    input: dict
    output: dict
    span_id: str | None = None
    latency_ms: int | None = None
    status: str = "success"


class ConversationSession(BaseModel):
    conversation_session_id: str
    ticket_id: str
    phoenix_session_id: str | None = None
    started_at: str
    ended_at: str | None = None
    turn_count: int = 0
    outcome: str | None = None


class AgentRun(BaseModel):
    agent_run_id: str
    conversation_session_id: str
    ticket_id: str
    agent_name: str = "helios_support_agent"
    agent_version: str = "1.0.0"
    prompt_version: str
    trace_id: str | None = None
    root_span_id: str | None = None
    phoenix_session_id: str | None = None
    input_hash: str | None = None
    response_json: dict
    tool_calls_json: list[ToolCallRecord] = []
    status: str
    latency_ms: int | None = None
    token_count_input: int | None = None
    token_count_output: int | None = None
    prompt_version_id: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Pydantic Models — Eval
# ---------------------------------------------------------------------------

class EvalResult(BaseModel):
    eval_result_id: str
    agent_run_id: str
    evaluator_name: str
    eval_type: EvalType
    score: float | None = None
    outcome: str
    explanation: str | None = None
    failure_key: str | None = None
    failure_summary: str | None = None
    annotation_level: AnnotationLevel
    span_id: str | None = None
    metadata_json: dict | None = None
    created_at: str
    rubric_version: str | None = None
    evidence_json: list[str] = Field(default_factory=list)


class FailureAggregate(BaseModel):
    failure_key: str
    failure_summary: str
    evaluator_name: str
    occurrence_count: int = 0
    first_seen_at: str
    last_seen_at: str
    example_run_ids_json: list[str] = []
    is_active: bool = True
    computed_at: str


# ---------------------------------------------------------------------------
# Pydantic Models — Canary Labels & Judge Outputs
# ---------------------------------------------------------------------------

class JudgeOutput(BaseModel):
    """Structured output contract for the four LLM judges.

    Every judge returns this shape so the eval-payload schema is uniform
    across groundedness, policy_compliance, tone, and resolution_quality.
    The ``evidence`` field carries supporting quotes used by the UI.
    """

    label: JudgeLabel
    explanation: str = Field(min_length=1, max_length=8000)
    evidence: list[str] = Field(default_factory=list)


class CanaryLabel(BaseModel):
    """Hand-derived ground-truth label for an LLM judge.

    One row per (fixture_id, judge_name); rationale documents why the
    fixture maps to this label so reviewers can audit the gold set.
    """

    canary_label_id: str
    fixture_id: str = Field(min_length=1, max_length=200)
    ticket_category: TicketCategory
    judge_name: str = Field(min_length=1, max_length=128)
    expected_label: JudgeLabel
    rationale: str = Field(min_length=1, max_length=4000)
    created_at: str


class CanaryRun(BaseModel):
    """One judge prediction on one canary fixture.

    Persisted per run so Cohen's kappa is reproducible and historical
    drift can be plotted as the judge prompt evolves.
    """

    canary_run_id: str
    canary_label_id: str
    judge_name: str = Field(min_length=1, max_length=128)
    predicted_label: JudgeLabel
    evidence_json: list[str] = Field(default_factory=list)
    explanation: str | None = None
    judge_model: str = Field(min_length=1, max_length=128)
    created_at: str


# ---------------------------------------------------------------------------
# Pydantic Models — Improvement
# ---------------------------------------------------------------------------

class ImprovementTrigger(BaseModel):
    improvement_trigger_id: str
    failure_key: str
    trigger_reason: TriggerReason
    occurrence_count: int
    example_run_ids_json: list[str] = []
    diagnosis_json: dict | None = None
    patch_proposal_json: dict | None = None
    regression_examples_json: list[dict] = []
    status: str = "pending"
    created_at: str
    updated_at: str


class RegressionExample(BaseModel):
    regression_example_id: str
    improvement_trigger_id: str
    input_ticket_json: dict
    expected_behavior: str
    failure_mode_targeted: str
    phoenix_dataset_id: str | None = None
    uploaded_at: str | None = None
    created_at: str
    source_agent_run_id: str | None = None
    auto_promoted: bool = False


# ---------------------------------------------------------------------------
# Pydantic Models — Experiment
# ---------------------------------------------------------------------------

class ExperimentRecord(BaseModel):
    experiment_id: str
    improvement_trigger_id: str
    baseline_prompt_version: str
    candidate_prompt_version: str
    dataset_id: str
    phoenix_experiment_id_baseline: str | None = None
    phoenix_experiment_id_candidate: str | None = None
    status: ExperimentStatus = ExperimentStatus.PENDING
    baseline_release_score: float | None = None
    candidate_release_score: float | None = None
    baseline_critical_failure_rate: float | None = None
    candidate_critical_failure_rate: float | None = None
    baseline_latency_p50_ms: int | None = None
    candidate_latency_p50_ms: int | None = None
    baseline_hallucination_rate: float | None = None
    candidate_hallucination_rate: float | None = None
    regression_cases_pass_rate: float | None = None
    safety_canary_pass_rate: float | None = None
    eval_summary_json: dict | None = None
    started_at: str | None = None
    completed_at: str | None = None
    baseline_prompt_version_id: str | None = None
    candidate_prompt_version_id: str | None = None
    created_at: str
    baseline_tool_call_count: float | None = None
    candidate_tool_call_count: float | None = None
    baseline_tool_adherence_rate: float | None = None
    candidate_tool_adherence_rate: float | None = None


class CreatePromptVersionRequest(BaseModel):
    """Body for ``POST /api/prompts/{identifier}/versions``."""

    prompt_text: str = Field(min_length=1, max_length=200_000)
    version_tag: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class ReleaseGateDecision(BaseModel):
    release_gate_decision_id: str
    experiment_id: str
    decision: ReleaseDecision
    release_score: float
    promotion_rules_passed: int
    rules_detail_json: dict | None = None
    requires_human_approval: bool = True
    decided_at: str


class HumanApproval(BaseModel):
    human_approval_id: str
    release_gate_decision_id: str
    reviewer_id: str
    status: str = "pending"
    comment: str | None = None
    reviewed_at: str | None = None
    created_at: str


# ---------------------------------------------------------------------------
# Pydantic Models — Audit
# ---------------------------------------------------------------------------

class AuditEvent(BaseModel):
    audit_event_id: str
    entity_type: str
    entity_id: str
    action: str
    actor: str
    detail_json: dict | None = None
    created_at: str


# ---------------------------------------------------------------------------
# API Response Envelope
# ---------------------------------------------------------------------------

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    request_id: str | None = None


class PaginatedData(BaseModel, Generic[T]):
    items: list[T]
    total_count: int
    page: int
    page_size: int
    has_next: bool


# ---------------------------------------------------------------------------
# Pydantic Models — Activity / Health / Config
# ---------------------------------------------------------------------------


class ActivityEvent(BaseModel):
    event_id: str
    kind: ActivityEventKind
    title: str
    subtitle: str | None = None
    timestamp: str
    target_route: str | None = None


class HealthCheck(BaseModel):
    ok: bool
    detail: str
    response_ms: int | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    checks: dict[str, HealthCheck]


class StatsResponse(BaseModel):
    """Headline counts surfaced on the landing-page stats strip.

    All four counts are pure SQL — no Gemini calls — so the landing page
    can render server-side on every request without burning the token
    budget. Source-of-truth is the local SQLite DB.
    """

    agent_runs_traced: int
    evaluators_wired: int
    mcp_tool_calls_per_run_avg: float
    prompts_auto_promoted: int


class ConfigResponse(BaseModel):
    app_env: str
    database_url: str
    gemini_model: str
    google_api_key: str
    phoenix_base_url: str
    phoenix_api_key: str
    phoenix_project_name: str
    repeated_failure_count: int
    repeated_failure_rate: float
    critical_failure_immediate: bool
    cooldown_minutes: int
    release_score_threshold: float
    latency_budget_ms: int
    agent_name: str
    agent_version: str
    active_prompt_version: str | None
