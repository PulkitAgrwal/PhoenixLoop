# PhoenixLoop

**A Gemini support agent that detects its own failures through Phoenix and fixes itself with evidence.**

`Python 3.11+` | `Next.js 14+` | `Phoenix Cloud`

---

## What is PhoenixLoop

PhoenixLoop is a self-healing AI support agent built on Google ADK and Gemini with Arize Phoenix for full-stack observability. It handles real customer support tickets, traces every conversation through Phoenix, and evaluates quality automatically with 14 evaluators (7 code + 4 LLM judge + 3 Phoenix tool). When failure patterns cross a threshold, the system aggregates them, diagnoses root causes by querying Phoenix MCP for operational evidence, proposes targeted prompt patches, runs baseline-vs-candidate Phoenix experiments, and gates releases through a human-approval workflow. Every failure becomes a safer next release.

---

## The Self-Healing Loop

```
Trace --> Evaluate --> Aggregate --> Diagnose --> Repair --> Experiment --> Gate
  ^                                                                        |
  +--------------------------- Approve & Promote -------------------------+
```

1. **Trace** -- Every conversation is captured as structured traces and spans in Phoenix via OpenInference.
2. **Evaluate** -- 14 evaluators (7 LLM-based + 7 code) score each session and span automatically.
3. **Aggregate** -- Failure patterns are counted and thresholds are checked.
4. **Diagnose** -- The reliability copilot queries Phoenix MCP for traces, annotations, and prompts to identify the root cause.
5. **Repair** -- A narrow prompt or tool-policy patch is proposed and written back to Phoenix via MCP.
6. **Experiment** -- Baseline and candidate prompts are tested side-by-side using Phoenix experiments with the same dataset and all 14 evaluators.
7. **Gate** -- Metrics thresholds must pass. A human reviews and approves before the candidate is promoted to production.

---

## Local Setup

### Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.11 – 3.13 (3.14 is not yet supported) | `python3 --version` |
| Node.js | 18+ | `node --version` |
| npm | 9+ | `npm --version` |

### Step 1: Clone and install

```bash
cd /path/to/project
chmod +x setup.sh
./setup.sh
```

This will:
- Create a Python virtual environment at `backend/.venv` (auto-selects Python 3.13/3.12/3.11)
- Install all backend pip dependencies
- Install all frontend npm dependencies
- Copy `.env.example` to `.env`
- Create the SQLite database with all 11 tables

### Step 2: Configure API keys

Open `.env` and fill in two keys:

```bash
nano .env   # or use any editor
```

**GOOGLE_API_KEY** — required for the Gemini agent and LLM judge evaluators:
1. Go to [https://aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Click **Create API Key**
3. Paste into `.env` as `GOOGLE_API_KEY=<your-key>`

**PHOENIX_API_KEY** — required for tracing, annotations, and experiments:
1. Go to [https://app.phoenix.arize.com](https://app.phoenix.arize.com)
2. Sign up (free) and create a space
3. Go to **Settings > API Keys**, create one
4. Paste into `.env` as `PHOENIX_API_KEY=<your-key>`
5. Set `PHOENIX_BASE_URL` to your space URL (default `https://app.phoenix.arize.com`)

### Step 3: Start the backend

```bash
cd backend
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

Verify it's running: open [http://localhost:8000/docs](http://localhost:8000/docs) for Swagger UI.

### Step 4: Start the frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

### Step 5: Seed demo data and run

1. On the home page, click **"Seed Demo Data"** — this loads 68 support tickets into the database
2. Go to **Conversation** — pick a ticket from the dropdown and click **Run Agent**
3. Explore the other pages: **Traces & Evals**, **Failure Trends**, **Improvements**, **Experiments**, **Release Gate**

You can also seed and run via the API directly:

```bash
# Seed demo tickets
curl -X POST http://localhost:8000/api/demo/seed

# Run agent on first 5 tickets
curl -X POST http://localhost:8000/api/demo/run-all

# Check health
curl http://localhost:8000/api/health
```

### Useful URLs

| URL | What |
|---|---|
| [localhost:3000](http://localhost:3000) | Frontend dashboard |
| [localhost:8000/docs](http://localhost:8000/docs) | Swagger UI (auto-generated, always up to date) |
| [localhost:8000/redoc](http://localhost:8000/redoc) | ReDoc API reference |
| [localhost:8000/api/health](http://localhost:8000/api/health) | Health check endpoint |

### Troubleshooting

| Problem | Fix |
|---|---|
| `ensurepip` error on setup | You're on Python 3.14. Install Python 3.13: `brew install python@3.13` |
| `GOOGLE_API_KEY` not set | Edit `.env` — the agent and LLM judges won't work without it |
| Frontend can't reach backend | Check backend is on port 8000 and `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` |
| Database errors | Delete `phoenixloop.db` and re-run `setup.sh` to recreate tables |
| Phoenix traces not appearing | Verify `PHOENIX_API_KEY` and `PHOENIX_BASE_URL` in `.env` |

---

## Architecture

PhoenixLoop uses a FastAPI backend running a Google ADK agent powered by Gemini. Every agent interaction is traced through OpenInference and sent to Phoenix Cloud for storage, evaluation, and experimentation. The reliability copilot communicates with Phoenix through bidirectional MCP -- reading traces, annotations, and prompts for diagnosis, and writing back candidate prompts, tags, and dataset examples for repair. Workflow state is tracked in a local SQLite database. The frontend is a Next.js application built with shadcn/ui that provides a dashboard for support conversations, the self-healing loop status, and human approval gates.

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Backend | Python 3.11+, FastAPI, Google ADK, Gemini | Agent runtime, API service, LLM reasoning |
| Observability | Arize Phoenix, OpenInference, OpenTelemetry | Tracing, evaluations, prompt management, experiments |
| Frontend | Next.js 14, TypeScript, shadcn/ui, Tailwind CSS, Framer Motion | Dashboard UI, conversation view, approval workflows |
| Database | SQLite with WAL mode | Workflow state, entity storage, failure tracking |

---

## Phoenix Integration

PhoenixLoop exercises seven pillars of Phoenix integration in every healing cycle:

1. **Traces and Spans** -- OpenInference auto-instrumentation captures every agent run, tool call, LLM invocation, and evaluation as structured traces and spans in Phoenix Cloud.

2. **Sessions** -- Each support conversation maps to a Phoenix session with metadata (customer ID, ticket category, prompt version, outcome) for grouping and filtering.

3. **Annotations** -- 14 pre-registered annotation configs capture evaluator results at both the session level (resolution correctness, policy compliance, safety/privacy) and the span level (groundedness, tool selection, tool invocation, tool response handling, and more).

4. **Evaluator Hub** -- All 7 LLM-based evaluators are registered in the Phoenix Evaluator Hub with version history. Each evaluator call generates its own OpenTelemetry trace in Phoenix, enabling recursive observability.

5. **Prompt Management** -- Prompts are versioned and stored in Phoenix with tag-based promotion workflow (`candidate`, `production`, `rejected`, `previous`). The agent always loads the prompt tagged `production`.

6. **Experiments** -- Baseline and candidate prompts are tested side-by-side using `run_experiment()` with dry-run support. Both experiments use the same dataset and all 14 evaluators, appearing under the same dataset in Phoenix UI for comparison.

7. **MCP Server** -- Bidirectional Phoenix MCP provides the read path (traces, spans, annotations, prompts, experiments, datasets) for diagnosis and the write path (`upsert-prompt`, `add-prompt-version-tag`, `add-dataset-examples`) for repair. MCP is the primary interface between the reliability copilot and Phoenix.

---

## License

MIT
