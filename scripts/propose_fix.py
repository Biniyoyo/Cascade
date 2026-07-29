"""Generate a reviewable remediation artifact from a recorded investigation.

Completes the loop:  detect → explain → map impact → route owner → open incident
→ **propose repair** → verify guard.

From a cached trace this produces, deterministically (no LLM call, no cost):
  * a **dbt schema test** (`not_null` / uniqueness) for the failing column, and
  * a **patch proposal** markdown tied to the identified root-cause lineage and
    the routed owner — explicitly marked as requiring human review/approval.

Nothing is auto-applied anywhere: the artifact is a proposal for the owner to
review, matching CASCADE's observe → propose → act rollout philosophy.

Usage:
  python scripts/propose_fix.py                 # all cached scenarios
  python scripts/propose_fix.py null_spike      # one
Artifacts land in examples/remediation/<scenario>/.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cascade.scenarios import SCENARIOS_BY_ID  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "demo" / "cached"
OUT = ROOT / "examples" / "remediation"


def _model_name(urn: str) -> str:
    m = re.search(r",([\w.$]+),PROD\)", urn)
    return (m.group(1).split(".")[-1] if m else "unknown").lower()


def _column(scenario: dict) -> str:
    """First backticked identifier in the symptom that isn't the table itself."""
    affected = _model_name(scenario["affected_urn"])
    for tok in re.findall(r"`(\w+)`", scenario["symptom"]):
        if tok.lower() != affected:
            return tok
    return ""  # no column named in the symptom (e.g. a row-level fan-out)


def _annotated_urn(trace: dict) -> str:
    """The root-cause URN the agent actually annotated in this run.

    Sourced from the trace rather than from the scenario's ground truth, so the
    proposal describes what the agent concluded — not what we know the answer
    to be.
    """
    for step in trace.get("steps", []):
        if step.get("kind") == "tool_use" and step.get("tool") == "update_description":
            urn = (step.get("input") or {}).get("entity_urn")
            if urn and urn != trace.get("scenario", {}).get("affected_urn"):
                return urn
    return ""


def _owners(trace: dict) -> list[str]:
    """Owner names from the trace's get_owners result, technical/steward first."""
    pending, names = None, []
    for step in trace.get("steps", []):
        if step.get("kind") == "tool_use":
            pending = step.get("tool")
            continue
        if step.get("kind") == "tool_result" and pending == "get_owners":
            content = step.get("content") or step.get("text") or ""
            text = (" ".join(b.get("text", "") for b in content)
                    if isinstance(content, list) else str(content))
            for name, kind in re.findall(r"^- (.+?) \((\w+),", text, re.M):
                if kind in ("technical_owner", "data_steward") and name not in names:
                    names.append(name)
            if names:
                return names
        pending = None
    return names


def generate(sid: str) -> Path:
    scenario = SCENARIOS_BY_ID[sid]
    trace = json.loads((CACHE / f"{sid}.json").read_text())
    col = _column(scenario)
    affected_model = _model_name(scenario["affected_urn"])
    root_urn = _annotated_urn(trace)
    root_model = _model_name(root_urn)
    dupe_case = "duplicat" in scenario["symptom"].lower()

    out_dir = OUT / sid
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. dbt schema test — the guard, expressed in the repo the owner already runs
    if dupe_case:
        # The failure is duplicated rows, not a null column — uniqueness on the
        # grain is the guard. Only add a column test if the symptom named one.
        col_block = f"""    columns:
      - name: {col}
        tests: [not_null]
""" if col else ""
        test_yaml = f"""# PROPOSED by CASCADE — requires human review before merge
# Guard for: {scenario['name']}
version: 2
models:
  - name: {affected_model}
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [order_id, line_item_id]
          name: cascade_guard_{affected_model}_no_fanout_duplicates
{col_block}"""
    else:
        test_yaml = f"""# PROPOSED by CASCADE — requires human review before merge
# Guard for: {scenario['name']}
version: 2
models:
  - name: {affected_model}
    columns:
      - name: {col}
        tests:
          - not_null:
              name: cascade_guard_{affected_model}_{col}_not_null
"""
    (out_dir / f"schema_test_{affected_model}.yml").write_text(test_yaml)

    # 2. patch proposal for the owner — taken from the graph's ownership aspect
    # as returned to the agent, not regexed out of the agent's prose.
    owners = _owners(trace)
    owner_line = (f"**Proposed reviewer/owner:** {', '.join(owners[:3])} "
                  "(from DataHub ownership)\n\n" if owners else "")
    proposal = f"""# Remediation proposal — {scenario['name']}

> Generated by CASCADE from the recorded investigation (`demo/cached/{sid}.json`).
> **Status: PROPOSAL — requires human review and approval. Nothing is auto-applied.**

{owner_line}## What broke (evidence-backed likely cause)

- Affected: `{scenario["affected_urn"]}`{f" (column `{col}`)" if col else ""}
- Likely root cause asset (from column-level lineage): `{root_urn or "n/a"}`
- Native incident: `{trace.get('incident_urn')}`
- Guard assertion (DataHub): `{trace.get('assertion_urn')}`

## Proposed repair steps (for the owner to verify & apply)

1. Verify the upstream load for `{root_model}`: row counts vs previous run, join-key
   integrity, and the load job's run logs.
2. Apply the dbt schema test in `schema_test_{affected_model}.yml` to the model's
   `.yml` so the failure mode is caught at build time — in addition to the DataHub
   guard assertion CASCADE already registered.
3. Backfill/refresh `{affected_model}` after the upstream fix, then resolve the
   DataHub incident.

## Why this is a proposal, not an auto-fix

Lineage identifies the fault domain; confirming the exact defect needs run logs /
row counts that live outside the catalog. CASCADE therefore contains the incident
(native incident + guard + owner alert) and hands the repair decision to a human.
"""
    (out_dir / "PROPOSAL.md").write_text(proposal)
    return out_dir


if __name__ == "__main__":
    which = sys.argv[1:] or [s for s in SCENARIOS_BY_ID
                             if (CACHE / f"{s}.json").exists()]
    for sid in which:
        print("generated:", generate(sid))
