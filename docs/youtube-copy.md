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

Measured, not asserted: same model with vs without DataHub's graph, strictly
graded on the root-cause URN the agent annotates — results, methodology, and
raw traces in the repo.

▶ Code (Apache-2.0): https://github.com/Biniyoyo/Cascade
▶ Upstream contributions:
   https://github.com/acryldata/mcp-server-datahub/pull/147
   https://github.com/datahub-project/datahub-skills/pull/56
▶ Devpost: https://devpost.com/software/cascade-autonomous-data-incident-response-on-datahub

Chapters
0:00 A column breaks at 2 a.m.
0:20 Real DataHub receipts — incident, assertion, lineage
0:35 How CASCADE works
1:00 Live investigation (no human in the loop)
1:30 The A/B: same model, with vs without DataHub
2:00 Write-back, owners, repair proposal
2:30 Evidence & open source

Music: "Deliberate Thought" & "Inspired" — Kevin MacLeod (incompetech.com),
licensed under Creative Commons: By Attribution 4.0
https://creativecommons.org/licenses/by/4.0/
