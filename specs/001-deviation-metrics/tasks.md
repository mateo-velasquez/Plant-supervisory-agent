# 001 · Deviation metrics — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · `domain/enums.py` with ordered `Severity` and tests for ordering and `max`.
- [ ] T2 · `domain/models.py` (frozen models) and `metrics/thresholds.py` with a loader test on fixture `umbrales.yaml`.
- [ ] T3 · Synthetic plant fixtures (CSV with BOM) plus failing loader tests (BOM, malformed row) → `ingestion/plant.py`.
- [ ] T4 · `ingestion/snapshot.py` with schema test → implementation.
- [ ] T5 · E3 → `metrics/progress.py`.
- [ ] T6 · E1 plan part → `metrics/plan.py` (mid and closing, previous shifts, fractional half).
- [ ] T7 · E4, E5, E6, E7, E8 plus the exact-cut-off test → `metrics/delay.py`.
- [ ] T8 · E9 plus tie and no-delayed cases → `metrics/bottleneck.py`.
- [ ] T9 · E1, E2, E10, E11, E12 → `metrics/severity.py`.
- [ ] T10 · `metrics/engine.py` integrating all functions for one snapshot, with a 2-combination fixture test.
- [ ] T11 · Import-boundary test: `metrics` does not import `anthropic` or `mcp`.
- [ ] T12 · Update `docs/STRUCTURE.md` and set this spec's status to Implemented.
