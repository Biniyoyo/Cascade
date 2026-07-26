# Deploying CASCADE safely

CASCADE writes to your metadata graph (incidents, assertions, descriptions).
Roll it out like any automation that touches production: watch it first, then
let it propose, then let it act.

## 1. Observe — cached replay (zero risk)

The web app serves pre-recorded runs out of `demo/cached/` with no DataHub
connection and no API key. Explore what the agent does before it can do
anything. This is the default deployment: with `CASCADE_LIVE_CODE` unset,
every live endpoint degrades to this mode.

## 2. Propose — human confirms every write

```bash
python run_incident.py --propose          # CLI
# or POST /api/trigger with "propose": true
```

The agent investigates with real read access to the graph, but its three write
tools — `raise_incident`, `create_assertion`, `update_description` — are
intercepted by an SDK permission callback (`can_use_tool`): each intended call
is recorded verbatim into `proposed_writes` and denied. Nothing is written.
A human reviews the PROPOSED ACTIONS block and applies what they agree with.

**Start production rollout here.** Move to act mode only after the proposals
have been consistently correct on your own incidents.

## 3. Act — guardrailed writes

When you do let it act, the writes are bounded:

- **Allowlisted tools only** (`ALLOWED_TOOLS` in `cascade/agent.py`): three
  write tools, the rest read-only. The MCP server version is pinned.
- **Hard per-run spend cap** (`max_budget_usd`) plus global and per-session
  live-run caps in `app.py` (`CASCADE_LIVE_MAX`, `CASCADE_LIVE_PER_SESSION`).
- **Access-code gate** (`CASCADE_LIVE_CODE`) on every live endpoint.
- **Audit log**: every write the agent executed or proposed is appended to
  `audit/audit.jsonl` — timestamp, trigger, tool, exact arguments, URNs
  created, run cost.

## Wiring the webhook

`POST /api/trigger` accepts the assertion-failure shape
`{urn, column, symptom, priority}` (plus `code` and `propose`). Point your
DataHub assertion-failure webhook or Actions-framework consumer at it; keep
`"propose": true` until you trust the runs. Without an `ANTHROPIC_API_KEY`
the endpoint responds gracefully with the prompt it would have run.

## Honest limits

- The audit log is a local JSONL file — durable enough for review, not
  tamper-proof. Ship it somewhere append-only if that matters to you.
- Run caps are in-memory and reset on process restart.
- There is no automatic rollback for `update_description`; propose mode is
  the rollback story — don't approve what you can't live with.
