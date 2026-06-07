# Example: refund-escalation-miss

A canonical failure scenario for the healing loop. A refund-denied customer threatens to escalate; the agent (running on the v1.1 production prompt) correctly denies the refund per the entitlements ledger but **fails to create an escalation**, which the `escalation_guard` evaluator catches.

## The ticket

A monthly-billing customer is past the 30-day refund window. They write back angry, asking for a manager. The deterministic `_compute_entitlements` ledger correctly returns `refund_eligible=False`. The agent's response politely denies the refund. The agent does **not** call `create_escalation` because the v1.1 prompt has no rule for "customer asks for manager → escalate."

## Expected failure

| Evaluator | Outcome | Failure summary |
|---|---|---|
| `escalation_guard` | fail | `ESCALATE_MISS · customer asked for manager, agent did not escalate` |
| `refund_guard` | pass | Refund correctly denied per policy |

## What the healing loop produces

1. **Cluster** — three identical `escalation_guard` failures trip an `ImprovementTrigger` with `trigger_reason=THRESHOLD_REPEATED_FAILURE`.
2. **Diagnose** — the diagnosis sub-agent calls `phoenix-mcp:get-spans` and `phoenix-mcp:get-span-annotations`, names the root cause: *"Agent prompt is missing the rule: escalate when the customer requests a human or manager."*
3. **Patch** — `proposal_generator` returns `PatchType.ESCALATION_RULE` with `proposed_change="Always escalate via create_escalation when the customer asks to speak to a manager, supervisor, or human."`
4. **Experiment** — baseline (v1.1) vs candidate (v1.2) on the regression set. `escalation_guard` pass rate goes from 0.10 to 0.98.
5. **Promote** — release-gate verdict: `PROMOTED`. The new prompt becomes production.

Run it: `curl -X POST http://localhost:8000/api/tickets -H "Content-Type: application/json" -d @ticket.json`
