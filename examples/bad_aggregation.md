# CASCADE sample output — Inflated totals (duplicated line items)

**Affected:** order_details · **Failure:** Correctness — metric inflation · **Priority:** CRITICAL

**Symptom:** Order totals in `order_details` are roughly doubled since the last run — line items appear duplicated, so revenue and quantity metrics on every downstream dashboard are inflated.

**Root cause (found):** order_items · **Blast radius:** 35 assets (3 dashboards, 12 charts) · **Incident:** urn:li:incident:d77d9253-a536-436e-aa4d-d362b079abc9 · **Assertion:** urn:li:assertion:cascade-ba2e8ccaf80a

---

## Without DataHub (same model, guessing)

## Best-Effort Diagnosis

**Likely Root Cause (high confidence guess):**
A join or union operation in the ETL pipeline that loads `order_details` is probably executing without proper deduplication logic — either a self-join gone wrong, a union with an unfiltered replay of recent data, or a missing `DISTINCT` after consolidating multiple source tables. The fact that *line items* are duplicated (not just counts) suggests the raw extraction or transformation step is the culprit, not a late-stage aggregation bug.

**Probable Downstream Impact:**
Any dashboard or metric relying on `order_details` for revenue, quantity sold, GMV, order count, or customer LTV is now showing ~2x inflated values. This likely includes:
- Financial/business dashboards (revenue reporting to leadership)
- Operational dashboards (inventory, fulfillment)
- Customer analytics (repeat purchase rates, AOV)
- Any alerts/SLAs tied to order volume thresholds

**Immediate actions:** Check the last ETL run logs for join/union cardinality warnings, verify that the upstream source tables haven't been accidentally re-loaded, and confirm whether a recent pipeline code change touched the deduplication logic.

---

## With DataHub — CASCADE's full report

All three write-backs confirmed. Full incident report below.

## 🚨 INCIDENT REPORT — Order total inflation in `order_details`

### Root cause
**Asset/column:** `order_items` (`urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.order_entry_db.order_entry.order_items,PROD)`), columns `quantity` and `unit_price`.

**Why:** Column-level lineage shows `order_details.line_total` is derived directly from `order_items.quantity` + `order_items.unit_price`. The dbt model builds `order_details` by joining `order_items` to the order header table **without first aggregating line items to order grain**, causing a classic fan-out join: every order row gets multiplied by its line-item count before totals are computed — producing exactly the "roughly doubled" symptom reported (orders with 2 line items ≈2x, orders with N line items ≈Nx). This is independently corroborated by a pre-existing engineering annotation already on the `order_items` source describing the same join/fan-out defect and estimating a 2–10x inflation range.

### Blast radius
Traced downstream from `order_details` up to 3 hops: **16 directly-verified downstream assets**:
- 1 sibling physical table: Snowflake `ORDER_DETAILS`
- **3 dashboards:** "Order Entry Dashboard" (Tableau), "datahub_order_entries" (PowerBI Report), "Order Entry Dashboard" (Looker)
- **12 charts:** Orders By Month, Promotions, Order Mode, Popular Products Categories (Tableau) · Popular Products, Promotions, Order Mode, Orders by Day (Looker) · Customer Analysis, Geographics, Executive Summary, DAX Visual (PowerBI)

Pre-existing documentation on the upstream source estimates ~35 assets affected when following further downstream hops (e.g. additional BI derivatives not resolved in this lineage query). Every revenue/quantity/AOV metric on these assets is currently inflated.

### Owner routed to
**Data Platform Team** (technical owner of both `order_details` and `order_items`) and **Ian Chen**, Director of Data Engineering (business owner of both assets, and the on-record Data Owner Escalation Contact). Data stewards **Julia Novak** and **David Kim** looped in for downstream BI validation post-fix.

### Writes performed
| Write | URN |
|---|---|
| Native incident (CRITICAL) on `order_details` | `urn:li:incident:d77d9253-a536-436e-aa4d-d362b079abc9` |
| Description pointer on root-cause asset `order_items` | update succeeded (append) |
| Guard assertion on `order_details.line_item_id` | `urn:li:assertion:cascade-ba2e8ccaf80a` — checks `COUNT(*) OVER (PARTITION BY order_id, line_item_id) = 1` |

### Suggested fix for engineer
In the dbt model for `order_details`, aggregate `order_items` to one row per `order_id` (or per `order_id, line_item_id` if line-item grain must be preserved) **before** joining to the order header table, so the join keys match 1:1 grain on both sides. Add a dbt `unique` test on the grain key of the final model to prevent regression, in addition to the new CASCADE assertion.

### 📨 Alert to owner
```
To: Ian Chen (Director of Data Engineering) / Data Platform Team
Cc: Julia Novak (Data Quality Eng), David Kim
Priority: CRITICAL

Subject: [CRITICAL] order_details revenue/quantity metrics ~2x inflated — join fan-out bug

Team — order_details (urn:li:dataset:(urn:li:dataPlatform:dbt,b2fd91.ORDER_ENTRY_DB.analytics.order_details,PROD))
is producing order totals and quantities roughly doubled since the last run.

Root cause: the dbt model joins `order_items` to the order header table without
aggregating line items first, so each order is fanned out by its line-item count
before totals are summed (line_total/order_total/quantity all inflated).

Blast radius: 3 dashboards + 12 charts across Tableau, Looker, and PowerBI
(Order Entry Dashboard, datahub_order_entries, Executive Summary, and more) are
currently showing inflated revenue/AOV numbers — do not trust these for
reporting until fixed.

Fix: aggregate order_items to order grain (or order_id+line_item_id) BEFORE
the join in the order_details dbt model; add a dbt `unique` test on the grain key.

I've opened a native DataHub incident (urn:li:incident:d77d9253-a536-436e-aa4d-d362b079abc9)
with full details and added a guard assertion (urn:li:assertion:cascade-ba2e8ccaf80a)
on order_id+line_item_id uniqueness to catch recurrence. Please action ASAP given
downstream exec dashboards are affected.

— CASCADE (automated incident response)
```
