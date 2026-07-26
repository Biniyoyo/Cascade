# Filing the two OSS contributions

## Section 1: PR to acryldata/mcp-server-datahub — incident write tools

A fully prepared, committed branch lives at:

`~/Desktop/others/oss-staging/mcp-server-datahub` (branch `add-incident-tools`, one commit on top of upstream `main`)

All 514 tests in `tests/test_mcp/` pass (including 15 new ones in `tests/test_mcp/tools/test_incidents.py`), and `ruff format --check`, `ruff check`, and `mypy` are all clean.

### Steps to file

1. **Fork the repo** (once): go to https://github.com/acryldata/mcp-server-datahub and click "Fork", or run:

   ```bash
   gh repo fork acryldata/mcp-server-datahub --clone=false
   ```

2. **Add your fork as a remote and push the branch** (replace `Biniyoyo` with your GitHub username if different):

   ```bash
   cd ~/Desktop/others/oss-staging/mcp-server-datahub
   git remote add fork https://github.com/Biniyoyo/mcp-server-datahub.git
   git push fork add-incident-tools
   ```

3. **Open the PR** against `acryldata/mcp-server-datahub` `main`:

   ```bash
   gh pr create \
     --repo acryldata/mcp-server-datahub \
     --head Biniyoyo:add-incident-tools \
     --title "feat(tools): add raise_incident / update_incident_status mutation tools (gated by TOOLS_IS_MUTATION_ENABLED)" \
     --body-file <(cat <<'EOF'
   [paste the PR body below]
   EOF
   )
   ```

   Or open it in the browser (GitHub will show a "Compare & pull request" banner after the push) and paste the title and body below.

### PR title

```
feat(tools): add raise_incident / update_incident_status mutation tools (gated by TOOLS_IS_MUTATION_ENABLED)
```

### PR body (ready to paste)

```markdown
## What

Adds two mutation tools that expose DataHub's native Incidents API to MCP agents:

- **`raise_incident(dataset_urn, title, description, priority=None)`** — raises a native incident on an asset via the `raiseIncident` GraphQL mutation (`type=OPERATIONAL`). The incident appears on the asset's Incidents tab and contributes to its health signals. `priority` is validated against `CRITICAL | HIGH | MEDIUM | LOW` and omitted from the mutation input when not provided. Returns the new incident URN.
- **`update_incident_status(incident_urn, state, message=None)`** — updates an incident via `updateIncidentStatus(urn, input: IncidentStatusInput)`. `state` is validated against `ACTIVE | RESOLVED`; `message` is optional.

Both tools are registered in `register_mutation_tools()` with the `mutation` tag and are only available when `TOOLS_IS_MUTATION_ENABLED=true` — the same gate as the existing tag/term/owner/domain mutations. No new environment variables or dependencies.

## Why

The server already gives agents everything they need to *diagnose* a data problem — search, lineage, schema, queries, assertions — but no way to *act* on the diagnosis. Its mutations stop at tags, terms, owners, domains, descriptions, and structured properties; DataHub's first-class incident primitive is not exposed. That means an agent that traces a broken pipeline through lineage cannot flag the affected asset for its human owners inside DataHub itself, and cannot close the incident after remediation. These two tools complete that loop with the platform's native incident lifecycle (raise → resolve/re-open), rather than approximating it with tags or description edits.

Mutation names and input shapes were verified against `datahub-graphql-core`'s `incident.graphql` (`raiseIncident(input: RaiseIncidentInput!): String`, `updateIncidentStatus(urn: String!, input: IncidentStatusInput!): Boolean`).

## Testing

- 15 new unit tests in `tests/test_mcp/tools/test_incidents.py`, mirroring the existing `test_tags.py` conventions (mocked `DataHubClient._graph.execute_graphql`, patched `graphql_helpers.get_datahub_client`): success paths, GraphQL variable shapes, enum validation and case normalization, omission of optional fields, empty-input `ValueError`s, mutation-returned-false and transport-exception `RuntimeError`s.
- Full suite: `uv run pytest tests/test_mcp/` — 514 passed.
- Lint/type: `make lint-check` clean (`ruff format --check`, `ruff check`, `mypy`).
- `tests/conftest.py` cross-repo compatibility shim extended to expose `tools.incidents` under the `datahub_integrations.mcp` namespace, matching the existing pattern for the other tool modules.
- README "Mutation Tools" section updated with both tools, matching the existing entry format.

## Breaking changes

None. Purely additive; tools are off by default (behind `TOOLS_IS_MUTATION_ENABLED`).

---

Built during the DataHub Agent Hackathon for the CASCADE project (autonomous data-incident responder): https://github.com/Biniyoyo/Cascade
```

