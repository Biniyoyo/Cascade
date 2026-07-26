"""Pre-seeded incident scenarios. These double as (1) the Gate-3 eval set and
(2) the cached demo content the judge-facing UI replays for free."""

DBT = "urn:li:dataset:(urn:li:dataPlatform:dbt,{path},PROD)"

SCENARIOS = [
    {
        "id": "null_spike",
        "name": "NULL spike (broken lookup)",
        "failure_type": "Data quality — NOT NULL contract violation",
        "affected_urn": DBT.format(path="b2fd91.ORDER_ENTRY_DB.analytics.order_details"),
        "affected_label": "order_details",
        "symptom": ("The `billing_country` column has a sudden spike of NULL/empty values "
                    "(it is declared NOT NULL and tagged PII), and the Order Entry dashboard's "
                    "country-level revenue splits are now wrong."),
        "priority": "HIGH",
        "expected_root_cause": "countries",   # human label (upstream dbt source)
        "expected_root_cause_urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.countries,PROD)",
    },
    {
        "id": "bad_aggregation",
        "name": "Inflated totals (duplicated line items)",
        "failure_type": "Correctness — metric inflation",
        "affected_urn": DBT.format(path="b2fd91.ORDER_ENTRY_DB.analytics.order_details"),
        "affected_label": "order_details",
        "symptom": ("Order totals in `order_details` are roughly doubled since the last run — "
                    "line items appear duplicated, so revenue and quantity metrics on every "
                    "downstream dashboard are inflated."),
        "priority": "CRITICAL",
        "expected_root_cause": "order_items",
        "expected_root_cause_urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.order_items,PROD)",
    },
    {
        "id": "pii_nulls",
        "name": "Invalid PII (email nulls)",
        "failure_type": "Data quality — PII completeness",
        "affected_urn": DBT.format(path="b2fd91.order_entry_db.order_entry.customers"),
        "affected_label": "customers",
        "symptom": ("The `cust_email` column in `customers` has a spike of NULL/invalid values, "
                    "breaking email campaigns and any downstream customer analytics that key on email."),
        "priority": "HIGH",
        # the true upstream is the physical Snowflake load feeding the dbt model —
        # NOT the affected dbt dataset itself (which would make grading trivial)
        "expected_root_cause": "snowflake CUSTOMERS load",
        "expected_root_cause_urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.customers,PROD)",
    },
]

SCENARIOS_BY_ID = {s["id"]: s for s in SCENARIOS}


def incident_prompt(scenario: dict) -> str:
    return f"""\
DATA INCIDENT (priority: {scenario['priority']})

Dataset: {scenario['affected_label']}
URN: {scenario['affected_urn']}
Failure type: {scenario['failure_type']}

Symptom: {scenario['symptom']}

Investigate via the DataHub graph and respond per your procedure.
"""
