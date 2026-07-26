# GitHub Issue Drafts — CASCADE upstream contributions

Ready-to-paste issue text. Part (a) is the issue-first proposal for the skills repo;
part (b) is five self-contained issues from real friction hit while building CASCADE
(an autonomous incident-response agent on DataHub, github.com/Biniyoyo/Cascade).

---

## (a) Skill proposal — file against `datahub-project/datahub-skills`

**Title:** Proposal: datahub-incident-response skill — lineage-driven root cause, blast radius, and owner routing

**Body:**

### What

A new catalog-interaction skill that runs a data-quality incident end to end:

1. **Triage** — read the failing dataset's schema, locate the affected column (type, nullability, PII)
2. **Root cause** — trace upstream *column-level* lineage to the responsible asset; any URN claimed in catalog descriptions is verified via entity lookup before being trusted (catalog text is treated as untrusted input — a prompt-injection defense)
3. **Blast radius** — downstream multi-hop lineage, dashboards/charts called out explicitly
4. **Route** — owners of the affected and root-cause assets; missing owners flagged as governance gaps
5. **Write back** — raise a native incident (SYMPTOM/ROOT CAUSE/BLAST RADIUS/FIX/OWNER body), append a pointer to the root-cause asset's description, and create a guard assertion on the failing column
6. **Report** — incident report plus a ready-to-send owner alert

The skill follows the repo's existing structure (frontmatter, Multi-Agent Compatibility, Not This Skill, Content Trust Boundaries, numbered steps with mandatory approval before writes, Common Mistakes / Red Flags / Remember) and ships with `references/report-template.md`.

### Overlap with datahub-quality (honest note)

`datahub-quality` already covers raising incidents and creating assertions as individual operations, and is the right skill for diagnosing health and configuring checks. This proposal covers the *composed, closed-loop response to a live incident* — lineage-driven root cause, blast radius, owner routing, and all three write-backs in one pass, ending in an owner alert. That could reasonably live as either:

- an **extension of datahub-quality** (a "respond to an incident" workflow section), or
- a **separate skill** (as proposed), keeping quality focused on checks and health.

Maintainer's call — happy to implement either shape. Draft implementation exists and was exercised end to end against `datahub docker quickstart` as part of the CASCADE agent (github.com/Biniyoyo/Cascade).

### Why now

Agents can already read the graph well; what's missing in the skill catalog is the act-and-remediate half — recording the diagnosis where the team will see it (Incidents tab, health signals) and guarding against recurrence.

---

## (b) Friction issues

### Issue 1 — MCP server has no incident-write tools

**Repo:** `acryldata/mcp-server-datahub`

**Title:** Mutation tools cover tags/terms/owners/descriptions but not incidents — agents cannot raise or resolve incidents

**Body:**

**What we did:** Built an incident-response agent on top of the MCP server (mutations enabled via `TOOLS_IS_MUTATION_ENABLED=true`). After diagnosing a root cause from lineage, the agent needed to open a native DataHub incident on the affected dataset and later resolve it.

**Expected:** Incident tools alongside the existing light mutations — something like `raise_incident(resource_urn, title, description, type, priority)` and `update_incident_status(urn, state, message)`, wrapping the existing `raiseIncident` / `updateIncidentStatus` GraphQL mutations.

