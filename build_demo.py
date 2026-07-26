"""Precompute self-contained display payloads for the UI (free: GraphQL only, no LLM).
Reads demo/cached/<id>.json (the agent run) and enriches with blast-radius graph,
owners, and root-cause node → demo/cached/<id>.display.json served statically."""
import json
from pathlib import Path

from cascade.scenarios import SCENARIOS
from cascade import graph
from cascade import datahub_incidents as di

CACHE = Path(__file__).resolve().parent / "demo" / "cached"


def build(scenario: dict) -> dict:
    sid = scenario["id"]
    run = json.loads((CACHE / f"{sid}.json").read_text())

    blast = graph.blast_radius(scenario["affected_urn"])
    ups = graph.upstream_nodes(scenario["affected_urn"])
    owners = di.get_owners(scenario["affected_urn"])

    # root-cause node = the upstream whose name matches the expected root cause
    exp = scenario["expected_root_cause"].lower()
    rc = next((u for u in ups if exp in (u["name"] or "").lower()
               or exp in (u["urn"] or "").lower()), None)
    root_cause = rc or {"name": scenario["expected_root_cause"], "urn": None, "platform": ""}

    payload = {
        "id": sid,
        "name": scenario["name"],
        "failure_type": scenario["failure_type"],
        "priority": scenario["priority"],
        "affected": {"urn": scenario["affected_urn"], "name": scenario["affected_label"]},
        "symptom": scenario["symptom"],
        "root_cause": {"name": root_cause["name"], "urn": root_cause.get("urn"),
                       "platform": root_cause.get("platform", "")},
        "blast": blast,
        "owners": owners,
        "incident_urn": run.get("incident_urn"),
        "assertion_urn": run.get("assertion_urn"),
        "root_cause_correct": run.get("root_cause_correct"),
        "cost_usd": run.get("cost_usd"),
        "report_markdown": run.get("final_text"),
        "trace": run.get("steps", []),
        "no_context": run.get("no_context"),  # the A/B "without DataHub" guess
    }
    (CACHE / f"{sid}.display.json").write_text(json.dumps(payload, indent=2, default=str))
    dd = blast["counts"]
    print(f"  {sid:16s} blast total={dd.get('total',0):3d} "
          f"(dash={dd.get('DASHBOARD',0)}, chart={dd.get('CHART',0)}, ds={dd.get('DATASET',0)}) "
          f"owners={len(owners)} root={root_cause['name']}")
    return payload


def main():
    print("building display payloads...")
    index = []
    for sc in SCENARIOS:
        p = build(sc)
        index.append({"id": p["id"], "name": p["name"], "failure_type": p["failure_type"],
                      "priority": p["priority"], "affected": p["affected"]["name"],
                      "blast_total": p["blast"]["counts"].get("total", 0),
                      "root_cause": p["root_cause"]["name"]})
    (CACHE / "index.json").write_text(json.dumps(index, indent=2))
    print(f"wrote index.json ({len(index)} scenarios)")


if __name__ == "__main__":
    main()
