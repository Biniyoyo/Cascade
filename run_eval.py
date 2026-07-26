"""Gate-3 eval + cache builder.

Runs every scenario once through CASCADE, saves the full trace to demo/cached/<id>.json
(the UI replays these for free), and checks whether CASCADE identified the expected
root cause. One paid run per scenario (Haiku ~ $0.15 each).

Usage:
  python run_eval.py            # run all scenarios
  python run_eval.py null_spike # run one
"""
import json
import sys
import time
from pathlib import Path

import anyio

from cascade.agent import run_incident, FINAL_MODEL
from cascade.no_context import run_no_context
from cascade.scenarios import SCENARIOS, SCENARIOS_BY_ID, incident_prompt
from cascade import datahub_incidents as di

CACHE_DIR = Path(__file__).resolve().parent / "demo" / "cached"


def _reset_incidents(urn: str):
    """Resolve any ACTIVE incidents on the target so each run starts clean."""
    try:
        for i in di.list_incidents(urn):
            if i["status"]["state"] == "ACTIVE":
                di.resolve_incident(i["urn"], "reset before eval run")
    except Exception:
        pass


async def run_one(scenario: dict) -> dict:
    print("\n" + "=" * 72)
    print(f"SCENARIO: {scenario['id']} — {scenario['name']}")
    print("=" * 72)
    _reset_incidents(scenario["affected_urn"])

    # A/B: the SAME model WITHOUT DataHub context (must guess), then WITH context.
    print("  [without DataHub] guessing…")
    no_ctx = run_no_context(scenario)
    # Cached showcase content uses the premium model for crisp, complete results.
    result = await run_incident(incident_prompt(scenario), max_budget_usd=2.5,
                                model=FINAL_MODEL)

    got = (result["final_text"] or "").lower()
    passed = scenario["expected_root_cause"].lower() in got
    # did the blind guess actually name the true root cause? (usually not)
    guess_hit = scenario["expected_root_cause"].lower() in no_ctx["text"].lower()
    record = {
        "scenario": scenario,
        "final_text": result["final_text"],
        "steps": result["steps"],
        "tools_used": result["tools_used"],
        "incident_urn": result["incident_urn"],
        "assertion_urn": result.get("assertion_urn"),
        "cost_usd": result["cost_usd"],
        "root_cause_correct": passed,
        "no_context": {"text": no_ctx["text"], "named_root_cause": guess_hit},
    }
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{scenario['id']}.json").write_text(json.dumps(record, indent=2, default=str))
    print(f"\n  A/B root cause '{scenario['expected_root_cause']}': "
          f"without DataHub={'named it' if guess_hit else 'guessed/missed'} | "
          f"with DataHub={'✅ FOUND' if passed else '❌ MISSING'}")
    print(f"  incident={result['incident_urn']} assertion={result.get('assertion_urn')} "
          f"| cost=${result['cost_usd']:.4f}")
    return record


async def main():
    which = sys.argv[1:] if len(sys.argv) > 1 else None
    scenarios = [SCENARIOS_BY_ID[i] for i in which] if which else SCENARIOS
    results = []
    for sc in scenarios:
        results.append(await run_one(sc))

    n = len(results)
    ok = sum(r["root_cause_correct"] for r in results)
    total_cost = sum(r["cost_usd"] for r in results)
    print("\n" + "#" * 72)
    print(f"EVAL: {ok}/{n} correct root cause  |  total cost ${total_cost:.4f}")
    for r in results:
        s = r["scenario"]
        print(f"  {'✅' if r['root_cause_correct'] else '❌'} {s['id']:16s} "
              f"expected={s['expected_root_cause']:12s} incident={r['incident_urn']}")
    print("#" * 72)


if __name__ == "__main__":
    anyio.run(main)
