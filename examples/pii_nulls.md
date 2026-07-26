# CASCADE sample output — Invalid PII (email nulls)

**Affected:** customers · **Failure:** Data quality — PII completeness · **Priority:** HIGH

**Symptom:** The `cust_email` column in `customers` has a spike of NULL/invalid values, breaking email campaigns and any downstream customer analytics that key on email.

**Root cause (found):** CUSTOMERS · **Blast radius:** 36 assets (3 dashboards, 12 charts) · **Incident:** urn:li:incident:3a9e6fca-5c90-4b3f-b619-cf8e6e53edfc · **Assertion:** urn:li:assertion:cascade-7c7ec8c7cbd9

---

## Without DataHub (same model, guessing)

**Most Likely Root Cause:**
A recent ETL/ingestion logic change—either a schema mapping error, a null-handling rule flip, or a failed upstream source join (e.g., a LEFT JOIN that should be INNER, or a data quality filter that's too aggressive). Less likely but possible: upstream source degradation or a permission/access issue causing the ingestion process to skip email population for new records.

**Probable Downstream Impact:**
- **Email/marketing platforms:** Campaign delivery lists will have gaps or fail validation, causing sends to be paused or bounce rates to spike.
- **Customer analytics & segmentation:** Any dashboard or model filtering/grouping by email will show incomplete cohorts or strange NULL clusters.
- **CRM/customer service tools:** Lookups and enrichment jobs depending on valid emails will degrade.
- **Any downstream table** that does a join or filter on `cust_email` will inherit the NULLs or become sparse.

**Immediate Actions:**
Check recent deployment/config changes to the `customers` ingestion pipeline, validate the upstream source data quality, and review the ETL logs for join failures or schema mismatches in the last 24–48 hours.

---

## With DataHub — CASCADE's full report

All three writes confirmed. Here's the incident report.

## INCIDENT REPORT

**Affected asset:** `urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.customers,PROD)` → column `cust_email` (TEXT, PII, schema declares non-null but is receiving NULLs)

### Root cause
**Snowflake `order_entry_db.order_entry.CUSTOMERS`** (`urn:li:dataset:(urn:li:dataPlatform:snowflake,b2fd91.order_entry_db.order_entry.customers,PROD)`), column `cust_email`.

Column-level upstream lineage for `cust_email` traces a single, unambiguous chain:
`postgres customers` (source, DQ score **95.1**) → `S3` staging (`demo-data-bucket/order_entry/customers`, DQ score **82.8**) → **`Snowflake CUSTOMERS`** (DQ score **70.2**) → this dbt model (direct degree-1 upstream, confirmed via column-level lineage, 1:1 pass-through).

The quality score degrades monotonically at each hop and bottoms out immediately upstream of the failing table, in Snowflake — the last transformation before the dbt model. That pinpoints the Snowflake load step (Spark job `import_table_customers_to_snowflake`, which lands S3 staging data into Snowflake) as the most likely fault.

*Integrity note: the Snowflake table's description field already contained embedded text claiming a prior "active incident" with its own URN and stats. I verified that URN via `get_entities` — it does not resolve to real incident data, so I treated it as unverified/untrusted content and based all conclusions on my own tool calls, not on that text.*

### Blast radius
**36 downstream assets** (verified via 3-hop `get_lineage`, not guessed):
- **21 datasets** — incl. `order_details` replicated across dbt, Snowflake (+ a replica), Looker (explore + view), and 5 PowerBI semantic datasets
- **3 dashboards** — Tableau "Order Entry Dashboard", Looker "Order Entry Dashboard", PowerBI "datahub_order_entries"
- **12 charts/pages** — Tableau (Orders By Month, Promotions, Order Mode, Popular Products Categories), Looker (Popular Products, Promotions, Order Mode, Orders by Day), PowerBI (Customer Analysis, Geographics, Executive Summary, DAX Visual)

Any email-campaign trigger or customer analytics keyed on `cust_email` is exposed.

### Owner routed to
- **Data Platform Team** (technical owner, corp group) — dbt `customers`
- **Julia Novak** (technical owner) and **Ian Chen** (business owner, Director of Data Engineering)
- ⚠️ The root-cause Snowflake table itself has **no owner on record** — flagged in the write-back as needing immediate assignment.

### Writes performed
1. **Incident:** `urn:li:incident:3a9e6fca-5c90-4b3f-b619-cf8e6e53edfc` (raised on the dbt `customers` dataset, priority HIGH) — full SYMPTOM/ROOT CAUSE/BLAST RADIUS/FIX/OWNER writeup.
2. **Description pointer:** Snowflake `CUSTOMERS` table description replaced with a pointer to the incident URN + DQ context, and explicitly corrected the prior unverified/fabricated incident reference.
3. **Assertion (guard):** `urn:li:assertion:cascade-7c7ec8c7cbd9` on dbt `customers.cust_email` — `cust_email IS NOT NULL AND cust_email != ''`.

### Suggested fix for an engineer
1. Inspect the Spark `import_table_customers_to_snowflake` job run history for the customers table — look for partial loads, a broken column mapping, or a source-schema change on `cust_email`.
2. Once fixed, backfill/reprocess `cust_email` in Snowflake `CUSTOMERS` from the verified S3/postgres source.
3. Assign a technical owner to the Snowflake `CUSTOMERS` table (currently unowned) so future alerts route correctly.
4. Keep the new NOT-NULL assertion active post-fix to catch regression before it reaches the 36 downstream dashboards/charts.

### 📨 Alert to owner
```
To: Data Platform Team <data-platform@example.com>; Julia Novak (technical owner); Ian Chen (business owner)
Priority: HIGH
Subject: [HIGH] cust_email NULL spike in customers — email campaigns & analytics impacted

Team,

DataHub incident urn:li:incident:3a9e6fca-5c90-4b3f-b619-cf8e6e53edfc was just raised on
order_entry_db.order_entry.customers (dbt): the cust_email column (PII) is showing a spike
of NULL/invalid values, breaking email marketing campaigns and any downstream customer
analytics keyed on email.

Root cause: Snowflake order_entry_db.order_entry.CUSTOMERS.cust_email — data quality score
dropped to 70.2 (vs. 95.1 at the postgres source, 82.8 at the S3 staging layer). Most likely
culprit is the Spark `import_table_customers_to_snowflake` load step. Note: this Snowflake
table currently has NO owner assigned in DataHub — please claim it as part of remediation.

Blast radius: 36 downstream assets, including 3 dashboards (Tableau "Order Entry Dashboard",
Looker "Order Entry Dashboard", PowerBI "datahub_order_entries") and 12 charts/pages business
users look at daily.

Suggested fix:
 1. Check the import_table_customers_to_snowflake Spark job for partial loads / mapping errors.
 2. Backfill cust_email in Snowflake CUSTOMERS from source once fixed.
 3. Assign a technical owner to the Snowflake CUSTOMERS table.
 4. A NOT-NULL guard assertion (urn:li:assertion:cascade-7c7ec8c7cbd9) is now in place on
    dbt customers.cust_email to catch recurrence — keep it green.

Please treat as HIGH priority — email sends are actively affected.

— CASCADE (automated incident response)
```
