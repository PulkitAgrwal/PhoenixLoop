# PRD: PhoenixLoop — Self-Healing Gemini Support Agent

**Document type:** Product Requirements Document (as built)
**Project:** PhoenixLoop
**Submission track:** Arize Track, Google Cloud Rapid Agent Hackathon 2026
**Demo domain:** Support QA agent for a fictional SaaS named AcmeFlow
**Last verified:** 2026-06-07
**PRD version:** 4.0 — rewritten to reflect the built system

---

## 0. Executive summary

PhoenixLoop is a self-healing Gemini support agent that detects its own failures, diagnoses root causes by reading its own observability data, generates targeted prompt patches, validates them against frozen regression sets, and gates promotion on score deltas.

The agent answers AcmeFlow customer-support tickets using three deterministic tools (`get_customer_context`, `search_policy`, `create_escalation`) plus a Phoenix-MCP-backed few-shot retriever. Every run is traced. Fourteen evaluators (7 code · 4 LLM judges · 3 Phoenix tool evals) score every run. Failures aggregate by deterministic `failure_key`. A separate diagnosis sub-agent — whose tool surface is the Phoenix MCP server — reads the failing spans back, names the recurring pattern, and proposes the minimal prompt change. An experiment runner scores baseline-vs-candidate on a 5-example regression set with code-evals only. A release-gate decides PROMOTED / REJECTED / PENDING REVIEW. Promotion flips the local active prompt version; the next agent run picks it up.

The Arize-track signal is the diagnosis sub-agent path: it produces visible `phoenix-mcp:get-spans` and `phoenix-mcp:get-span-annotations` spans on every failure cluster — observability data flowing back into reasoning.

One-line pitch:

> The agent that watches itself in Phoenix and rewrites its own prompt — measurably, not theoretically.

---

## 1. Source verification and grounding

### 1.1 Contest facts verified

| Claim | Verified data | Source |
|---|---|---|
| Hackathon deadline | 2026-06-11 at 2:00 PM PDT | [S1] |
| Contest period | 2026-05-05 12:00 PM PT to 2026-06-11 2:00 PM PT | [S2] |
| Public participant scale | ~6.5k participants at verification time | [S1], [S3] |
| Total cash prizes | USD 60,000 | [S1] |
| Partner tracks | Arize, Elastic, Fivetran, GitLab, MongoDB, Dynatrace | [S1], [S2] |
| Arize prizes | 1st USD 5,000, 2nd USD 3,000, 3rd USD 2,000 | [S2] |
| Required project type | Functional agent powered by Gemini and Google Cloud Agent Builder, integrating a partner MCP server | [S2] |
| Required platform | Web, Android, or iOS | [S2] |
| Required repo | Public open-source repo with visible open-source license | [S2] |
| Required video | Demo video ≤3 minutes; YouTube or Vimeo, English | [S2] |
| Judging criteria | Equal weight: technological implementation · design · potential impact · quality of idea | [S2] |
| Judging process | Stage One pass/fail viability gate, then scored judging | [S2] |
| Tie-break order | Technological implementation → design → impact → idea quality | [S2] |
| AI tooling restriction | Google Cloud AI tools required; partner built-in AI features permitted; other AI tools not permitted | [S2] |
| Team size limit | Max 4 persons | [S2] |

### 1.2 Arize track facts verified

| Claim | Verified data | Source |
|---|---|---|
| Arize track theme | Build Gemini agents with full observability and self-introspection via MCP | [S3] |
| Evaluation emphasis | Technical implementation, meaningful tracing and MCP use, self-improvement loop quality, overall impact | [S3] |
| Runtime constraint | Arize requires a code-owned runtime; visual Agent Builder alone does not provide tracing integration | [S3] |
| Instrumentation | OpenInference auto-instrumentors exist for Google ADK, Google GenAI, etc. | [S3] |
| Phoenix hosting | Phoenix Cloud or self-hosted Phoenix | [S3] |
| MCP | Configure Phoenix MCP so the agent can introspect operational data at runtime | [S3] |
| Bonus direction | Bonus credit for agents that use observability data to improve over time | [S3] |
| Starter resource | Arize Gemini hackathon starter (referenced for setup patterns; no code copied) | [S3], [S23] |

---

## 2. Product

### 2.1 Identity

**PhoenixLoop — a self-healing Gemini support agent.** Real support behavior on the hot path; a real self-improvement loop in the background.

### 2.2 Thesis

Most hackathon agents demo a happy path. PhoenixLoop demonstrates the harder, more valuable behavior: what happens when an agent fails, how Phoenix evidence powers diagnosis, how a safe repair is proposed and proven, and how promotion is gated on the score delta.

### 2.3 Why this framing

| Alternative framing | Why we didn't pick it |
|---|---|
| Phoenix-feature wrapper | Judges see infrastructure, not an agent solving real problems |
| Support bot with logging | Generic; doesn't exercise Phoenix beyond tracing |
| Dashboard rebuild | Originality question — looks like a UI over someone else's product |

PhoenixLoop leads with the agent solving real tickets. The self-healing loop is the differentiator, not the entire product.

### 2.4 Personas

| Persona | Goal | How they use it |
|---|---|---|
| **Alex — AI Engineer** (primary) | Ship a support agent that improves without manual prompt-tweaking | Configures the healing loop, reviews proposals, monitors Phoenix |
| **Jordan — Support Ops Lead** | Meet resolution-rate and safety SLAs | Approves/rejects prompt changes; trusts the loop to surface problems early |
| **Sam — End Customer** | Get an accurate, fast answer | Interacts with the agent; never sees the healing infrastructure |
| **Morgan — Demo Viewer** (judge) | Understand what "self-healing" means concretely | Watches the demo: failure → diagnosis → patch → experiment → verdict |

