"""Fair A/B eval + cache builder.

BOTH arms use the SAME model (default: Haiku, `EVAL_MODEL`). Each scenario runs
`--reps` times (default 5); every run's full trace is saved to
demo/cached/runs/<scenario>_r<i>.json, an aggregate table is written to
docs/eval.md, and the canonical UI replay (demo/cached/<scenario>.json) is the
first PASSING rep (labelled; all raw runs are published either way).

Before every rep the graph is reset (scripts/reset_graph.py logic): active
incidents on the target are resolved and root-cause asset descriptions are
restored to a hint-free baseline, so no run benefits from a previous run's
annotations or from pre-existing "analyst note" hints.

Usage:
  python run_eval.py                      # all 3 scenarios × 5 reps, Haiku
  python run_eval.py --reps 1 null_spike  # quick single run
  python run_eval.py --model claude-sonnet-5 --reps 3
"""
import argparse
import json
import os
import re
from pathlib import Path


def _sanitize(text: str) -> str:
    """Strip any local absolute paths the harness may embed in tool output."""
    home = os.path.expanduser("~")
    text = text.replace(home, "/Users/demo")
    return re.sub(r"/Users/[A-Za-z0-9_.-]+/", "/Users/demo/", text)

import anyio

from cascade.agent import run_incident, DEV_MODEL
from cascade.no_context import run_no_context
from cascade.scenarios import SCENARIOS, SCENARIOS_BY_ID, incident_prompt
from cascade.grading import grade_root_cause, grade_completeness, grade_no_context
from scripts.reset_graph import reset_for_scenario

EVAL_MODEL = DEV_MODEL  # same model BOTH arms — fairness is the point
CACHE_DIR = Path(__file__).resolve().parent / "demo" / "cached"
RUNS_DIR = CACHE_DIR / "runs"
EVAL_MD = Path(__file__).resolve().parent / "docs" / "eval.md"


async def run_rep(scenario: dict, model: str, rep: int) -> dict:
    print(f"\n--- {scenario['id']} rep {rep} [{model}] ---")
    reset_for_scenario(scenario)

    no_ctx = run_no_context(scenario, model=model)
    result = await run_incident(incident_prompt(scenario), max_budget_usd=1.0,
                                model=model)

    record = {
        "scenario": scenario,
        "model": model,
        "rep": rep,
        "final_text": result["final_text"],
        "steps": result["steps"],
        "tools_used": result["tools_used"],
        "incident_urn": result["incident_urn"],
        "assertion_urn": result.get("assertion_urn"),
        "cost_usd": result["cost_usd"],
        "no_context": {"text": no_ctx["text"], "model": no_ctx["model"]},
    }
    record["root_cause_correct"] = grade_root_cause(
        record["steps"], record["final_text"], scenario)
    record.update(grade_completeness(record))
    record["no_context"]["named_root_cause"] = grade_no_context(
        no_ctx["text"], scenario)
    record["grading"] = ("strict structural: update_description write must target "
                         "expected_root_cause_urn; incident+assertion URNs required "
                         "for completeness; same model both arms")

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / f"{scenario['id']}_r{rep}.json").write_text(
        _sanitize(json.dumps(record, indent=2, default=str)))
    ok = record["root_cause_correct"]
    print(f"    root cause {'PASS' if ok else 'MISS'} | incident={bool(record['incident_urn'])} "
          f"assertion={bool(record['assertion_urn'])} | no-ctx named={record['no_context']['named_root_cause']} "
          f"| ${record['cost_usd']:.3f}")
    return record


def write_eval_md(all_runs: dict, model: str):
    lines = [
        "# CASCADE eval — fair A/B, raw results\n",
        f"**Model (both arms): `{model}`** · strict structural grading "
        "(root-cause `update_description` write must target the ground-truth URN; "
        "incident + assertion URNs required for completeness). Graph reset to a "
        "hint-free baseline before every rep (`scripts/reset_graph.py`).\n",
        "| scenario | with DataHub (root cause) | incident | assertion | without DataHub | mean cost |",
        "|---|---|---|---|---|---|",
    ]
    tot_pass = tot_n = tot_nc = 0
    for sid, runs in all_runs.items():
        n = len(runs)
        p = sum(r["root_cause_correct"] for r in runs)
        inc = sum(r["incident_created"] for r in runs)
        asr = sum(r["assertion_created"] for r in runs)
        nc = sum(r["no_context"]["named_root_cause"] for r in runs)
        cost = sum(r["cost_usd"] for r in runs) / max(n, 1)
        tot_pass += p; tot_n += n; tot_nc += nc
        lines.append(f"| {sid} | **{p}/{n}** | {inc}/{n} | {asr}/{n} | {nc}/{n} | ${cost:.2f} |")
    lines += [
        f"\n**Aggregate: {tot_pass}/{tot_n} correct root causes with DataHub vs "
        f"{tot_nc}/{tot_n} without — same model, same prompts.**\n",
        "Raw per-run traces: `demo/cached/runs/*.json`. The war-room replay uses the "
        "first passing rep per scenario (labelled in each cached file); re-score "
        "everything offline with `python scripts/regrade.py`.\n",
    ]
    EVAL_MD.parent.mkdir(exist_ok=True)
    EVAL_MD.write_text("\n".join(lines))
    print(f"\nwrote {EVAL_MD}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scenarios", nargs="*", help="scenario ids (default: all)")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--model", default=EVAL_MODEL)
    args = ap.parse_args()

    scenarios = ([SCENARIOS_BY_ID[i] for i in args.scenarios]
                 if args.scenarios else SCENARIOS)
    all_runs, total_cost = {}, 0.0
    for sc in scenarios:
        runs = []
        for rep in range(1, args.reps + 1):
            r = await run_rep(sc, args.model, rep)
            runs.append(r)
            total_cost += r["cost_usd"]
        all_runs[sc["id"]] = runs
        canonical = next((r for r in runs if r["root_cause_correct"]), runs[0])
        canonical = dict(canonical)
        canonical["canonical_note"] = (f"showcase replay = rep {canonical['rep']} "
                                       f"of {len(runs)}; all reps in demo/cached/runs/")
        (CACHE_DIR / f"{sc['id']}.json").write_text(
            _sanitize(json.dumps(canonical, indent=2, default=str)))

    write_eval_md(all_runs, args.model)
    print(f"\nTOTAL API COST THIS EVAL: ${total_cost:.2f}")


if __name__ == "__main__":
    anyio.run(main)
