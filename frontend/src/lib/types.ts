// Enums
export type TicketCategory =
  | "refund"
  | "billing"
  | "admin_access"
  | "data_export"
  | "privacy"
  | "legal"
  | "outage_credit"
  | "ambiguous";

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export type FailureType =
  | "missing_required_tool"
  | "unsupported_claim"
  | "privacy_leak"
  | "wrong_escalation"
  | "malformed_output"
  | "retrieval_miss"
  | "incorrect_resolution"
  | "latency_regression"
  | "token_budget_exceeded"
  | "tool_error";

export type PatchType =
  | "tool_policy_rule"
  | "escalation_rule"
  | "prompt_constraint"
  | "retrieval_routing";

export type TriggerReason =
  | "threshold_repeated_failure"
  | "critical_failure"
  | "manual_demo_trigger";

export type ReleaseDecision =
  | "promoted"
  | "rejected"
  | "pending_human_review"
  | "blocked_critical_failure";

export type ExperimentStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed";

export type EvalType = "code" | "llm_judge" | "phoenix_tool_eval";

export type AnnotationLevel = "session" | "span";

// Entities
export interface SupportTicket {
  ticket_id: string;
  customer_id: string;
  category: TicketCategory;
  subject: string;
  body: string;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ToolCallRecord {
  tool_name: string;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  span_id: string | null;
  latency_ms: number | null;
  status: string;
}

export interface ConversationSession {
  conversation_session_id: string;
  ticket_id: string;
  phoenix_session_id: string | null;
  started_at: string;
  ended_at: string | null;
  turn_count: number;
  outcome: string | null;
}

export interface AgentRun {
  agent_run_id: string;
  conversation_session_id: string;
  ticket_id: string;
  agent_name: string;
  agent_version: string;
  prompt_version: string;
  trace_id: string | null;
  root_span_id: string | null;
  phoenix_session_id: string | null;
  input_hash: string | null;
  response_json: Record<string, unknown>;
  tool_calls_json: ToolCallRecord[];
  status: string;
  latency_ms: number | null;
  token_count_input: number | null;
  token_count_output: number | null;
  created_at: string;
}

export interface EvalResult {
  eval_result_id: string;
  agent_run_id: string;
  evaluator_name: string;
  eval_type: EvalType;
  score: number | null;
  outcome: string;
  explanation: string | null;
  failure_key: string | null;
  failure_summary: string | null;
  annotation_level: AnnotationLevel;
  span_id: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface FailureAggregate {
  failure_key: string;
  failure_summary: string;
  evaluator_name: string;
  occurrence_count: number;
  first_seen_at: string;
  last_seen_at: string;
  example_run_ids_json: string[];
  is_active: boolean;
  computed_at: string;
}

export interface ImprovementTrigger {
  improvement_trigger_id: string;
  failure_key: string;
  trigger_reason: TriggerReason;
  occurrence_count: number;
  example_run_ids_json: string[];
  diagnosis_json: Record<string, unknown> | null;
  patch_proposal_json: Record<string, unknown> | null;
  regression_examples_json: Record<string, unknown>[];
  status: string;
  created_at: string;
  updated_at: string;
}

export interface RegressionExample {
  regression_example_id: string;
  improvement_trigger_id: string;
  input_ticket_json: Record<string, unknown>;
  expected_behavior: string;
  failure_mode_targeted: string;
  phoenix_dataset_id: string | null;
  uploaded_at: string | null;
  created_at: string;
}

export interface ExperimentRecord {
  experiment_id: string;
  improvement_trigger_id: string;
  baseline_prompt_version: string;
  candidate_prompt_version: string;
  dataset_id: string;
  phoenix_experiment_id_baseline: string | null;
  phoenix_experiment_id_candidate: string | null;
  status: ExperimentStatus;
  baseline_release_score: number | null;
  candidate_release_score: number | null;
  baseline_critical_failure_rate: number | null;
  candidate_critical_failure_rate: number | null;
  baseline_latency_p50_ms: number | null;
  candidate_latency_p50_ms: number | null;
  baseline_hallucination_rate: number | null;
  candidate_hallucination_rate: number | null;
  regression_cases_pass_rate: number | null;
  safety_canary_pass_rate: number | null;
  eval_summary_json: Record<string, unknown> | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}

export interface ReleaseGateDecision {
  release_gate_decision_id: string;
  experiment_id: string;
  decision: ReleaseDecision;
  release_score: number;
  promotion_rules_passed: number;
  rules_detail_json: Record<string, unknown> | null;
  requires_human_approval: boolean;
  decided_at: string;
}

export interface HumanApproval {
  human_approval_id: string;
  release_gate_decision_id: string;
  reviewer_id: string;
  status: string;
  comment: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface AuditEvent {
  audit_event_id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  actor: string;
  detail_json: Record<string, unknown> | null;
  created_at: string;
}

// API Response envelope
export interface ApiResponse<T = unknown> {
  ok: boolean;
  data: T | null;
  error: string | null;
  request_id: string | null;
}

export interface PaginatedData<T = unknown> {
  items: T[];
  total_count: number;
  page: number;
  page_size: number;
  has_next: boolean;
}
