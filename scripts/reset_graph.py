"""Reset the demo graph to a hint-free baseline before an eval rep.

Fairness requires that no run benefits from (a) a previous run's own
annotations (incident pointers appended to descriptions), (b) pre-existing
"analyst note" hints in the datapack that literally describe the planted
defect, or (c) leftover injection payloads. This script:

  1. resolves any ACTIVE incidents on the scenario's affected dataset, and
  2. rewrites the affected + ground-truth root-cause assets' editable
     descriptions with all hint/pollution lines removed.

Usage:  python scripts/reset_graph.py          # reset every scenario's assets
        (run_eval.py calls reset_for_scenario() before each rep)
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cascade import datahub_incidents as di  # noqa: E402
from cascade.scenarios import SCENARIOS  # noqa: E402

# any line containing one of these is stripped from descriptions
HINT_MARKERS = [
    "INCIDENT POINTER", "🚨", "INCIDENT NOTE", "AGENT INSTRUCTION",
    "fan-out", "fan out", "duplicat", "known issue", "analyst note",
    "join-key mismatch", "missing rows",
]

_GET = """query d($urn: String!) {
  dataset(urn: $urn) { editableProperties { description } properties { description } }
}"""
_SET = """mutation u($input: DescriptionUpdateInput!) { updateDescription(input: $input) }"""


def _clean_text(text: str) -> str:
    kept = []
    for line in (text or "").split("\n"):
        low = line.lower()
        if any(m.lower() in low for m in HINT_MARKERS):
            continue
        kept.append(line)
    out = "\n".join(kept)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _clean_description(urn: str) -> bool:
    d = (di._gql(_GET, {"urn": urn}) or {}).get("dataset") or {}
    current = ((d.get("editableProperties") or {}).get("description")
               or (d.get("properties") or {}).get("description") or "")
    cleaned = _clean_text(current)
    if cleaned != current.strip():
        di._gql(_SET, {"input": {"resourceUrn": urn, "description": cleaned}})
        return True
    return False


def reset_for_scenario(scenario: dict):
    affected = scenario["affected_urn"]
    root = scenario.get("expected_root_cause_urn")
    try:
        for inc in di.list_incidents(affected):
            if inc["status"]["state"] == "ACTIVE":
                di.resolve_incident(inc["urn"], "reset before eval rep")
    except Exception as e:  # noqa: BLE001
        print(f"    (incident reset skipped: {e})")
    for urn in filter(None, {affected, root}):
        try:
            if _clean_description(urn):
                print(f"    cleaned description: {urn.split(',')[-2].split('.')[-1]}")
        except Exception as e:  # noqa: BLE001
            print(f"    (description reset skipped for {urn[:60]}: {e})")


if __name__ == "__main__":
    for sc in SCENARIOS:
        print(f"reset: {sc['id']}")
        reset_for_scenario(sc)
    print("graph reset complete")
