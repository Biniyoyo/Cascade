"""Re-grade the cached eval traces with the structural (URN-based) grader.

No API calls, no live DataHub — pure re-scoring of demo/cached/*.json using
run_eval.grade_root_cause / grade_no_context, rewriting root_cause_correct and
no_context.named_root_cause in both the raw and .display cache files.

Usage:  python scripts/regrade.py
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cascade.grading import grade_root_cause, grade_no_context  # noqa: E402
from cascade.scenarios import SCENARIOS_BY_ID  # noqa: E402

CACHE = Path(__file__).resolve().parents[1] / "demo" / "cached"


def main():
    with_hits, without_hits, n = 0, 0, 0
    for sid, scenario in SCENARIOS_BY_ID.items():
        raw_path = CACHE / f"{sid}.json"
        if not raw_path.exists():
            continue
        n += 1
        rec = json.loads(raw_path.read_text())
        ok = grade_root_cause(rec["steps"], rec.get("final_text") or "", scenario)
        nc = grade_no_context(rec["no_context"]["text"], scenario)
        rec["scenario"] = scenario
        rec["root_cause_correct"] = ok
        rec["grading"] = ("structural: update_description entity_urn == expected_root_cause_urn; "
                          "single run per scenario")
        rec["no_context"]["named_root_cause"] = nc
        raw_path.write_text(json.dumps(rec, indent=2, default=str))
        with_hits += ok
        without_hits += nc

        disp_path = CACHE / f"{sid}.display.json"
        if disp_path.exists():
            disp = json.loads(disp_path.read_text())
            disp["root_cause_correct"] = ok
            if isinstance(disp.get("no_context"), dict):
                disp["no_context"]["named_root_cause"] = nc
            if isinstance(disp.get("scenario"), dict):
                disp["scenario"] = scenario
            disp_path.write_text(json.dumps(disp, indent=2, default=str))
        print(f"{sid:16s} with DataHub: {'CORRECT' if ok else 'MISS':7s} | "
              f"without: {'named it' if nc else 'missed'}")

    print(f"\nA/B: {with_hits}/{n} correct root cause WITH DataHub vs "
          f"{without_hits}/{n} WITHOUT — same model, same question.")


if __name__ == "__main__":
    main()
