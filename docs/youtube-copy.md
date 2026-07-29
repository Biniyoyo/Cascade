# YouTube re-upload — paste-ready copy

## Title
CASCADE — DataHub-grounded autonomous data incident response

## Description
An AI on-call engineer for data pipelines, built on DataHub for the "Build with
DataHub: The Agent Hackathon" (Track 1 — Agents That Do Real Work).

When a data-quality check fails, CASCADE reads DataHub's context graph via the
MCP Server (schema, column-level lineage, owners), identifies the evidence-backed
likely root cause, maps the downstream blast radius, files a native DataHub
incident, registers a guard assertion, routes the owners — and proposes the
repair (dbt test + patch proposal, human-approval gated).

Measured, not asserted: the same model, with vs without DataHub's graph,
strictly graded on the root-cause URN the agent annotates —
10/10 correct with DataHub vs 0/10 without, across two model tiers, at a
measured $0.11 per investigation.

We also audited our own eval and published the auditor. A bug in the graph-reset
script left a previous run's annotation on the root-cause asset in 8 of 18 runs;
all 18 passed, but those 8 were told the answer, so they're excluded from the
number above rather than quietly re-run. Check any trace yourself with
scripts/audit_contamination.py. Methodology and every raw trace are in the repo.

▶ Try the war room (no setup): https://biniyoyo.github.io/Cascade/
▶ Code (Apache-2.0): https://github.com/Biniyoyo/Cascade
▶ Upstream contributions:
   https://github.com/acryldata/mcp-server-datahub/pull/147
   https://github.com/datahub-project/datahub-skills/pull/56
▶ Devpost: https://devpost.com/software/cascade-autonomous-data-incident-response-on-datahub

Chapters
0:00 A column breaks at 2 a.m.
0:23 What CASCADE does
0:59 The incident war room
1:12 Live investigation — no human in the loop
1:31 Without DataHub, the same model only guesses
1:37 With DataHub's graph, it knows
1:47 Blast radius: 35 downstream assets
1:55 Write-back: incident, guard, annotation
2:10 Routed to the owners
2:22 A context problem, not a model problem
2:28 Proof in numbers, and contributed upstream

Music: "Deliberate Thought" & "Inspired" — Kevin MacLeod (incompetech.com),
licensed under Creative Commons: By Attribution 4.0
https://creativecommons.org/licenses/by/4.0/
