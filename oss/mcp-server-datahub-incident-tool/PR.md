# PR: add `raise_incident` / `update_incident_status` mutation tools

**Repo:** acryldata/mcp-server-datahub

## Why
The MCP server's mutation tools currently cover tags, terms, owners, domains,
structured properties, and descriptions — but **not incidents**. DataHub has a
first-class native Incidents feature (`raiseIncident` / `updateIncidentStatus`
GraphQL mutations, surfaced on every asset's Incidents tab and wired into health
signals), yet an MCP agent cannot open or resolve one. That's the missing primitive
for "agents that do real work": an agent can *read* the graph to diagnose an issue
but can't *record* it where the team will see it.

## What
Adds two tools, gated behind the existing `TOOLS_IS_MUTATION_ENABLED` flag:
- `raise_incident(resource_urn, title, description, type, priority)` → incident URN
- `update_incident_status(urn, state, message)`

Both wrap existing GraphQL mutations using the server's current GraphQL client and
follow the existing tool-registration pattern (see `incident_tools.py`, hook into
`register_mutation_tools`).

## Validation
Exercised end-to-end against a local `datahub docker quickstart`: raising an
incident on a dataset returns a real `urn:li:incident:...` and it appears on the
dataset's Incidents tab; `update_incident_status(..., "RESOLVED")` resolves it.

## Notes
- Priority is validated against the `IncidentPriority` enum (CRITICAL/HIGH/MEDIUM/LOW).
- No new dependencies. Read-only default behavior is unchanged.

*(Contributed as part of the CASCADE project for the DataHub Agent Hackathon, which
uses exactly these tools to close the incident-response loop.)*
