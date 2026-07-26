# CASCADE — autonomous data-incident response, grounded in DataHub

> **CASCADE uses DataHub's Context Graph via the [MCP Server](https://github.com/acryldata/mcp-server-datahub) to read lineage, schema, and ownership — and writes back via DataHub's native Incidents API, plus data-quality assertions and owner routing.** It is an AI agent that does real on-call work: when a data-quality check fails, CASCADE finds the root cause, maps the blast radius, raises a real incident, and remediates — autonomously.

**Track:** Agents That Do Real Work · **Built with:** DataHub MCP Server, DataHub native Incidents API, Claude Agent SDK · Apache-2.0.

---

## The problem

A column silently breaks at 2 a.m. Which dashboards are now wrong? What upstream change caused it? Who owns the fix? Today an engineer answers these by hand — reading lineage, clicking through the catalog, guessing — for hours, while wrong numbers reach executives.

## The thesis CASCADE proves

> *"This is not an LLM problem. It is a context problem. Without context, you're paying your agents to guess."* — DataHub

CASCADE is a live proof of that. Give the **same model** only the symptom and it guesses. Give it **DataHub's lineage graph** and it pinpoints the exact root cause in one or two hops, scopes the real blast radius, and acts. **The intelligence is in the context, not the parameters** — CASCADE is model-agnostic by design (runs on Claude; the MCP interface is model-neutral).

## What CASCADE does (autonomously)

1. **Triage** — reads the failing dataset's schema (`list_schema_fields`) to locate the affected column.
2. **Root cause** — traces upstream **column-level lineage** (`get_lineage`, `get_lineage_paths_between`) to the exact upstream asset/column responsible — with evidence, not guesses.
3. **Blast radius** — traces downstream (`get_lineage`) to enumerate every impacted dashboard, chart, and dataset.
4. **Route** — reads ownership (`get_owners`) to route the incident to the responsible team/person.
5. **Write back** — raises a **native DataHub incident**, updates the root-cause asset, and creates a **data-quality assertion** to prevent recurrence.
6. **Alert** — drafts a ready-to-send owner notification with root cause, blast radius, and the fix.

## How CASCADE uses DataHub (the heart of the project)

| DataHub capability | CASCADE call | Why it matters |
|---|---|---|
| Context graph search | `search` | Locate assets in the graph |
| Schema | `list_schema_fields` | Find the failing column, its type, NOT NULL / PII status |
| **Lineage (column-level)** | `get_lineage`, `get_lineage_paths_between` | **Root cause + blast radius — the core reasoning substrate** |
| Consumers | `get_dataset_queries` | See who actually queries the data |
| Ownership | `get_owners` | Route the incident to the right team |
| **Native Incidents API** | `raiseIncident` (our tool) | **Write a real incident back — closing the loop** |
| Descriptions | `update_description` | Annotate the root-cause asset |
| **Data-quality assertions** | `upsertCustomAssertion` (our tool) | **Remediate: guard against recurrence** |

CASCADE reads **and writes** the graph — the "contribute back" behavior the hackathon explicitly rewards.

## Architecture

```
  data-quality check fails
          │
          ▼
   ┌──────────────┐   MCP: search, get_lineage, get_lineage_paths_between,
   │   CASCADE     │──▶ list_schema_fields, get_owners  ──▶  DataHub Context Graph
   │  (agent loop) │◀──                                       (local Quickstart)
   └──────────────┘
          │ raise native incident · update description · create assertion · route owner
          ▼
   DataHub Incidents tab + health signals + guard assertion  ◀── the loop, closed
```

## Why the native-incident write-back is novel

The DataHub **MCP server exposes no incident-writing tool** — its writes stop at tags, terms, owners, and descriptions. CASCADE adds `raise_incident` (wrapping DataHub's native `raiseIncident` GraphQL mutation) and `create_assertion` (via `upsertCustomAssertion`). So CASCADE **closes a loop DataHub's own agent stack cannot today** — and we contribute those tools back (see `oss/`).

## Quickstart (runs from a clean clone)

```bash
# 1. DataHub (Docker) + sample lineage
python3 -m pip install 'acryl-datahub[datahub-rest]'
datahub docker quickstart                         # UI :9002 (datahub/datahub), GMS :8080
datahub datapack load showcase-ecommerce --force  # 1049 entities with lineage

# 2. CASCADE
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env        # set ANTHROPIC_API_KEY (for live runs); DataHub needs no token locally

# 3a. Run the web app (cached demo works with NO keys/DataHub)
uvicorn app:app --port 8100        # open http://localhost:8100

# 3b. Or run the agent on one incident (live)
python run_incident.py

# 3c. Or the eval across 3 scenarios (captures cached demo content)
python run_eval.py
```

## The app

A judge-facing **"incident war room"** (`http://localhost:8100`):
- Pick an incident → watch CASCADE's reasoning replay (real tool calls),
- see the **root cause**, **blast-radius map**, **native incident**, **guard assertion**, and **owner routing**,
- and the **Context A/B**: the same model *without* DataHub (guessing) vs *with* DataHub (correct).

The 3 scenarios are **pre-seeded and cached**, so the app is fully explorable at **$0** and needs no DataHub to serve. A gated, budget-capped **"Run it live"** button does a real run for judges (access code + global/per-session caps + graceful fallback).

## Reliability

`run_eval.py` is a small eval harness: it injects 3 known-root-cause incidents and checks CASCADE finds the correct upstream cause. **3/3** on the showcase-ecommerce graph. CASCADE also detects and **refuses injected "incident" text** planted in metadata descriptions (verifies via `get_entities` before trusting it).

## AI + cost

- Model: Claude (Haiku for live/dev ~**$0.13/run**; Sonnet for the recorded showcase). Model-agnostic via MCP.
- Spend-capped per run (`max_budget_usd`) and per deployment (global + per-session caps).

## Open-source contributions (see `oss/`)

- **`raise_incident` / `update_incident_status` MCP tool** for [mcp-server-datahub](https://github.com/acryldata/mcp-server-datahub) — the incident-write primitive the server lacks.
- **`datahub-incident-response` Skill** for [datahub-skills](https://github.com/datahub-project/datahub-skills) — packages CASCADE's detect → trace → blast-radius → raise-incident → route methodology for any agent.

## Repo map

| Path | What |
|---|---|
| `cascade/agent.py` | the agent (Claude Agent SDK + DataHub MCP + CASCADE tools) |
| `cascade/tools.py` | in-process MCP tools: `raise_incident`, `create_assertion`, `get_owners` |
| `cascade/datahub_incidents.py` | native Incidents + assertions + ownership (GraphQL) |
| `cascade/prompts.py` | the incident-response procedure |
| `cascade/scenarios.py` · `run_eval.py` | the 3 scenarios + eval/cache builder |
| `app.py` · `frontend/index.html` | the war-room web app |
| `oss/` | the open-source contributions |
| `examples/` | sample outputs (incident reports, alerts) |
```
