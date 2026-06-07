# Example: citation-hallucination

A canonical failure scenario for `citation_presence` and the `groundedness` LLM judge. The agent answers a billing-policy question without consulting the policy docs (i.e., without calling `search_policy`), so its answer is correct-sounding but ungrounded — there's no `POL-BIL-*` ID in the response.

## The ticket

A small-business customer asks about billing-cycle proration after a mid-month upgrade. The v1.1 prompt doesn't aggressively require `search_policy` for billing questions, so on some seeds the agent answers from training-data memory. The answer is plausible but uncitable.

## Expected failure

| Evaluator | Outcome | Failure summary |
|---|---|---|
| `citation_presence` | fail | `RETRIEVAL_MISS · response cites no policy IDs` |
| `groundedness` (LLM judge) | fail | `UNSUPPORTED_CLAIM · claims about proration not backed by tool output` |

## What the healing loop produces

1. **Cluster** — three identical `citation_presence` failures cluster on `failure_key=fk-citation-miss-billing`.
2. **Diagnose** — the diagnosis sub-agent reads back the failing spans and notes that the agent skipped `search_policy` in all three failing runs.
3. **Patch** — `proposal_generator` returns `PatchType.PROMPT_CONSTRAINT` with `proposed_change="Before answering any billing, refund, privacy, or escalation question, you MUST call search_policy and cite the returned POL-* identifier in your response."`
4. **Experiment** — baseline vs candidate on the regression set. `citation_presence` pass rate goes from 0.10 to 0.98; `groundedness` pass rate goes from 0.65 to 0.93.
5. **Promote** — release-gate verdict: `PROMOTED`.

Run it: `curl -X POST http://localhost:8000/api/tickets -H "Content-Type: application/json" -d @ticket.json`
