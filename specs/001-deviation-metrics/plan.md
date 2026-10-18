# 001 · Deviation metrics — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/enums.py` | `Stage`, `Market`, `Model`, `Severity` (ordered), with Spanish values (ADR-0005). |
| `domain/models.py` | Frozen pydantic models: `Unit`, `ReleasedUnit`, `Snapshot`, `PlanRow`, `StandardTime`, `Shipment`, `Shift`, `Combination`, `CombinationMetrics`. |
| `metrics/thresholds.py` | `Thresholds` model plus `load_thresholds(path)` for `umbrales.yaml`. |
| `ingestion/plant.py` | `load_plan`, `load_standards`, `load_shipments`, `load_shifts` (`utf-8-sig`, validated). |
| `ingestion/snapshot.py` | `load_snapshot(path) -> Snapshot`. |
| `metrics/progress.py` | `count_progress(released) -> dict[Combination, int]`. |
| `metrics/plan.py` | `cumulative_plan(plan, shifts, shift_id, is_closing) -> dict[Combination, float]`. |
| `metrics/delay.py` | `projected_yard_arrival`, `reachable_shipment`, `unit_delay_days`, `combination_delay`. |
| `metrics/bottleneck.py` | `is_delayed(unit, at, standards, tolerance)`, `bottleneck_stage(units, …)`. |
| `metrics/severity.py` | `gap_severity`, `delay_severity`, `minimum_severity`. |
| `metrics/engine.py` | `compute_metrics(snapshot, released_so_far, ctx) -> dict[Combination, CombinationMetrics]`. |

## Types and interfaces
```python
class Severity(StrEnum):            # order: NONE < MEDIUM < HIGH < CRITICAL
    NONE = "ninguna"; MEDIUM = "media"; HIGH = "alta"; CRITICAL = "critica"

class Stage(StrEnum):
    BODY = "carroceria"; PAINT = "pintura"; ASSEMBLY = "montaje"
    QUALITY = "calidad"; YARD = "patio"; DISPATCH = "despacho"

@dataclass(frozen=True)
class PlantContext:                 # everything static for the series, loaded once
    plan: list[PlanRow]; shifts: list[Shift]; standards: StandardsTable
    shipments: ShipmentsTable; thresholds: Thresholds

class CombinationMetrics(BaseModel, frozen=True):
    combination: Combination
    progress: int; cumulative_plan: float
    gap_units: float; gap_pct: float
    delay_days: float | None; bottleneck: Stage | None
    gap_severity: Severity; delay_severity: Severity; minimum_severity: Severity
    @property
    def has_deviation(self) -> bool: ...
```

## Design notes
- **Pure functions:** the time reference is always the snapshot timestamp, never `datetime.now()`.
- **Strategy:** `delay_severity` reads per-market levels from `Thresholds`, so there is no `if market == ...` branching.
- `StandardsTable` and `ShipmentsTable` are small lookup wrappers. Shipments are indexed per market and sorted by cut-off, so `reachable_shipment` is a `bisect`.
- `released_so_far` is passed in by the caller. The registry will own it (spec 003), which keeps `metrics` free of I/O.

## Test strategy
- `tests/unit/metrics/`: one test module per metrics file, with E1–E12 as named tests.
- `tests/fixtures/plant/`: tiny synthetic CSVs (written with BOM) and a minimal `umbrales.yaml` copy with the same structure.
- Snapshot fixtures are built in Python with builder helpers rather than large JSON files.
- Not covered here: multi-snapshot accumulation (spec 003) and real-data smoke runs (an eval, not a test).

## Risks
- **Misreading §1 on half-shift plans or daily plan:** mitigated by E1/E2 and the open question log.
- **Time arithmetic off by a boundary (`>` vs `≥` at cut-off):** E5 sits 1 h before the cut-off, so a dedicated test at exactly the cut-off is added.
