# PhoenixLoop — Worked examples

Three curated failure → diagnosis → patch scenarios that exercise the full healing loop. Each subdirectory has:

- `README.md` — the scenario in plain English: the ticket body, the expected failure, the evaluator that catches it, what the healing loop produces.
- `ticket.json` — the exact `SupportTicket` payload, ready to `POST /api/tickets`.

## Index

| Scenario | Failing evaluator | Patch type |
|---|---|---|
| [`refund-escalation-miss/`](./refund-escalation-miss/) | `escalation_guard` | `escalation_rule` |
| [`citation-hallucination/`](./citation-hallucination/) | `citation_presence` + `groundedness` | `prompt_constraint` |
| [`privacy-leak-canary/`](./privacy-leak-canary/) | `privacy_guard` + `safety_privacy` | `prompt_constraint` |

## How to run one

```bash
# Boot the stack (if you haven't already)
docker compose up --build

# In a separate terminal:
curl -X POST http://localhost:8000/api/tickets \
  -H "Content-Type: application/json" \
  -d @examples/refund-escalation-miss/ticket.json

# Then run the agent on the new ticket:
curl -X POST http://localhost:8000/api/tickets/example-refund-escalate-miss-001/run

# Watch the trigger appear on /healing/improvements.
```

The privacy-leak example uses a Visa test-card number (`4111 1111 1111 1247`) that is **publicly documented as a non-card sandbox identifier**. It is not a real card. Do not paste real cardholder data into any ticket body during testing.
