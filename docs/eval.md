# CASCADE eval — fair A/B, raw results (two model tiers)

Same model in BOTH arms within each tier. Strict structural grading: the agent's
root-cause `update_description` write must target the ground-truth **table**
(accepted at any layer of its ingestion chain — postgres origin, warehouse load,
or dbt source — never the affected dataset itself). A URN merely mentioned in
prose never counts. Graph reset to a hint-free baseline before every rep
(`scripts/reset_graph.py`). All raw traces in `demo/cached/runs/`.

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

Re-score everything offline: `python scripts/regrade.py` (canonical replays) or
re-grade the raw runs directly — grading logic is `cascade/grading.py`.