### 2.5 Demo domain — AcmeFlow

AcmeFlow is a fictional project-management SaaS with Free, Pro, Business, and Enterprise plans; monthly and annual billing; refund/admin-access/privacy/outage-credit policies. Eight ticket categories drive the seed:

| Category | Required behavior |
|---|---|
| Refund request | Lookup customer + subscription + refund eligibility. Cite policy. No unsupported promises. |
| Billing dispute | Lookup invoices, check duplicates, escalate if unclear. |
| Workspace admin access | Verify ownership; refuse without proof; escalate. |
| Data export | Check role + privacy policy; require verified admin. |
| Privacy-sensitive | Refuse to disclose another user's data; cite privacy policy. |
| Legal threat | Escalate to legal. Do not negotiate. |
| Outage credit | Check outage policy + tier. Escalate enterprise. |
| Ambiguous | Clarify or look up safely. No assumptions. |

The auto-seed runs four demo tickets plus two fail-twins (intentional `CitationPresence` failures on refund cases) so the loop fires on first boot.

---

## 3. Architecture

### 3.1 System diagram

```
                ┌───────────────────────────────────────────────────┐
                │  Next.js 14 dashboard (App Router · permanent dark)│
                │                                                    │
                │  Top nav + contextual sub-tabs                     │
                │  /, /conversation, /activity/{runs,failures},      │
                │  /healing/{improvements,experiments,release-gate}, │
                │  /prompts, /settings                               │
                └───────────────────────────┬───────────────────────┘
                                            │ fetch /api/*
                                            ▼
┌───────────────────────────────────────────────────────────────────┐
│  FastAPI · uvicorn                                                │
│                                                                   │
│  api/        tickets · conversations · evals · failures ·         │
│              improvements · experiments · release_gate · prompts ·│
│              activity · stats · seed · demo · config · health     │
│                                                                   │
│  agent/      support_agent.run_agent   ── Google ADK + Gemini     │
│              diagnosis_agent           ── ADK + Phoenix MCP       │
│              prompts.get_production_prompt(db)   ◄── local DB     │
│              tools (3): get_customer_context, search_policy,      │
│              create_escalation + retrieve_similar_resolutions     │
│                                                                   │
│  evaluation/ runner + 7 code + 4 LLM judges + 3 Phoenix tool      │
│              evals (14 total)                                     │
│  diagnosis/  failure_aggregator · proposal_generator              │
│  experiments/ orchestrator (code-evals only, 5-example cap) ·     │
│              release_gate (6 rules)                               │
│  tracing/    phoenix.otel.register(auto_instrument=True, batch)   │
│                                                                   │
└─────────┬──────────────────────────────────────────┬──────────────┘
          │                                          │
          ▼                                          ▼
┌──────────────────────────────────┐    ┌──────────────────────────────┐
│  SQLite (WAL, FK on)             │    │  Arize Phoenix Cloud         │
│  ◄ canonical for hot-path data   │    │  ◄ observability surface     │
│                                  │    │                              │
│  tickets · agent_runs (with      │    │  traces / spans / sessions   │
│   trace_id, root_span_id) ·      │    │  annotations (14 evaluator   │
│   evals · failure_aggregates ·   │ ◄┐ │    configs)                  │
│   improvement_triggers ·         │  │ │  experiments                 │
│   regression_examples ·          │  │ │  Evaluator Hub               │
│   experiments · release_gate_    │  │ │  prompts (mirror)            │
│   decisions · human_approvals ·  │  │ │  datasets (successful-       │
│   audit_events · prompts ·       │  │ │   resolutions)               │
│   prompt_versions                │  │ │                              │
└──────────────────────────────────┘  │ └──────────┬───────────────────┘
                                      │            │
                                      └──── @arizeai/phoenix-mcp ──────┐
                                            (read + write)              │
                                                                        ▼
                                                       diagnosis sub-agent
                                                       reads failing spans
```

### 3.2 Architectural rules

1. **Anything the agent reads on the hot path lives in the local DB.** Reading the active prompt is a SQLite row lookup, not a Phoenix round-trip. The agent keeps running if Phoenix is unreachable.
2. **Phoenix is the observability surface and the experiment runtime.** Not the configuration store.
3. **The MCP path is the diagnosis sub-agent.** The support agent does call MCP for few-shot retrieval, but the diagnosis sub-agent is where real-time `phoenix-mcp:*` spans show up on every demo run.
4. **Code-evals only in the experiment hot path.** No LLM judges inside `run_experiment` — deterministic, cheap, fast.
5. **All multi-table writes in transactions.** `PRAGMA foreign_keys = ON` on every connection. `PRAGMA journal_mode = WAL` on init.

### 3.3 Module map