**Actual:** No incident tools exist. The agent can *diagnose* an issue but cannot *record* it where the team will see it (the asset's Incidents tab, health signals). We had to ship a sidecar GraphQL client exposing these as custom MCP tools.

**Suggestion:** Add both tools behind the existing `TOOLS_IS_MUTATION_ENABLED` flag, following the current tool-registration pattern. We have a working reference implementation (validated against `datahub docker quickstart`: returned real `urn:li:incident:...` URNs that appear in the UI) and are happy to PR it.

---

### Issue 2 — get_lineage responses can exceed 100k characters; no agent-friendly pagination defaults

**Repo:** `acryldata/mcp-server-datahub`

**Title:** get_lineage can return >100k-character responses — needs pagination/size defaults suitable for agent contexts

**Body:**

**What we did:** Called `get_lineage` with multiple hops on a moderately connected dataset (downstream blast-radius traversal) from an LLM agent.

**Expected:** A bounded response — a default page size / max-entities cap tuned for LLM context windows, with truncation metadata ("N of M entities returned, use offset/next_page to continue") so the agent can decide whether to fetch more.

**Actual:** A single response exceeding 100,000 characters. That either blows a large fraction of the model's context in one tool result or gets truncated mid-JSON by the client, and there is no obvious knob for "give me the first 50 edges plus a total count."

**Suggestion:** Default `get_lineage` to a conservative result cap with explicit `total`/`truncated` fields and an offset or cursor parameter. Even a documented `max_entities` argument would let agent authors keep tool results bounded. (For comparison, the `datahub lineage` CLI defaults to `--count 100` and reports capping in its summary — the MCP tool would benefit from the same behavior.)

---

### Issue 3 — Incident `priority`: GraphQL enum vs. integer aspect model produces an unhelpful coercion error

**Repo:** `datahub-project/datahub`

**Title:** raiseIncident priority is an enum, but the aspect model documents integers 0-3 — integer input fails with an opaque coercion error

**Body:**

**What we did:** During our incident + custom-assertion write-back path, we called the `raiseIncident` mutation with `"priority": 2` (an integer), because the underlying aspect model (`com.linkedin.incident.IncidentInfo.priority`) is `optional int` documented as "0 - CRITICAL, 1 - HIGH, 2 - MED, 3 - LOW" — and even carries the comment "(We probably should have modeled as an enum)".

**Expected:** Either the integer to be coerced to the corresponding `IncidentPriority` enum value, or a clear error like: `priority must be one of CRITICAL | HIGH | MEDIUM | LOW (got 2)`.

**Actual:** An unhelpful GraphQL validation/coercion error that names neither the allowed enum values nor the int-vs-enum mismatch, leaving the caller to diff the schema by hand. The enum/int split between the GraphQL layer (`IncidentPriority`) and the stored aspect (int 0-3, where *lower* is *more* severe) is an easy trap for anyone who has looked at the aspect model or older REST examples first.

**Suggestion:** Improve the error message to list the accepted enum values (ideally noting the int mapping), and/or accept the documented integers as aliases. A docs note on the mapping (0=CRITICAL … 3=LOW, i.e. inverted from intuition) would also help.

---

### Issue 4 — With auth disabled on quickstart, GraphQL writes need Authorization + X-DataHub-Actor headers to attribute properly (undocumented)

**Repo:** `datahub-project/datahub`

**Title:** Document write attribution on auth-disabled deployments: Authorization + X-DataHub-Actor headers required for writes to be attributed

**Body:**

**What we did:** Ran `datahub docker quickstart` with metadata-service authentication disabled (the quickstart default) and issued GraphQL writes (`raiseIncident`, `updateDescription`, `upsertCustomAssertion`) directly against `GMS/api/graphql` from a service.

**Expected:** With auth disabled, plain unauthenticated POSTs to work and be attributed to some documented default actor — with the mechanism for overriding the actor documented.

**Actual:** Writes only behaved properly for us when we sent **both** an `Authorization: Bearer <any-token>` header **and** an `X-DataHub-Actor: urn:li:corpuser:...` header; without them, writes are attributed to a system/unknown actor (or rejected, depending on path). Neither the need for a placeholder bearer token on an auth-disabled instance nor the `X-DataHub-Actor` header is documented in the authentication or GraphQL API docs — we found the combination by reading server code and experimenting.

**Suggestion:** Document the attribution behavior for auth-disabled deployments (what actor writes default to, and that `X-DataHub-Actor` overrides it), and clarify whether the placeholder `Authorization` header is intentionally required. A short "calling the API on quickstart" docs section would save integrators real time.

---

### Issue 5 — API-created custom assertions surface less clearly in the UI health summary than native ones

**Repo:** `datahub-project/datahub`

**Title:** Custom assertions (upsertCustomAssertion + reportAssertionResult) are under-represented in the dataset health summary vs. native assertions

**Body:**

**What we did:** As automated incident remediation, we registered a guard assertion on a failing column via `upsertCustomAssertion` and pushed results via `reportAssertionResult`, then checked the dataset in the UI to confirm the guard is visible to the owning team.

**Expected:** The custom assertion to carry the same visual weight as a native assertion — counted in the dataset's health badge/summary and clearly listed alongside native checks on the Quality/Assertions surface, so an on-call engineer notices it exists.

**Actual:** The assertion exists and is queryable via the API, but in the UI it surfaces much less prominently than native assertions: the health summary emphasis is on native assertion status, and the custom assertion is easy to miss unless you already know to look for it. For teams using DataHub as the pane of glass, an API-created guard that nobody sees loses most of its value.

**Suggestion:** Treat custom assertions as first-class in the health summary (same counting and badge behavior as native, given they report results through `reportAssertionResult`), or at minimum document the intended difference in visibility.
