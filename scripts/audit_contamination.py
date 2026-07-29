"""Audit the published eval traces for hint contamination. No API calls.

An agent that reads "[ACTIVE INCIDENT] — this source is implicated in ..." off a
table's description hasn't *found* the root cause; it has been *told*. That text
is exactly what CASCADE itself writes when it annotates a root cause, so a reset
bug between reps can silently hand the answer to the next run.

This script re-reads every raw trace and, for each run, reports whether any
CASCADE-authored annotation marker appeared in a **read**-tool result (search /
get_lineage / get_entities / list_schema_fields / ...) **before** that run wrote
its own annotation. A run is `CLEAN` only if it saw no such marker.

We ran it on our own published results and it found a real bug (see docs/eval.md):
`scripts/reset_graph.py` read a scenario key that no longer existed, so
root-cause descriptions were never cleaned between reps. 6 of 18 runs were
contaminated. The bug is fixed; the affected runs stay published and are
excluded from the headline number rather than quietly re-run.

Usage:  python scripts/audit_contamination.py            # table + summary
        python scripts/audit_contamination.py --verbose  # show the leaked text
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "demo" / "cached" / "runs"

# Tools that only READ the graph. A marker showing up in one of these results
# means the graph itself carried the hint.
READ_TOOLS = {"search", "get_lineage", "get_lineage_paths_between",
              "get_entities", "list_schema_fields", "get_dataset_queries"}

# Phrases CASCADE writes into descriptions when it annotates a root cause.
ANNOTATION_MARKERS = ["ACTIVE INCIDENT", "INCIDENT ALERT", "CRITICAL INCIDENT",
                      "INCIDENT POINTER", "implicated in", "root source of",
                      "ACTION REQUIRED", "Remediate:"]

# A leak is specifically an annotation sitting on a **ground-truth root-cause**
# asset — that is the answer the agent is supposed to derive. Incident metadata
# on the *affected* asset is not a leak: the failing table is given in the
# prompt, and an open incident on it is part of the premise.


def _text(step: dict) -> str:
    content = step.get("content") or step.get("text") or ""
    if isinstance(content, list):
        return " ".join(b.get("text", "") if isinstance(b, dict) else str(b)
                        for b in content)
    return str(content)


def _leaky_entities(body: str, root_urns: set[str]) -> list[tuple[str, str]]:
    """[(root_urn, marker)] for root-cause entities whose payload carries an
    annotation marker. Falls back to a proximity window when the result isn't
    parseable JSON."""
    found = []
    for urn in root_urns:
        at = body.find(urn)
        while at != -1:
            # The entity's own object, bounded by the NEXT dataset entity. (Not
            # the next `"urn"` key — every entity nests a platform.urn, which
            # would cut the window off before the description field.)
            nxt = body.find('urn:li:dataset:', at + len(urn))
            end = nxt if nxt != -1 else len(body)
            window = body[at:min(end, at + 6000)]
            hit = next((m for m in ANNOTATION_MARKERS if m in window), None)
            if hit:
                found.append((urn, hit))
                break
            at = body.find(urn, at + len(urn))
    return found


def audit_run(record: dict, root_urns: set[str]) -> dict:
    """Return {clean, leak_step, leak_tool, marker, snippet, own_annotation_step}."""
    pending, leak, own_annotation = None, None, None
    for i, step in enumerate(record.get("steps", [])):
        if step.get("kind") == "tool_use":
            if step.get("tool") == "update_description" and own_annotation is None:
                own_annotation = i
            pending = step.get("tool")
        elif step.get("kind") == "tool_result":
            if pending in READ_TOOLS and leak is None:
                body = _text(step)
                hits = _leaky_entities(body, root_urns)
                if hits:
                    urn, marker = hits[0]
                    at = body.find(urn)
                    leak = {"leak_step": i, "leak_tool": pending, "marker": marker,
                            "leak_urn": urn,
                            "snippet": body[at:at + 420]}
            pending = None
    return {"clean": leak is None, "own_annotation_step": own_annotation,
            **(leak or {})}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true",
                    help="print the leaked description text")
    args = ap.parse_args()

    paths = sorted(RUNS.glob("*/*.json"))
    if not paths:
        print(f"no traces under {RUNS}", file=sys.stderr)
        return 2

    clean = contaminated = 0
    print(f"{'run':32} {'verdict':14} {'passed':7} leaked-via")
    print("-" * 78)
    for p in paths:
        rec = json.loads(p.read_text())
        root_urns = set(rec.get("scenario", {}).get("expected_root_cause_urns") or [])
        res = audit_run(rec, root_urns)
        tag = f"{p.parent.name}/{p.stem}"
        if res["clean"]:
            clean += 1
            print(f"{tag:32} {'CLEAN':14} {str(rec.get('root_cause_correct')):7} -")
        else:
            contaminated += 1
            print(f"{tag:32} {'CONTAMINATED':14} {str(rec.get('root_cause_correct')):7} "
                  f"{res['leak_tool']} → \"{res['marker']}\"")
            if args.verbose:
                print(f"    …{res['snippet'].strip()[:300]}…\n")

    total = clean + contaminated
    print("-" * 78)
    print(f"{clean}/{total} runs verifiably hint-free; "
          f"{contaminated}/{total} saw a stale annotation before writing their own.")
    print("Headline numbers should be quoted over the CLEAN subset only.")
    return 1 if contaminated else 0


if __name__ == "__main__":
    sys.exit(main())
