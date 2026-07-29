"""Run ONE incident end-to-end through CASCADE — against any DataHub dataset.

Nothing here is specific to the demo graph. Point it at a dataset URN from *your*
DataHub and describe the symptom in plain English; CASCADE reads your lineage,
schema and ownership through the DataHub MCP Server and responds.

    # the seeded demo incident (defaults)
    python run_incident.py

    # your own catalog — any platform DataHub knows about
    python run_incident.py \
      --urn 'urn:li:dataset:(urn:li:dataPlatform:snowflake,PROD_DB.sales.orders,PROD)' \
      --symptom 'freshness check failed — no rows loaded since 03:00 UTC'

    # see what it *would* write, without writing anything
    python run_incident.py --propose

Environment (same as the DataHub MCP Server): DATAHUB_GMS_URL, DATAHUB_GMS_TOKEN,
plus ANTHROPIC_API_KEY. Writes need a token with edit rights.
"""
import argparse
import json
import re

import anyio
from cascade.agent import run_incident

# Defaults reproduce the recorded demo incident on the seeded quickstart graph.
DEMO_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,"
    "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)"
)
DEMO_SYMPTOM = (
    "A data-quality check failed — the `billing_country` column has a sudden "
    "spike of NULL / empty values, and the Order Analytics Looker dashboard is "
    "now showing wrong country-level revenue splits. On-call needs to know the "
    "root cause and everything downstream that is now unreliable."
)


def dataset_label(urn: str) -> str:
    """Human-readable table name out of a dataset URN, for the prompt header."""
    m = re.search(r",([^,]+),[A-Z]+\)$", urn)
    return m.group(1).split(".")[-1] if m else urn


def build_prompt(urn: str, symptom: str, priority: str) -> str:
    return f"""\
DATA INCIDENT (priority: {priority})

Dataset: {dataset_label(urn)}
URN: {urn}

Symptom: {symptom}

Investigate via the DataHub graph and respond per your procedure.
"""


async def main(urn: str, symptom: str, priority: str, budget: float,
               propose: bool = False):
    print("=" * 70)
    print("CASCADE — incident run" + ("  [PROPOSE MODE — no writes]" if propose else ""))
    print(f"target: {dataset_label(urn)}")
    print("=" * 70)
    result = await run_incident(build_prompt(urn, symptom, priority),
                                max_budget_usd=budget, propose=propose)
    print("\n" + "=" * 70)
    if propose:
        print("PROPOSED ACTIONS (captured by the permission gate — NOT executed)")
        print("-" * 70)
        if result["proposed_writes"]:
            for i, w in enumerate(result["proposed_writes"], 1):
                print(f"  {i}. {w['tool']}")
                for line in json.dumps(w["input"], indent=2).splitlines():
                    print(f"     {line}")
        else:
            print("  (none — the agent proposed no writes this run)")
        print("-" * 70)
        print("Re-run without --propose to let CASCADE execute these itself.")
    print(f"tools used: {result['tools_used']}")
    print(f"run cost:   ${result['cost_usd']:.4f}")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run one CASCADE incident end-to-end against any DataHub dataset.")
    parser.add_argument(
        "--urn", default=DEMO_URN,
        help="dataset URN to investigate (default: the seeded demo incident)")
    parser.add_argument(
        "--symptom", default=DEMO_SYMPTOM,
        help="what broke, in plain English — the failing check, column, or SLA")
    parser.add_argument(
        "--priority", default="high",
        choices=["low", "medium", "high", "critical"],
        help="incident priority to file (default: high)")
    parser.add_argument(
        "--budget", type=float, default=2.0,
        help="hard spend cap in USD for this run (default: 2.0)")
    parser.add_argument(
        "--propose", action="store_true",
        help="dry run: investigate with real read access, but collect the "
             "write-tool calls as proposals for a human to confirm instead of "
             "executing them")
    args = parser.parse_args()
    anyio.run(main, args.urn, args.symptom, args.priority, args.budget,
              args.propose)