```
backend/src/
├── config.py                       Pydantic settings + .env loading
├── exceptions.py                   Domain exception hierarchy
├── models.py                       Pydantic models + enums
├── db.py                           Schema DDL, all SQL, FK + WAL
├── utils/retry.py                  @retry decorator (exponential backoff)
├── utils/logging_config.py         JSON / human dual-mode logging
│
├── tracing/
│   ├── phoenix_client.py           Phoenix client factory (singleton)
│   ├── instrumentor.py             phoenix.otel.register(auto_instrument=True)
│   └── annotations.py              14 annotation-config registrations
│
├── agent/
│   ├── tools.py                    get_customer_context · search_policy ·
│   │                                create_escalation + retrieve_similar_resolutions
│   ├── mcp_tools.py                Phoenix MCP toolset factory + lifespan mgmt
│   ├── prompts.py                  get_production_prompt(db)
│   ├── schemas.py                  AgentResponseContract (structured output)
│   ├── support_agent.py            run_agent / run_agent_events (SSE)
│   └── diagnosis_agent.py          ADK Agent with Phoenix MCP toolset
│
├── evaluation/
│   ├── runner.py                   BaseEvaluator + dispatcher
│   ├── code_evals/                 7 deterministic code evaluators
│   ├── llm_judges/combined.py      4 judges batched in one Gemini call
│   │                                  (incl. Phoenix Evals HALLUCINATION +
│   │                                  QA templates embedded verbatim)
│   └── tool_evals/combined.py      3 Phoenix tool-evaluators
│
├── diagnosis/
│   ├── failure_aggregator.py       Failure_key clustering + threshold logic
│   └── proposal_generator.py       patch_synthesis (one-line prompt diff)
│
├── experiments/
│   ├── orchestrator.py             run_experiment (5-example cap, code-evals only)
│   └── release_gate.py             check_promotion_rules · approve · reject
│
├── api/
│   ├── dependencies.py             get_db_session, get_request_id, pagination
│   ├── middleware.py               request-id + global exception handlers
│   ├── tickets.py, conversations.py, evals.py, failures.py
│   ├── improvements.py             analyze (sub-agent → fallback) · generate-regressions
│   ├── experiments.py
│   ├── release_gate.py
│   ├── prompts.py                  list/get/list_versions + POST create + POST experiment
│   ├── activity.py
│   ├── stats.py                    /api/stats — landing-page metrics
│   ├── seed.py                     full_loop_seed (live + lightweight)
│   ├── demo.py
│   ├── config_api.py
│   └── health.py
│
└── main.py                         FastAPI app, CORS, lifespan
                                    (init_db + Phoenix instrumentor + MCP
                                     warm-up + background auto-seed)
```

### 3.4 Frontend structure

```
frontend/src/
├── app/
│   ├── layout.tsx                  TopNav + skip-to-content
│   ├── page.tsx                    Landing — hero, stats strip, 7-node loop,
│   │                                 evidence row, architecture SVG, code walks,
│   │                                 comparison table, anti-claim, CTA, footer
│   ├── conversation/page.tsx       Two-column lg+, stacked mobile
│   ├── activity/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── runs/page.tsx           Agent runs + expanding TraceWaterfall
│   │   └── failures/page.tsx       Dense list + recharts sparkline + brand-green
│   │                                 left border on selected
│   ├── healing/
│   │   ├── layout.tsx, page.tsx
│   │   ├── improvements/page.tsx   Triggers list + DiagnosisTrace + PromptDiff
│   │   │                             + RegressionList
│   │   ├── experiments/page.tsx    Scoreboard (baseline vs candidate, ASCII bars)
│   │   └── release-gate/page.tsx   Decisions list + 6-rule criteria
│   ├── prompts/page.tsx            Master-detail + Edit modal + diff tabs
│   └── settings/page.tsx           Config readout + health probes
│
└── components/
    ├── ui/                         Button, Card, Tag, Eyebrow, KBD, CodeBlock,
    │                                 CodeInline, StatusDot, MetricNumber,
    │                                 HairlineDivider, GridOverlay (built from
    │                                 scratch against DESIGN.md tokens)
    ├── layout/                     top-nav, page-header, page-tabs
    ├── shared/                     phoenix-deep-link (inert chip when unset),
    │                                 status-badge, stat-card
    ├── traces/                     trace-waterfall, span-detail, eval-badge
    ├── conversation/               chat-interface, live-trace-pane, tool-call-card,
    │                                 message-bubble, scenario-selector
    ├── improvements/               diagnosis-trace, prompt-diff (using `diff` pkg),
    │                                 evidence-card, regression-list
    ├── experiments/                score-comparison (scoreboard table),
    │                                 prompt-changes-section
    └── prompts/                    version-list, version-detail, edit-prompt-dialog,
                                      confirm-save-dialog, prompt-diff-*
```

The frontend was rewritten end-to-end against `DESIGN.md` — voltagent-inspired: canvas `#101010`, single brand-green accent `#00d992`, hairline `#3d3a39`, Inter + SF Mono, permanent dark. Anti-slop rules in DESIGN.md (no gradients, glassmorphism, drop shadows, emoji icons, rounded-3xl bubbles, light mode, logo wall, or identical-rounded-card grids) are honored throughout.

---

## 4. Critical paths

### 4.1 Path A — Run a conversation

1. UI streams `POST /api/tickets/{id}/run/stream` (SSE).
2. `support_agent.run_agent` reads the active prompt from the local DB (`prompts.active_version_id` → `prompt_versions.prompt_text`).
3. Within `using_attributes(...)` ADK runs Gemini; `trace_id` / `root_span_id` / `phoenix_session_id` are captured lazily on the first event.
4. Tool calls — `get_customer_context`, `search_policy`, optionally `create_escalation`, plus `retrieve_similar_resolutions` (MCP) — stream to Phoenix as spans.
5. SSE emits `agent_start` → `tool_call_started` / `tool_call_completed` × N → `text_chunk` → `agent_done` → `eval_result` × 14 → `done`.
6. The `agent_runs` row is written with `prompt_version_id` so every conversation is anchored to the exact prompt that produced it.

### 4.2 Path B — Evaluate

`EvaluationRunner` invokes all 14 evaluators against the run:

- **Code-evals (7):** schema_validity, tool_sequence, refund_guard, privacy_guard, escalation_guard, citation_presence, latency_budget. Deterministic Python.
- **LLM judges (4):** groundedness (uses Phoenix `HALLUCINATION_PROMPT_TEMPLATE`), resolution_correctness (uses Phoenix `QA_PROMPT_TEMPLATE`), policy_compliance (custom), safety_privacy (custom). Batched into a single Gemini call via `CombinedLLMJudges`.
- **Phoenix tool evals (3):** ToolSelection, ToolInvocation, ToolResponseHandling. Gated behind `ENABLE_LLM_TOOL_EVALS` (default off — code-evals catch the same regressions cheaply).

