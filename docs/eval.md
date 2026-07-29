# CASCADE eval — fair A/B, raw results (two model tiers)

Same model in BOTH arms within each tier. Strict structural grading: the agent's
root-cause `update_description` write must target the ground-truth **table**
(accepted at any layer of its ingestion chain — postgres origin, warehouse load,
or dbt source — never the affected dataset itself). A URN merely mentioned in
prose never counts. All raw traces in `demo/cached/runs/`.

## Headline: 10/18 verifiably hint-free, 10/10 correct

> **We audited our own eval and found a bug — this is the corrected reading.**
>
> `scripts/reset_graph.py` was supposed to strip every prior annotation before
> each rep. It read a scenario key that no longer existed
> (`expected_root_cause_urn`, singular), so it silently only ever cleaned the
> *affected* dataset — never the ground-truth root-cause asset. In **8 of 18
> runs** the root-cause table therefore still carried a previous rep's CASCADE
> annotation (e.g. *"[ACTIVE INCIDENT] — this source is implicated in a NULL
> spike on `order_details.billing_country`"*) when the agent read it. Those runs
> were told the answer; they cannot be counted as finding it.
>
> **The bug is fixed** (plural key + a much wider hint-marker list). The
> contaminated runs stay published rather than being quietly deleted or re-run,
> and are **excluded from the headline**. Verify any trace set yourself:
>
> ```
> python scripts/audit_contamination.py --verbose
> ```
>
> It flags, per run, any CASCADE-authored annotation that appeared on a
> ground-truth root-cause asset in a **read**-tool result before that run wrote
> its own. Incident metadata on the *affected* asset is not counted — the
> failing table is given in the prompt, so an open incident on it is premise,
> not leakage.

**Admissible result: of the 10 runs that are verifiably hint-free, 10/10
identified the correct root-cause table (0/10 for the same models without
DataHub).** All 18 runs passed, but only these 10 are claimed.

| tier | runs | hint-free | correct (hint-free only) |
|---|---|---|---|
| claude-haiku-4-5 | 15 | 8 | **8/8** |
| claude-sonnet-5 | 3 | 2 | **2/2** |

The per-scenario table below reports **all** reps, including the contaminated
ones, for completeness.

| model | scenario | with DataHub | incident | assertion | without DataHub | mean $ |
|---|---|---|---|---|---|---|
| claude-haiku-4-5 | bad_aggregation | **5/5** | 5/5 | 5/5 | 0/5 | $0.13 |
| claude-haiku-4-5 | null_spike | **5/5** | 5/5 | 5/5 | 0/5 | $0.11 |
| claude-haiku-4-5 | pii_nulls | **5/5** | 5/5 | 5/5 | 0/5 | $0.08 |
| claude-sonnet-5 | bad_aggregation | **1/1** | 1/1 | 1/1 | 0/1 | $0.56 |
| claude-sonnet-5 | null_spike | **1/1** | 1/1 | 1/1 | 0/1 | $0.43 |
| claude-sonnet-5 | pii_nulls | **1/1** | 1/1 | 1/1 | 0/1 | $0.37 |

**claude-haiku-4-5: 15/15 correct root causes with DataHub vs 0/15 without.**
**claude-sonnet-5: 3/3 correct root causes with DataHub vs 0/3 without.**

Combined: **18/18 with DataHub vs 0/18 without** — the same models that scored
zero from the symptom alone find the exact root-cause table every time when
given the graph. The value is the context, not the parameters.

## Known limitation of the control arm

The no-DataHub control's system prompt (`cascade/no_context.py`) ended with
*"Do not invent specific asset names or URNs you can't know"* — while the
control was scored on whether it names the specific upstream asset. That is a
fair criticism of the method, so state the counter-evidence rather than the
score: across all 18 control outputs the true root-cause table name appears
**0 times** for `null_spike` (`countries`) and **0 times** for
`bad_aggregation` (`order_items`). For `pii_nulls` the string `customers`
appears, but only as the already-known *affected* table — never as an upstream
cause. The control never named the answer, hedging instruction or not; check
for yourself in `demo/cached/runs/*/*.json` → `no_context.text`.

The instruction has been removed for future runs (the control is now asked to
name its most-suspected upstream table even if unconfirmed). The published
control numbers above were produced with the old prompt and are labelled as
such — they have not been re-run, because re-running would cost API budget this
project no longer has.

## Reproduce offline (no API, no DataHub)

```
python scripts/audit_contamination.py   # which runs are admissible
python scripts/regrade.py               # re-score every raw run + the replays
```

Grading logic is `cascade/grading.py`; nothing above is self-reported by the
agent.