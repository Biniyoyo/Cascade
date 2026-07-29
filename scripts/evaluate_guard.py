"""Report a native assertion run event for the guard CASCADE registered.

DataHub custom assertions are evaluated by YOUR check runner (dbt test, Airflow
task, cron SQL check...) — this script is the reporting hook that runner calls,
posting the result natively via `reportAssertionResult` so the guard's status
appears on the asset's Quality/health UI.

Usage:
  python scripts/evaluate_guard.py <assertion_urn> --result PASS
  python scripts/evaluate_guard.py <assertion_urn> --result FAIL --url https://ci/run/123
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cascade import datahub_incidents as di  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("assertion_urn")
    ap.add_argument("--result", choices=["PASS", "FAIL"], required=True)
    ap.add_argument("--url", help="external URL of the check run (CI/Airflow/dbt)")
    args = ap.parse_args()
    ok = di.report_assertion_result(
        args.assertion_urn, success=(args.result == "PASS"),
        external_url=args.url,
        error_type=None if args.result == "PASS" else "SOURCE_DATA_ISSUE")
    print(f"reported {args.result} for {args.assertion_urn}: {'ok' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
