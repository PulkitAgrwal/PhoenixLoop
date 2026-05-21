# CLAUDE.md — PhoenixLoop Engineering Standards

## Project Overview
PhoenixLoop is a self-healing Gemini support agent. Full PRD: `/Users/pulkitagarwal/Desktop/PS2/Sem-2/Project/PRD.md`
Implementation Plan: `/Users/pulkitagarwal/Desktop/PS2/Sem-2/Project/docs/superpowers/plans/2026-05-17-phoenixloop-implementation.md`

## Before You Write Any Code
1. Read the PRD (link above)
2. Read the relevant task in the implementation plan
3. Read this entire file
4. Identify which files you're creating/modifying
5. Check existing code for patterns to follow — do NOT invent new patterns

## Tech Stack
- Backend: Python 3.11+, FastAPI, Google ADK, arize-phoenix-client, arize-phoenix-evals, aiosqlite
- Frontend: Next.js 14+, TypeScript, shadcn/ui, Tailwind CSS, Framer Motion
- Database: SQLite (dev) with WAL mode and foreign keys enabled
- No git operations. No commits. No git init.
- Backend venv at backend/.venv — never install globally

## Architecture Principles
- **Dependency Injection:** Services receive their dependencies (Phoenix client, DB, MCP client) as parameters. Never instantiate inside business logic.
- **Repository Pattern:** All database access goes through `db.py`. No raw SQL in business logic files.
- **Service Layer:** Business logic in service modules (agent/, evaluation/, diagnosis/, experiments/). API routes are thin — they validate input, call a service, return the response.
- **Abstract Base Classes:** Evaluators implement `BaseEvaluator`. Tools implement `BaseTool`. This is enforced, not optional.

## OOP Requirements
- Every evaluator MUST extend `BaseEvaluator` (defined in `evaluation/runner.py`)
- Every agent tool MUST extend `BaseTool` (defined in `agent/tools.py`)
- Use `typing.Protocol` for duck-typing interfaces where ABCs are too rigid
- Type hints on ALL function signatures, return types, and non-obvious variables
- Pydantic models for ALL data crossing module boundaries — no raw dicts

## Naming Conventions
| Context | Convention | Example |
|---|---|---|
| Python files | snake_case | `failure_aggregator.py` |
| Python classes | PascalCase | `FailureAggregator` |
| Python functions | snake_case | `update_aggregates()` |
| Python constants | UPPER_SNAKE | `MAX_RETRY_ATTEMPTS` |
| DB columns | snake_case | `failure_key` |
| API paths | kebab-case | `/api/release-gate` |
| API JSON fields | snake_case | `failure_key` |
| TypeScript files | kebab-case | `score-comparison.tsx` |
| TypeScript types | PascalCase | `ExperimentRecord` |
| TypeScript functions | camelCase | `fetchExperiment()` |
| CSS classes | kebab-case via Tailwind | `text-sm font-medium` |

## Database Rules (ACID)
- `PRAGMA foreign_keys = ON` on every connection
- `PRAGMA journal_mode = WAL` on initialization
- ALL multi-table writes in a transaction — no partial writes
- Use `INSERT OR REPLACE` for idempotent operations
- Seed operations (`POST /api/demo/seed`) are fully idempotent — safe to call repeatedly
- No orphan records — cascade deletes or prevent deletion if referenced

## API Design Rules
- Standard CRUD: POST (create), GET (list + get-by-id), PUT (full update), PATCH (partial update), DELETE (soft)
- NO redundant endpoints — use query params for filtering, not separate routes
- ALL list endpoints support pagination: `?page=1&amp;page_size=20`
- ALL mutating endpoints support `Idempotency-Key` header
- Response envelope: `{"ok": bool, "data": T | null, "error": str | null, "request_id": str}`
- HTTP status codes: 200 (success), 201 (created), 400 (bad request), 404 (not found), 409 (conflict/duplicate), 500 (internal error)
- FastAPI dependency injection for DB sessions, Phoenix client, config

## Error Handling
- Domain exceptions hierarchy in `backend/src/exceptions.py`
- Global FastAPI exception handlers convert domain exceptions to error envelope responses
- Every external call (Phoenix API, Gemini API, MCP) wrapped in `@retry` decorator
- Retry config: max_attempts=3, exponential backoff (1s, 2s, 4s)
- Log WARNING on each retry attempt with attempt number and error
- Log ERROR with full traceback on final failure
- No bare `except:` or `except Exception:` without specific handling + logging
- No `pass` in except blocks — handle it or re-raise it

## Logging
- Use Python `logging` module — no `print()` statements
- JSON structured logging in production, human-readable in development
- Every log line includes: timestamp, level, module, function, request_id
- Levels: ERROR (breaks operation), WARNING (recovered/retried), INFO (operation completed), DEBUG (detailed data)
- Log at the boundary: log when entering/exiting a significant operation, not every line

## Retry Utility
Located at `backend/src/utils/retry.py`. Use it for ALL external calls:
```python
from src.utils.retry import retry

@retry(max_attempts=3, backoff_base=1.0, retryable_exceptions=(httpx.TimeoutException,))
async def call_phoenix(...):
    ...
```

## What We're Doing Well (track as we build)

- Full type safety with Pydantic models at all boundaries
- ACID-compliant database operations
- Idempotent API design
- Structured logging with request_id propagation
- Retry with exponential backoff on all external calls
- Abstract base classes for extensible evaluator/tool systems
- Dependency injection throughout
- Consistent naming across Python/TypeScript/SQL/API

## Known Violations / Tech Debt (track as we build)

## Forbidden Patterns

- `# type: ignore` without adjacent comment explaining why
- `# noqa` without justification
- `pass` in except blocks
- `TODO` or `FIXME` in code — do it now or delete it
- Hardcoded URLs, thresholds, or timeouts — use config
- String-typed fields where enums exist
- Raw SQL outside of `db.py`
- `print()` for logging — use `logging` module
- Raw dicts crossing module boundaries — use Pydantic models
- `Any` type hints — be specific or use `Protocol`
- Mutable default arguments
- Global state — use dependency injection
- `Co-Authored-By` or `Generated by` lines in commit messages — never attribute commits to AI
- AI-generated comments like `// Added by Claude`, `# Generated`, `// AI-assisted` — code stands on its own
