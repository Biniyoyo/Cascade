"""Gate-2 vertical slice: run ONE incident end-to-end through CASCADE."""
import argparse
import json

import anyio
from cascade.agent import run_incident

HERO_URN = (
    "urn:li:dataset:(urn:li:dataPlatform:dbt,"
    "b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD)"
)

INCIDENT = f"""\
DATA INCIDENT (priority: high)

Dataset: order_details (analytics)
URN: {HERO_URN}

Symptom: A data-quality check failed — the `billing_country` column has a sudden
spike of NULL / empty values, and the Order Analytics Looker dashboard is now
showing wrong country-level revenue splits. On-call needs to know the root cause
and everything downstream that is now unreliable.

Investigate via the DataHub graph and respond per your procedure.
"""


async def main(propose: bool = False):
    print("=" * 70)
    print("CASCADE — incident run" + ("  [PROPOSE MODE — no writes]" if propose else ""))
    print("=" * 70)
    result = await run_incident(INCIDENT, max_budget_usd=2.0, propose=propose)
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
        description="Run one CASCADE incident end-to-end.")
    parser.add_argument(
        "--propose", action="store_true",
        help="dry run: investigate with real read access, but collect the "
             "write-tool calls as proposals for a human to confirm instead of "
             "executing them")
    args = parser.parse_args()
    anyio.run(main, args.propose)