<!-- Section 2 is appended below by the docs-skill PR agent. -->

---

## SECTION 2 — datahub-skills contribution

Contribution: the `datahub-incident-response` skill in
`oss/datahub-incident-response-skill/` (SKILL.md + README.md + references/report-template.md),
formatted to match the house style of github.com/datahub-project/datahub-skills.

### Step 1 — File the proposal issue FIRST

The skills repo is maintainer-curated; propose before PRing.

1. Go to https://github.com/datahub-project/datahub-skills/issues/new
2. Paste the proposal from `oss/ISSUE_DRAFTS.md`, part (a):
   - Title: `Proposal: datahub-incident-response skill — lineage-driven root cause, blast radius, and owner routing`
   - Body: as drafted (includes the honest datahub-quality overlap note — extension vs. new skill is the maintainer's call)
3. Note the issue number (referred to as `#<ISSUE>` below). If maintainers prefer
   extending datahub-quality instead, adapt before PRing.

### Step 2 — Fork and branch

```bash
gh repo fork datahub-project/datahub-skills --clone ~/Desktop/others/oss-staging/datahub-skills-fork
cd ~/Desktop/others/oss-staging/datahub-skills-fork
git checkout -b add-incident-response-skill
```

### Step 3 — Copy the skill in (repo layout: skills/<name>/)

```bash
mkdir -p skills/datahub-incident-response/references
cp ~/Desktop/others/CASCADE/oss/datahub-incident-response-skill/SKILL.md  skills/datahub-incident-response/
cp ~/Desktop/others/CASCADE/oss/datahub-incident-response-skill/README.md skills/datahub-incident-response/
cp ~/Desktop/others/CASCADE/oss/datahub-incident-response-skill/references/report-template.md skills/datahub-incident-response/references/
```

### Step 4 — Lint like CI does (prettier + markdownlint via pre-commit)

```bash
pip install pre-commit && pre-commit install
pre-commit run --all-files   # fix anything it flags before pushing
```

### Step 5 — Commit, push, open the PR

PR titles must be Conventional Commits (CI enforces this; the title becomes the
squash-merge commit). Use the `feat:` form of "Add datahub-incident-response skill":

```bash
git add skills/datahub-incident-response
git commit -m "feat: add datahub-incident-response skill"
git push -u origin add-incident-response-skill
gh pr create --repo datahub-project/datahub-skills \
  --title "feat: add datahub-incident-response skill" \
  --body-file /tmp/pr-body.md
```

### Ready-to-paste PR body (save as /tmp/pr-body.md)

```markdown
Closes #<ISSUE>

## What

Adds a `datahub-incident-response` skill: end-to-end response to a data-quality
incident — triage the affected column, find the root cause from upstream
column-level lineage, compute the downstream blast radius (dashboards called out),
route to owners, then write back: raise a native incident, append a pointer to the
root-cause asset's description, and create a guard assertion against recurrence.
Ends with an incident report + a ready-to-send owner alert
(`references/report-template.md`).

## Relationship to datahub-quality

Deliberately complementary, as discussed in #<ISSUE>: `datahub-quality`
investigates health and manages checks; this skill runs the composed,
act-and-remediate loop for a live incident. Happy to reshape it as a
datahub-quality extension if maintainers prefer.

## Format

Follows the existing catalog-interaction skill structure: frontmatter
(name/description/user-invocable/min-cli-version/allowed-tools), Multi-Agent
Compatibility, Not This Skill, Content Trust Boundaries (catalog descriptions are
treated as untrusted input — metadata-claimed URNs are verified via entity lookup
before being trusted), numbered steps with mandatory approval before writes, and
Common Mistakes / Red Flags / Remember.

## Validation

The workflow is extracted from a working agent exercised end to end against
`datahub docker quickstart` (real `raiseIncident` / `updateDescription` /
`upsertCustomAssertion` writes, verified in the UI):
https://github.com/Biniyoyo/Cascade — built for the DataHub Agent Hackathon.
```

### Step 6 — After opening

- Link the PR back on the proposal issue.
- CI runs prettier/markdownlint and the PR-title check; fix and re-push if red.
