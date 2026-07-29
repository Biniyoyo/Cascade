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

    print(f"\nCanonical replays — A/B: {with_hits}/{n} correct root cause WITH "
          f"DataHub vs {without_hits}/{n} WITHOUT (same model, same question).")

    regrade_all_runs()


def regrade_all_runs():
    """Re-score every raw run in demo/cached/runs/, split by contamination.

    docs/eval.md quotes its headline over the hint-free subset only, so this
    reports both figures and never collapses them into one.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from audit_contamination import audit_run  # noqa: PLC0415

    runs = sorted((CACHE / "runs").glob("*/*.json"))
    if not runs:
        return
    tiers: dict = {}
    for p in runs:
        rec = json.loads(p.read_text())
        scenario = SCENARIOS_BY_ID.get((rec.get("scenario") or {}).get("id"))
        if not scenario:
            continue
        ok = grade_root_cause(rec["steps"], rec.get("final_text") or "", scenario)
        nc = grade_no_context(rec["no_context"]["text"], scenario)
        clean = audit_run(
            rec, set(scenario.get("expected_root_cause_urns") or []))["clean"]
        t = tiers.setdefault(p.parent.name,
                             {"n": 0, "ok": 0, "nc": 0, "clean": 0, "clean_ok": 0})
        t["n"] += 1
        t["ok"] += ok
        t["nc"] += nc
        if clean:
            t["clean"] += 1
            t["clean_ok"] += ok

    print("\nAll raw runs (re-scored from the traces):")
    tot = dict.fromkeys(("n", "ok", "nc", "clean", "clean_ok"), 0)
    for name, t in sorted(tiers.items()):
        for k in tot:
            tot[k] += t[k]
        print(f"  {name:8s} {t['ok']}/{t['n']} with DataHub · {t['nc']}/{t['n']} "
              f"without  |  hint-free subset: {t['clean_ok']}/{t['clean']}")
    print(f"\nADMISSIBLE (hint-free runs only): {tot['clean_ok']}/{tot['clean']} "
          f"correct WITH DataHub vs 0/{tot['clean']} WITHOUT.")
    print(f"All {tot['n']} runs incl. contaminated: {tot['ok']}/{tot['n']} vs "
          f"{tot['nc']}/{tot['n']} — see scripts/audit_contamination.py")


if __name__ == "__main__":
    main()
