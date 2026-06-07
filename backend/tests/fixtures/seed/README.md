# Seed fixtures (`LIGHTWEIGHT_DEMO=true`)

Hand-curated JSON snapshots of a complete healing-loop run. The auto-seed path
reads these when `LIGHTWEIGHT_DEMO=true` and skips every Gemini call — pure-UI
iteration becomes token-free.

**The fixtures are intentionally static.** Live mode never writes here. To
refresh them from a real run, invoke:

```
python scripts/capture_fixtures.py --from-last-seed
```

That script reads the most recent seeded run from the DB and overwrites the
files below. It is opt-in only — nothing on the boot path touches it.

## Files

| File | Holds |
|---|---|
| `tickets.json` | 6 SupportTicket records (4 successful demos + 2 fail-twins). |
| `agent_runs.json` | One AgentRun per ticket, with response_json and tool_calls. |
| `eval_results.json` | EvalResults for every run; two share a CitationPresence failure_key. |
| `improvement_trigger.json` | The aggregator's trigger created from the failure cluster. |
| `diagnosis.json` | DiagnosisResult JSON shaped for the UI's diagnosis panel. |
| `patch_proposal.json` | The candidate prompt patch. |
| `regression_examples.json` | Two regression examples linked to the trigger. |
| `prompt_version_candidate.json` | The candidate PromptVersion row written by the seed. |
| `experiment.json` | Completed ExperimentRecord with non-zero baseline + candidate scores. |
| `release_gate.json` | The ReleaseGateDecision the gate emitted. |

Edit by hand; commit the diff.
