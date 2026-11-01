# 001 · Deviation metrics — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [x] T1 · `domain/enums.py` with ordered `Severity` and tests for ordering and `max`.
- [x] T2 · `domain/models.py` (frozen models) and `metrics/thresholds.py` with a loader test on fixture `umbrales.yaml`.
- [x] T3 · Synthetic plant fixtures (CSV with BOM, `turnos.csv.fecha` as `M/D/YYYY`) plus failing loader tests: BOM stripped, `fecha` ignored in favor of `inicio`/`fin`, malformed row names file, row and field, plan completeness (a shift missing a combination row fails naming `plan_produccion.csv`, the shift and the combination; an explicit `unidades_plan = 0` loads), a duplicate shift × combination row fails, and a row for a shift absent from `turnos.csv` fails → `ingestion/plant.py`.
- [x] T4 · `ingestion/snapshot.py` with schema tests (a unit without `etapa` fails naming the file and the field, US-01) → implementation.
- [x] T5 · E3 → `metrics/progress.py`.
- [x] T6 · E1 plan part, mid/closing detection via `turnos.csv` (S001 → T01 mid, S002 → T01 closing) and E17 (unknown snapshot names it) → `metrics/plan.py` (mid and closing, previous shifts, fractional half).
- [x] T7 · E4, E5, E6, E7, E8, E13, the exact-cut-off test (arrival equal to the cut-off misses it) and E14/E14b (Q-04: no reachable shipment → unit delay `None`, combination `None` if any unit is `None`, `delay_beyond_horizon` True) → `metrics/delay.py`.
- [x] T8 · E9, E16 (tie → most downstream), the no-delayed case, a repainting unit delayed with 0 elapsed, and units in `patio`/`despacho` never delayed → `metrics/bottleneck.py`.
- [x] T9 · E1, E2, E10, E11, E12, E15 (plan 0 → `gap_pct` `None`, no gap severity) and the severity parts of E13 (`alta`) and E14 (beyond horizon → `critica`) → `metrics/severity.py`.
- [x] T10 · `metrics/engine.py` integrating all functions for one snapshot, with a 2-combination fixture test.
- [x] T11 · Import-boundary test: `metrics` does not import `anthropic` or `mcp`.
- [x] T12 · Update `docs/STRUCTURE.md` and set this spec's status to Implemented.
