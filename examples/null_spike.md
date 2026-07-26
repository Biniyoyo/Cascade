# CASCADE sample output — NULL spike (broken lookup)

**Affected:** order_details · **Failure:** Data quality — NOT NULL contract violation · **Priority:** HIGH

**Symptom:** The `billing_country` column has a sudden spike of NULL/empty values (it is declared NOT NULL and tagged PII), and the Order Entry dashboard's country-level revenue splits are now wrong.

**Root cause (found):** countries · **Blast radius:** 35 assets (3 dashboards, 12 charts) · **Incident:** urn:li:incident:23a3103c-00d0-4692-95a3-2fc6fe9148ef · **Assertion:** urn:li:assertion:cascade-5c1019a5f342

---

## Without DataHub (same model, guessing)

**Best-Effort Diagnosis:**

**Likely Root Cause (highest confidence guess):**
A recent upstream change in the order entry application or ETL pipeline probably stopped populating `billing_country` before inserting/updating records in `order_details`. This could be:
- An application deployment that removed/commented out the country field capture logic
- An ETL job that changed or broke the source join/lookup to populate country data
- A data validation rule that was removed, allowing NULLs through that were previously rejected

**Probable Downstream Impact:**
Any dashboard or report aggregating revenue by country will show incomplete totals (missing the NULL bucket) and skewed country-level comparisons. The Order Entry dashboard's country-level revenue splits are the obvious victim, but any downstream analytics, BI reports, or ML models that depend on `billing_country` for segmentation (especially those tagged as PII-related for compliance/audit) are likely also broken. The NOT NULL constraint being violated suggests the issue is fresh and systemic, not data quality drift.

**Next Steps (if I had access):**
Check recent deployments to the order entry system and ETL jobs; compare `billing_country` population rates before/after the incident timestamp; and review any schema or validation changes.

---

## With DataHub — CASCADE's full report

All three writes confirmed. Here's the full incident report.

---

## INCIDENT REPORT

### Root Cause
`order_details.billing_country` (NOT NULL, PII) is populated by a **single, direct column-level lineage edge** from `countries.country_name` in the dbt source `urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.countries,PROD)` — no intermediate transformation exists. Since this is a lookup/join relationship (not a passthrough), a NULL spike here is consistent with either:
- missing/dropped rows in `countries` since its last refresh, or
- a join-key mismatch (e.g. country code vs. country name) between order-entry source tables and `countries`.

Ingestion chain feeding that table: Postgres `countries` → Spark export → S3 → Spark import → Snowflake `COUNTRIES` → dbt source `countries`. No other upstream input to `billing_country` exists, so this lookup is the most likely fault point.

### Blast Radius
**35 downstream assets** (3 hops): **20 datasets, 12 charts, 3 dashboards**.
- **Dashboards (all business-facing):**
  - Looker – *"Order Entry Dashboard"* (`urn:li:dashboard:(looker,b2fd91.dashboards.53)`)
  - Tableau – *"Order Entry Dashboard"* (`urn:li:dashboard:(tableau,b2fd91.843bf583-900b-f1ba-0532-b5e67a0373dc)`)
  - Power BI – *"datahub_order_entries"* report (`urn:li:dashboard:(powerbi,b2fd91.reports.66666666-7777-8888-9999-000000000000)`)
- **Charts (12):** Looker — Popular Products, Promotions, Order Mode, Orders by Day; Tableau — Order Mode, Orders By Day, Promotions, Top Product Category; Power BI — 4 report pages.
- **Datasets (20):** Snowflake `ORDER_DETAILS`/`ORDER_DETAILS_REPLICA`/`ORDER_HISTORY`, dbt `order_history`, Looker explore/view, Power BI semantic models (Customer Analytics, Essential KPI, Geographic, Product Performance, Time Intelligence Measures), 4 Tableau Custom SQL datasets.

Any country-revenue KPI/measure/visual across these is affected — matches the reported symptom on the Order Entry dashboards.

### Owner Routing
**Data Platform Team** — technical owner of both the affected dataset (`order_details`) and the root-cause asset (`countries` source). **Ian Chen, Director of Data Engineering**, is business owner of both and is the named point of contact.

### Writes Confirmed
- **Native incident:** `urn:li:incident:23a3103c-00d0-4692-95a3-2fc6fe9148ef` (priority HIGH, on `order_details`) — full SYMPTOM/ROOT CAUSE/BLAST RADIUS/SUGGESTED FIX/OWNER in the description.
- **Description update:** root-cause asset `countries` (dbt source) now carries a pointer back to the incident and the join-failure hypothesis.
- **Guardrail assertion:** `urn:li:assertion:cascade-5c1019a5f342` — `billing_country IS NOT NULL` on `order_details`.

### Suggested Fix (for engineer)
1. Inspect `countries` at each hop (Postgres → S3 → Snowflake) for rows dropped since the last refresh.
2. Check the join key used to attach `country_name` onto `order_details` for a format mismatch (ISO code vs. full name, casing, or new countries missing from the reference table).
3. Re-run/backfill the `order_details` dbt model once `countries` is fixed.
4. The new NOT NULL assertion will now catch recurrence automatically.

---

### 📨 Alert to owner
```
To: Data Platform Team (Ian Chen, Director of Data Engineering)
Priority: HIGH
Subject: [HIGH] billing_country NULL spike breaking Order Entry dashboard country revenue splits

Ian / Data Platform Team —

A NOT NULL contract violation is live on order_details.billing_country (PII column). Native incident opened:
urn:li:incident:23a3103c-00d0-4692-95a3-2fc6fe9148ef

ROOT CAUSE: Column lineage shows billing_country is populated directly (single hop) from
countries.country_name (dbt source order_entry_db.order_entry.countries). The NULL spike
points to either dropped rows in `countries` since its last refresh, or a join-key mismatch
(country code vs. name) in the lookup. Ingestion chain: Postgres countries -> S3 -> Snowflake
COUNTRIES -> dbt source.

BLAST RADIUS: 35 downstream assets — all 3 "Order Entry Dashboard" instances (Looker, Tableau,
Power BI) plus 12 charts and 20 datasets/semantic models are showing wrong country-level
revenue splits right now.

SUGGESTED FIX: Check `countries` for missing rows post-refresh and verify the join key format;
backfill order_details once fixed. I've added a NOT NULL assertion
(urn:li:assertion:cascade-5c1019a5f342) on billing_country to catch recurrence, and left a
pointer note on the `countries` table description.

Please triage ASAP — this is customer-facing revenue reporting.

— CASCADE (automated incident response)
```
