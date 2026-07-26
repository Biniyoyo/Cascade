"""Gate-2 vertical slice: run ONE incident end-to-end through CASCADE."""
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


async def main():
    print("=" * 70)
    print("CASCADE — incident run")
    print("=" * 70)
    result = await run_incident(INCIDENT, max_budget_usd=2.0)
    print("\n" + "=" * 70)
    print(f"tools used: {result['tools_used']}")
    print(f"run cost:   ${result['cost_usd']:.4f}")
    print("=" * 70)


if __name__ == "__main__":
    anyio.run(main)