Results write to the local `evals` table AND to Phoenix as span annotations via `client.spans.log_span_annotations()`. Pre-registered annotation configs in Phoenix (`tracing/annotations.py`) ensure the labels render correctly in the Phoenix UI.

### 4.3 Path C — Failure aggregation and trigger

Each failed eval bumps a `failure_aggregates` row keyed by deterministic `failure_key` (e.g. `citation_presence__refund`). When `occurrence_count >= REPEATED_FAILURE_COUNT` (default 2), a new `improvement_triggers` row is created.

Critical-failure categories (privacy_leak, wrong_escalation) trigger on a single occurrence.

### 4.4 Path D — Diagnose

`POST /api/improvements/{trigger_id}/actions/analyze` invokes the diagnosis sub-agent.

The diagnosis sub-agent (`agent/diagnosis_agent.py`):
- ADK `Agent` with the lifespan-managed Phoenix MCP toolset as its tool surface
- Prompt limits to ≤2 MCP calls per diagnosis (`get-spans` + `get-span-annotations`)
- Emits a JSON-conforming `DiagnosisAgentResult` (post-hoc Pydantic parse, since ADK 1.18 `output_schema × tools` is incompatible)
- Result includes `mcp_tools_used: list[str]` which powers the Diagnosis Trace panel in the UI

If MCP is unavailable, the path degrades gracefully to the legacy service-side `diagnose()`.

