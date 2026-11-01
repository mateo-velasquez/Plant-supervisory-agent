# 015 · Analytics dashboard (stretch) — Plan

## Modules

| File | Responsibility |
|---|---|
| `analytics/queries.py` | Aggregations over registry, usage and eval results. |
| `analytics/render.py` | Dashboard rendering (medium decided when Ready). |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
Read-only; depends on `cases`, `telemetry` and `evaluation`, never the reverse.

## Test strategy
Query tests on a synthetic registry; a render smoke test.

## Risks
Scope creep: limited to the metrics the brief asks to measure.
