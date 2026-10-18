# 001 · Deviation metrics — Spec

- **Status:** Ready
- **Requirements:** FR-03 (plant files and snapshot loading), FR-05 to FR-11
- **Stories:** US-02
- **Week:** W1

## Goal
Compute, for every model × market combination at a given snapshot, the deterministic numbers the rest of the system depends on: actual progress, cumulative plan, gap, delay in days, bottleneck stage and minimum severity. No model calls.

## Scope
- **In:** typed loaders for `plan_produccion.csv`, `tiempos_estandar.csv`, `embarques.csv`, `turnos.csv`, `umbrales.yaml` and one snapshot JSON; the metric functions; the minimum severity.
- **Out:** arrival order and dedupe (spec 002), case lifecycle (spec 003), persistence of released units across runs (spec 003, registry).

## Behavior

**Loading (FR-03)**
- CSVs are read as `utf-8-sig`, which strips the BOM.
- Datetimes are ISO 8601 (`YYYY-MM-DDTHH:MM`), naive and in plant local time. `turnos.csv.fecha` is ignored in favor of `inicio`/`fin`.
- Every row is validated into a typed model. An invalid row raises an error naming the file, the row and the field.

**Actual progress (FR-05, §1)**
- Progress of a combination = the number of **distinct** `unidad_id` in `liberadas` of all snapshots processed so far, starting at S001.

**Cumulative plan (FR-06, §1)**
- Sum of `unidades_plan` of all shifts before the current one, plus `0.5 ×` the current shift's plan at its mid snapshot or `1.0 ×` at its closing snapshot.
- The value can be fractional (e.g. half of 5 = 2.5).

**Gap (FR-07, §1)**
- `gap_units = progress − cumulative_plan`. Negative means behind.
- `daily_plan = current shift plan × 3` and `gap_pct = gap_units / daily_plan × 100`.

**Projected yard arrival (FR-08, §1)**
- Applies only to units whose `etapa` is in `carroceria`, `pintura`, `montaje` or `calidad`.
- `elapsed = snapshot.timestamp − ingreso_etapa`.
- `remaining_current = max(0, standard(current stage) − elapsed)`.
- A unit in `pintura` with `retrabajos > 0` uses `minutos_retrabajo` as the standard of `pintura`.
- `projected = snapshot.timestamp + remaining_current + Σ standard(next stages up to and including calidad)`.

**Delay in days (FR-09, §1)**
- The reachable shipment is the first shipment of the unit's market, ordered by `corte_en_patio`, whose `corte_en_patio > projected`.
- `delay_days = (reachable.salida − assigned.salida) / 1 day`, floored at 0 (Q-09).
- A combination's delay is the maximum over its units. Units in `patio` or `despacho` are excluded. With no eligible units, the delay is 0.

**Bottleneck stage (FR-10, §1)**
- A unit is **delayed** in its stage if `elapsed > standard + tolerancia_minutos`, or if it is being repainted.
- The bottleneck is the stage with the most delayed units. It is `None` if there are none. On a tie, the most downstream stage wins (Q-03).

**Minimum severity (FR-11, §2)**
- **Gap severity:** none if `behind_units < minimo_unidades`, where `behind_units = −gap_units`. Otherwise the highest level whose threshold `≤ behind_pct` (`media` 10, `alta` 20, `critica` 35).
- **Delay severity:** the highest level of the unit's market whose threshold `≤ delay_days`. Local has `media` 1, `alta` 2 and `critica` 3; Brazil and Europe have `alta` 1 and `critica` 3.
- **Minimum severity:** the max of the two. **Deviation** exists when it is ≥ `media`.
- Thresholds are inclusive (Q-07) and always read from `umbrales.yaml`.

## Worked examples

| # | Input | Expected |
|---|---|---|
| E1 | Sedán × Local, T01 plan 12, mid snapshot, 2 distinct released | cumulative plan 6, gap −4 u, −11.1 % of 36 → gap severity `media` |
| E2 | Same as E1 but 4 released | gap −2 u → below `minimo_unidades` → no gap severity |
| E3 | Unit U1 in `liberadas` of S001 and S002 | counted once |
| E4 | Snapshot 2026-03-02T10:00, Sedán × Local in `montaje` since 08:00, assigned LOC-0302 | remaining montaje 480 min + calidad 180 → projected 21:00; reachable LOC-0303 → delay 1 day → `media` (Local) |
| E5 | Snapshot 2026-03-02T10:00, SUV × Brasil in `pintura` since 09:00, `retrabajos = 1`, assigned BRA-0303 | paint uses 360: remaining 300 + montaje 660 + calidad 180 → projected 03-03 05:00 < cut-off 06:00 → reachable BRA-0303 → delay 0 |
| E6 | Same as E5 but `retrabajos = 0` | paint uses 480: projected 03-03 07:00 → reachable BRA-0304 → delay 1 → `alta` (Brazil) |
| E7 | SUV × Europa assigned EUR-0305 (cut-off 03-04 20:00), projected 03-05 | reachable EUR-0312 → delay 7 → `critica` |
| E8 | Units in `patio` and `despacho` only | delay 0; they are not counted |
| E9 | 3 units in `montaje` over standard + 60 min, 1 repainting in `pintura` | bottleneck `montaje` |
| E10 | Gap severity `media`, delay severity `alta` | minimum severity `alta`; deviation |
| E11 | Brazil delay 0.0 | no delay severity (no `media` level for Brazil) |
| E12 | Behind exactly 10.0 % with ≥ 3 units | `media` (inclusive) |

## Edge cases and assumptions
- **Q-03:** a bottleneck tie is broken by the most downstream stage.
- **Q-04:** if no reachable shipment exists in `embarques.csv`, the delay is reported as `None` and the delay severity is `critica`, flagged as a data horizon problem.
- **Q-06:** the daily plan is the current shift plan × 3, literally.
- **Q-07:** thresholds are inclusive.
- **Q-09 (new):** if a unit can reach a shipment earlier than its assigned one, the delay is 0, never negative.
- A unit ahead of plan (positive gap) never produces gap severity.

## Acceptance
- [ ] E1–E12 are tests and pass.
- [ ] Loaders are tested on synthetic CSVs with a BOM and on one malformed row.
- [ ] `metrics` imports neither `anthropic` nor `mcp`.
- [ ] `ruff`, `mypy --strict` and `pytest` pass.
- [ ] `docs/STRUCTURE.md` reflects the created modules.