`proposal_generator.generate_proposal()` then runs as a separate Gemini call (`gemini_call_purpose=patch_synthesis`), produces a one-line prompt diff, persists it as a new `prompt_versions` row (`source = diagnosis_proposal`, FK'd to the trigger), and mirrors to Phoenix via MCP `upsert-prompt`.

### 4.5 Path E — Experiment

`POST /api/experiments` → `orchestrator.run_experiment`:
- Loads 5 frozen regression examples (or a derived set)
- Runs baseline prompt against each example, scores with code-evals only, averages → `baseline_release_score`
- Runs candidate prompt against each example, scores with code-evals only, averages → `candidate_release_score`
- Persists both, computes verdict via `release_gate.score(...)`
- 10 Gemini calls per experiment (5 baseline + 5 candidate); no judge round-trips

### 4.6 Path F — Release gate

Six rules — `check_promotion_rules`:
1. Candidate score ≥ baseline + δ
2. Critical-failure rate ≤ baseline critical-failure rate
3. Regression canaries pass rate ≥ 90%
4. Safety canaries pass rate = 100%
5. Latency p50 within budget
6. Score above `RELEASE_SCORE_THRESHOLD` (default 0.75)

Verdicts: `promoted` · `rejected` · `pending_human_review` · `blocked_critical_failure`. On promotion, `set_active_version(prompt_id, candidate_version_id)` flips the local pointer; the next `run_agent` invocation picks up the new prompt. The Phoenix mirror gets the `production` tag for visibility.

### 4.7 Path G — Auto-seed on first boot

`backend/src/api/seed.py:full_loop_seed`:
- Idempotent — returns `{"skipped": True}` if `agent_runs` is non-empty
- Runs as an `asyncio.create_task(...)` in the lifespan so the API becomes reachable in ~5s while the seed proceeds in the background
- **Live mode** (default): runs 4 demo tickets + 2 fail-twins → evals → aggregate → diagnosis sub-agent → proposal → experiment → release-gate verdict. ~60–90s, ~30 Gemini calls total
- **Lightweight mode** (`LIGHTWEIGHT_DEMO=true`): reads JSON from `backend/tests/fixtures/seed/`. Zero Gemini calls, completes in <1s

`scripts/reset_db.py` wipes the host's `phoenixloop.db` + WAL/SHM sidecars and recreates the schema. `docker compose down -v` wipes the Docker volume.

---

## 5. Phoenix integration

| Surface | Implementation |
|---|---|
| Tracing | `phoenix.otel.register(project_name="phoenixloop", auto_instrument=True, batch=True, protocol="http/protobuf")` — captures both ADK agent spans and direct `google-genai` calls |
| Span IDs on AgentRun | Captured lazily inside `using_attributes(...)` block in `support_agent.py`. Stored on `agent_runs.trace_id` + `agent_runs.root_span_id` so Phoenix deep-links from the UI hit the right span |
| Annotations | 14 annotation configs registered at startup via `tracing/annotations.py`. Eval results write via `client.spans.log_span_annotations()` |
| LLM judges | `CombinedLLMJudges` batches all 4 judges into one Gemini call. Two judges (`groundedness`, `resolution_correctness`) embed Phoenix Evals templates verbatim (`HALLUCINATION_PROMPT_TEMPLATE`, `QA_PROMPT_TEMPLATE`) — credible "uses Phoenix Evals" story without inventing wrappers |
| Phoenix MCP — runtime | The diagnosis sub-agent's tool surface is the Phoenix MCP toolset (`@arizeai/phoenix-mcp@latest` via npx). Every diagnosis produces visible `phoenix-mcp:get-spans` and `phoenix-mcp:get-span-annotations` spans |
| Phoenix MCP — datasets | The support agent's `retrieve_similar_resolutions` tool calls Phoenix MCP `get-dataset-examples(dataset='successful-resolutions')`. Top-3 cap. Gracefully degrades when the dataset is absent |
| Phoenix MCP — prompts | `proposal_generator` calls MCP `upsert-prompt` to mirror the candidate version; release-gate approval calls `add-prompt-version-tag` with `production` |
| Experiments | Local `experiments` rows are canonical. Phoenix experiment IDs (`phoenix_experiment_id_baseline` / `phoenix_experiment_id_candidate`) are recorded for deep-link |

### Phoenix write strategy

Prompts are mirrored to Phoenix, not authored there. The local DB stays canonical for the active prompt so the agent's hot path doesn't depend on Phoenix availability. Mirror writes happen lazily on proposal generation and release-gate promotion.

---

## 6. Agent surface

### 6.1 Tools (3 + 1)

| Tool | Purpose | Signature |
|---|---|---|
| `get_customer_context` | Customer profile + subscription + entitlements (incl. `refund_eligible` + reason) + recent tickets | `(customer_id: str) -> CustomerContext` |
| `search_policy` | RAG over `data/policies/*.md` | `(query: str, category: str \| None) -> list[PolicyMatch]` |
| `create_escalation` | Real write action with distinct trace semantics | `(ticket_id, reason, target_team) -> EscalationRecord` |
| `retrieve_similar_resolutions` | Phoenix-MCP-backed few-shot retriever (top-3 from `successful-resolutions` dataset, in-process TTL cache 5 min) | `(category: str, brief: str) -> list[ResolutionExample]` |

Consolidated from the original 6-tool surface. `draft_customer_response` was deleted entirely — the model IS the language model; tool calls that just echo the response schema force a pointless Gemini→tool→Gemini ping-pong.

### 6.2 Models

- **Support agent:** `gemini-2.5-flash`, `thinking_budget=128`
- **Diagnosis sub-agent:** `gemini-2.5-flash`, `thinking_budget=128`
- **Proposal generator:** `gemini-2.5-flash`, single call per failure cluster (`gemini_call_purpose=patch_synthesis`)
- **LLM judges:** `gemini-2.5-flash`, one batched call per agent run (`gemini_call_purpose=judges_combined`)
- **Experiment runner:** `gemini-2.5-flash` for both baseline and candidate (5+5 calls)

Flash everywhere. No Pro, no Flash-Lite. Engineered thought: tune `thinking_budget` per agent rather than reach for a bigger model.

### 6.3 Structured output

ADK 1.18 `output_schema × tools` is incompatible (`llm_agent.py:301-307`). We use fallback (b): tools enabled + prompt demands JSON + post-hoc Pydantic parse with a synthesized fallback on parse failure. Same surface guarantee from the UI's perspective; works with the tool surface intact.

---

## 7. Evaluation framework

14 evaluators, all named, all deterministic in outcome (LLM judges are deterministic in scoring rubric even if generative).

### 7.1 Code-evals (7)

| Evaluator | Checks |
|---|---|
| `SchemaValidity` | Response conforms to `AgentResponseContract` |
| `ToolSequence` | Required tools called for category (e.g. REFUND requires `get_customer_context`) |
| `RefundGuard` | No refund promised unless `entitlements.refund_eligible == True` |
| `PrivacyGuard` | No disclosure of another user's data |
| `EscalationGuard` | Legal/admin/critical categories escalated |
| `CitationPresence` | Refund/policy answers cite `[P-XXX]` policy IDs |
| `LatencyBudget` | Wall-clock within `LATENCY_BUDGET_MS` |

### 7.2 LLM judges (4)

| Evaluator | Source |
|---|---|
| `groundedness` | Phoenix `HALLUCINATION_PROMPT_TEMPLATE` embedded inside batched call |
| `resolution_correctness` | Phoenix `QA_PROMPT_TEMPLATE` embedded inside batched call |
| `policy_compliance` | Custom — encodes AcmeFlow-specific [P-XXX] format + refund-window logic |
| `safety_privacy` | Custom — refusal language for privacy-sensitive requests |

All four batched into one Gemini call (`CombinedLLMJudges`). Zero extra round-trips per run.

### 7.3 Phoenix tool evals (3)

`ToolSelectionEvaluator`, `ToolInvocationEvaluator`, `ToolResponseHandlingEvaluator` — gated behind `ENABLE_LLM_TOOL_EVALS` (default off). Deterministic code-evals catch the same regressions on the 3-tool surface.

### 7.4 Failure-key formula

```
failure_key = f"{evaluator_name}__{ticket_category}".lower()
```

Deterministic. Stable across runs. Drives the failure-aggregator clustering.

---

## 8. Self-healing loop

### 8.1 Trigger thresholds

```yaml
hackathon_thresholds:
  repeated_failure_count: 2
  repeated_failure_rate: 0.30
  critical_failure_immediate: true
  cooldown_minutes: 30
  release_score_threshold: 0.75
```

Critical-failure categories: privacy_leak, wrong_escalation. One occurrence trips immediate analysis. Never triggers automatic promotion — release-gate still applies.

### 8.2 Diagnosis sub-agent

Located at `backend/src/agent/diagnosis_agent.py`. Tool surface = Phoenix MCP toolset. Prompt:

- Instructs ≤2 MCP calls per diagnosis (token budget)
- Demands a single JSON object matching `DiagnosisAgentResult`
- Confidence rubric (0.9+ multiple spans clearly show same root cause, 0.6–0.8 partial, 0.3–0.5 guess, 0.0–0.2 no useful evidence)

Output shape:

```json
{
  "failure_pattern": "one-line description",
  "root_cause": "underlying reason",
  "evidence_summary": "1-3 sentence summary from spans/annotations",
  "confidence": 0.0,
  "suggested_fix": "smallest prompt change that addresses this",
  "mcp_tools_used": ["get-spans", "get-span-annotations"]
}
```

The `mcp_tools_used` field powers the Diagnosis Trace panel in `/healing/improvements` — real tool names rendered as span rows with brand-green left borders.

### 8.3 Patch behavior

| Patch type | Allowed |
|---|---|
| One-line prompt addition (citation requirement, refund-eligibility check) | Yes |
| Tool policy rule | Yes |
| Escalation threshold change | Yes |
| Whole-prompt rewrite | No |
| Automatic deployment without release-gate verdict | No |

### 8.4 Release-gate rules

Six rules in `experiments/release_gate.py:check_promotion_rules`:

1. `candidate_score >= baseline_score + delta`
2. `candidate_critical_failure_rate <= baseline_critical_failure_rate`
3. `regression_cases_pass_rate >= 0.90`
4. `safety_canary_pass_rate == 1.00`
5. `candidate_latency_p50_ms <= LATENCY_BUDGET_MS`
6. `release_score >= RELEASE_SCORE_THRESHOLD`

Verdicts: `promoted`, `rejected`, `pending_human_review`, `blocked_critical_failure`. On `promoted`, the local prompt pointer flips; the next agent run uses the new prompt.

---

## 9. Data model

13 tables, FK-linked, WAL + `foreign_keys=ON`.

| Group | Tables |
|---|---|
| Ticket | `tickets` |
| Run | `agent_runs` (with `trace_id`, `root_span_id`, `phoenix_session_id`, `prompt_version_id` FK) |
| Eval | `evals`, `failure_aggregates` |
| Improvement | `improvement_triggers`, `regression_examples` |
| Experiment | `experiments` (FK: baseline & candidate prompt_version_ids), `release_gate_decisions`, `human_approvals` |
| Prompt | `prompts`, `prompt_versions` (with `source` enum, `improvement_trigger_id` FK, `parent_version_id`) |
| Cross-cutting | `audit_events` |

Schema details in `backend/src/db.py`. Pydantic models for all data crossing module boundaries in `backend/src/models.py` — no raw dicts in business logic.

---

## 10. API surface

All routes return the response envelope `{ok, data, error, request_id}`. All list endpoints support pagination via `?page=&page_size=`. All mutating endpoints accept `Idempotency-Key`.

| Group | Routes |
|---|---|
| Tickets | `GET /api/tickets`, `GET /api/tickets/{id}`, `POST /api/tickets/{id}/run`, `POST /api/tickets/{id}/run/stream` (SSE) |
| Conversations | `GET /api/conversations`, `GET /api/conversations/{id}` |
| Evals | `GET /api/evals/{run_id}`, `GET /api/failures?active_only=` |
| Improvements | `GET /api/improvements`, `GET /api/improvements/{id}`, `POST /api/improvements`, `POST .../actions/analyze`, `POST .../actions/generate-regressions` |
| Experiments | `GET /api/experiments`, `GET /api/experiments/{id}`, `POST /api/experiments` |
| Release gate | `GET /api/release-gate`, `GET /api/release-gate/{id}`, `POST .../actions/{approve,reject}` |
| Prompts | `GET /api/prompts`, `GET /api/prompts/{id}`, `GET .../versions`, `GET .../versions/{vid}`, `POST .../versions`, `POST .../versions/{vid}/actions/experiment` |
| Stats | `GET /api/stats` — `{agent_runs_traced, evaluators_wired, mcp_tool_calls_per_run_avg, prompts_auto_promoted}` |
| Activity | `GET /api/activity?limit=` |
| Demo | `POST /api/demo/seed`, `POST /api/demo/run-all`, `POST /api/demo/full-loop` |
| Config / Health | `GET /api/config`, `GET /api/health` |

Standard HTTP status codes: 200 / 201 / 400 / 404 / 409 / 500. Domain exceptions in `backend/src/exceptions.py` are mapped to error envelopes by global FastAPI handlers.

---

## 11. Frontend

### 11.1 Design system

Voltagent-inspired. See `DESIGN.md` for the full spec.

- **Canvas** `#101010` (only surface; permanent dark)
- **Brand** `#00d992` (single accent; CTA-only)
- **Hairline** `#3d3a39` (1px solid borders; the brand's elevation system)
- **Ink** `#f2f2f2` (default text), **Body** `#bdbdbd`, **Mute** `#8b949e`
- **Type:** Inter (display + body) + SF Mono (code + numeric metrics)
- **Radii:** 6px buttons / 8px cards / pill for inline status tags
- **Motion:** Framer Motion with `useReducedMotion()` + global `prefers-reduced-motion` halt

Anti-slop rules (enforced, non-negotiable): no gradients, no glassmorphism, no drop shadows, no emoji icons, no rounded-3xl bubbles, no light mode, no logo wall, no identical-rounded-card grids.

### 11.2 Pages

| Route | Strength |
|---|---|
| `/` | Landing: hero with real `phoenix.otel.register` IDE-card + faux terminal streaming `phoenix-mcp:*` lines; live `/api/stats` strip; 7-node loop with code tags; three-column evidence row; hand-built SVG architecture diagram; three code-walks; dense 6-row comparison table; anti-claim block; CTA band; footer |
| `/conversation` | Two-column lg+ (chat + live trace pane), stacked mobile. `phoenix-mcp:*` spans get a 2px brand-green left border in the trace pane. MCP count surfaced separately |
| `/activity/runs` | Agent-run table with expanding `TraceWaterfall` |
| `/activity/failures` | Dense list + per-row recharts sparkline + mono `failure_key` + 2px brand-green left border on selection + "Diagnose via Phoenix" CTA |
| `/healing/improvements` | Triggers list + `DiagnosisTrace` panel (consumes `diagnosis.mcp_tools_used` — real `phoenix-mcp` tool names rendered as span rows) + `PromptDiff` (using the `diff` package: additions brand-green, deletions mute strikethrough) + regression list |
| `/healing/experiments` | Baseline-vs-candidate scoreboard with ASCII block bars + per-metric Δ + PROMOTED / REJECTED verdict panel |
| `/healing/release-gate` | Decisions list + 6-rule criteria checklist |
| `/prompts` | Master-detail + edit modal with Edited / Original / Diff tabs + confirm-save dialog (draft vs experiment) |
| `/settings` | Config readout + Phoenix/Gemini health probes |

### 11.3 Accessibility

- `:focus-visible { outline: 2px solid #00d992; outline-offset: 2px; }` global
- Skip-to-content link in `layout.tsx`
- ARIA labels on every icon-only button; `aria-pressed`, `aria-expanded` on toggles
- Touch targets ≥44px (button sm height = 32px, default = 44px)
- `prefers-reduced-motion` halts animations globally
- 375px mobile: no horizontal scroll
- Phoenix deep-link renders an inert "Configure Phoenix" chip when `NEXT_PUBLIC_PHOENIX_URL` is unset — no 404s

---

## 12. Environment configuration

### 12.1 `.env`

```bash
# Google Gemini
GOOGLE_API_KEY=
GEMINI_MODEL=gemini-2.5-flash

# Arize Phoenix Cloud
PHOENIX_API_KEY=
PHOENIX_BASE_URL=https://app.phoenix.arize.com
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com
PHOENIX_PROJECT_NAME=phoenixloop

# App
APP_ENV=development
APP_PORT=8000
DATABASE_URL=sqlite:///phoenixloop.db
FRONTEND_URL=http://localhost:3000

# Thresholds (hackathon defaults)
REPEATED_FAILURE_COUNT=2
REPEATED_FAILURE_RATE=0.30
CRITICAL_FAILURE_IMMEDIATE=true
COOLDOWN_MINUTES=30
RELEASE_SCORE_THRESHOLD=0.75
LATENCY_BUDGET_MS=10000

# Demo / auto-seed
LIGHTWEIGHT_DEMO=false       # true → fixtures, zero Gemini calls
ENABLE_LLM_TOOL_EVALS=false  # keep off; code-evals catch the same regressions
```

### 12.2 `.gemini/settings.json`

```json
{
  "mcpServers": {
    "phoenix": {
      "command": "npx",
      "args": ["-y", "@arizeai/phoenix-mcp@latest"],
      "env": {
        "PHOENIX_API_KEY": "$PHOENIX_API_KEY",
        "PHOENIX_BASE_URL": "https://app.phoenix.arize.com"
      }
    }
  }
}
```

Lets a Gemini CLI user introspect the project's Phoenix workspace without further setup.

---

## 13. Token economy

Live-mode auto-seed produces ~30 Gemini calls end-to-end. Audit via:

```bash
grep gemini_call_purpose backend/logs/*.log | sort | uniq -c
```

Expected breakdown:

| `gemini_call_purpose` | Count | Note |
|---|---|---|
| `support_agent_response` | ~6 | One per seeded ticket |
| `judges_combined` | ~6 | Four judges batched into one call per run |
| `diagnosis_agent` | 3–4 | Multi-turn sub-agent with Phoenix MCP |
| `patch_synthesis` | 1 | Once per failure cluster |
| `experiment_baseline+candidate` | 10 | 5 regression cases × 2 prompts |

Lightweight mode: 0 calls.

---

## 14. Test coverage

```bash
cd backend && .venv/bin/python -m pytest tests/ -q
# 243 passed
```

Test groups:

- `tests/test_tools.py` — 3-tool surface contracts + 6 retrieval tests
- `tests/test_code_evals.py` — 7 code evaluators against fixtures
- `tests/test_config.py` — Pydantic settings + env loading
- `tests/agent/test_support_agent_mcp.py` — tool count + MCP toolset wiring
- `tests/agent/test_degraded_mode.py` — every path degrades cleanly when `PHOENIX_API_KEY` unset
- `tests/agent/test_diagnosis_agent.py` — sub-agent invocation with mocked MCP
- `tests/api/test_stats_api.py` — `/api/stats` (4 tests)
- `tests/api/test_seed_lightweight.py` — fixture-driven seed (4 tests)
- `tests/api/test_demo_full_loop.py` — live e2e
- `tests/evaluation/test_phoenix_evals_templates.py` — `HALLUCINATION_PROMPT_TEMPLATE` + `QA_PROMPT_TEMPLATE` integration
- Plus the existing API/diagnosis/experiments/release-gate/prompts test suites

---

## 15. Demo scenarios

The seed produces a complete, story-coherent demo data set automatically on first boot. From a clean DB:

1. `/activity/failures` shows two `CitationPresence` failures clustered on `citation_presence__refund` — repeated-failure threshold tripped
2. `/healing/improvements` shows one trigger. Click "Diagnose via Phoenix" — the diagnosis sub-agent runs, the Diagnosis Trace panel populates with `phoenix-mcp:get-spans` and `phoenix-mcp:get-span-annotations` rows. Confidence ~0.9
3. The prompt diff appears: one-line addition mandating `[P-XXX]` citation on refund responses. Additions brand-green, deletions mute-strikethrough
4. `/healing/experiments` shows one experiment with baseline ≈0.42, candidate ≈0.91, verdict PROMOTED
5. Click any Phoenix deep-link in the trace pane to land on the exact span in Phoenix Cloud with all 14 annotations attached
6. Re-run a refund ticket on `/conversation` — agent now cites the policy ID. Healed.

Total elapsed if the seed has run: under 2 minutes of clicking through.

---

## 16. Non-goals

1. Unrestricted self-modifying prompts in production.
2. Non-Gemini LLM backends.
3. Real customer data.
4. Mobile apps.
5. Fine-tuning during the hackathon.
6. Production-grade SLAs.
7. Multi-tenant accounts with OAuth.
8. Whole-prompt rewrites (only narrow patches allowed).
9. Automatic deployment without release-gate verdict.

---

## 17. Risks and mitigations

| Risk | Mitigation |
|---|---|
| ADK `output_schema × tools` incompatibility | Fallback (b): prompt-demands-JSON + post-hoc Pydantic parse, with a synthesized fallback on parse failure |
| Phoenix Cloud unavailable | All hot-path reads go to local SQLite. `retrieve_similar_resolutions` degrades gracefully when dataset is absent. Diagnosis sub-agent falls back to legacy service-side `diagnose()` |
| Gemini latency on demo | `thinking_budget` tuned per agent (128). Code-evals only inside experiments. Lightweight fixture mode for UI iteration |
| Token-budget overrun | Capped at 5 regression examples. Judges batched into one call per run. ~30 calls per full seed |
| Healthcheck timing out before live seed completes | Auto-seed runs as an `asyncio.create_task` in the lifespan — API reachable in ~5s, seed continues in background |
| Phoenix deep-link 404 when `NEXT_PUBLIC_PHOENIX_URL` unset | Render an inert "Configure Phoenix" chip instead of a broken link |

---

## 18. Submission status

| Item | Status |
|---|---|
| Working agent on Gemini + ADK | ✅ |
| Phoenix tracing live (auto-instrumented) | ✅ |
| 14 evaluators wired | ✅ |
| Phoenix MCP at runtime (diagnosis sub-agent) | ✅ |
| Phoenix MCP at runtime (few-shot retrieval) | ✅ |
| Bidirectional MCP (`get-*` + `upsert-prompt`) | ✅ |
| Phoenix Evals templates (2 of 4 judges) | ✅ |
| Experiment runner with real baseline/candidate scoring | ✅ |
| Release gate with 6 promotion rules | ✅ |
| Auto-seed on first boot (live + lightweight) | ✅ |
| Frontend rebuilt per DESIGN.md | ✅ |
| 243 pytest cases passing | ✅ |
| Open-source license | ✅ MIT |
| Public repo | Pending push |
| Hosted URL | Deferred — local-only contract for this session |
| Demo video | Deferred — local-only contract for this session |
| 5 hero screenshots | Deferred |

---

## 19. Judge-facing narrative

> "PhoenixLoop is a Gemini support agent that traces every run with Arize Phoenix, clusters its own failed evaluations, and uses Phoenix MCP at runtime to read its own failing spans back and propose a prompt fix. An experiment runner scores baseline vs candidate on a frozen regression set. A release gate decides whether to promote. We don't ship a demo of self-improvement — we ship a measurable one."

### Why this is Phoenix-native

1. **`phoenix.otel.register(auto_instrument=True)`** — canonical SDK call, picks up ADK + google-genai. Batched export, not synchronous per-call.
2. **14 evaluators write real annotations** onto the correct span (we capture `trace_id` + `root_span_id` inside `using_attributes`).
3. **2 of 4 LLM judges use Phoenix Evals templates** — `HALLUCINATION_PROMPT_TEMPLATE` + `QA_PROMPT_TEMPLATE` embedded verbatim. Custom judges for domain rules where Phoenix can't know our `[P-XXX]` citation format.
4. **Phoenix MCP is the diagnosis sub-agent's tool surface.** Real `get-spans` / `get-span-annotations` calls per demo. Visible in the trace pane with a brand-green left border.
5. **Phoenix MCP is also the support agent's few-shot retriever** via `get-dataset-examples`. The retrieval span is part of the user-facing trace.
6. **Real before/after.** No hard-coded numbers; the scoreboard reads `eval_summary_json` and the local `experiments` row.
7. **Engineering thought, not model thought.** Flash everywhere; `thinking_budget` tuned per agent; tool surface reduced from 6 to 3; code-evals only in the experiment hot path.

---

## 20. Source appendix

| ID | Description |
|---|---|
| S1 | Google Cloud Rapid Agent Hackathon overview, Devpost |
| S2 | Google Cloud Rapid Agent Hackathon official rules, Devpost |
| S3 | Arize track resources, Devpost |
| S4 | Phoenix MCP Server documentation |
| S5 | Phoenix MCP TypeScript package / API reference |
| S6 | Phoenix datasets and experiments overview |
| S7 | Phoenix dataset concepts |
| S8 | Phoenix evaluations guide |
| S9 | Phoenix get-started evaluations guide |
| S10 | Phoenix prompt management overview |
| S11 | Phoenix prompt concepts |
| S12 | Phoenix prompt iteration guide |
| S13 | Phoenix Python SDK / API reference |
| S14 | Arize Phoenix client |
| S15 | Phoenix sessions |
| S16 | Phoenix tracing overview |
| S17 | Phoenix annotations via client |
| S18 | OpenInference Google ADK instrumentation |
| S23 | Arize Gemini hackathon starter (referenced; no code copied) |
| S29 | Google Cloud: Build and deploy AI agent to Cloud Run using ADK |
| S30 | Google Cloud: Agent Development Kit |
| S33 | Google AI: Gemini structured outputs |
| S35 | Phoenix Evaluator Hub — Arize AX January 2026 Updates |
| S36 | Phoenix Evaluators Concepts documentation |
| S37 | Phoenix ToolInvocationEvaluator / ToolSelectionEvaluator documentation |
| S38 | Phoenix Prompt Management SDK — Quickstart Prompts Python |
| S39 | Phoenix Datasets & Experiments — `run_experiment()` documentation |
| S40 | Phoenix MCP Server write tools documentation |
| S41 | Arize blog: How to Evaluate Tool-Calling Agents |
