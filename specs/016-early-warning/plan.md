# 016 · Early warning: gap trend forecast and the Pronóstico window — Plan

ADR-0023 "Early warning as a code-only gap forecast shown in the dashboard" records the trend model, the dashboard window as the channel instead of a notice, storage in registry v5, write-time held-out truncation, failure containment, and why Anticipación is computed in the viewer (unlike ADR-0022).

## Modules

| File | Change | Responsibility |
|---|---|---|
| `domain/forecast.py` | New (leaf) | `ForecastStatus`, `Thresholds3`, `ForecastPoint`, `ForecastBasis`, `ForecastWarning`, `ForecastRow` (R8; I1). |
| `domain/calendar.py` | Adds | `scheduled_time`, `future_snapshots` (R4). |
| `metrics/plan.py` | Adds | `shift_plan` (moved from `engine._shift_plan`; `engine` imports it). |
| `metrics/forecast.py` | New (pure) | `ForecastConfig`, `WindowBase`, `threshold_units`, `forecast_snapshot` (R2–R7). |
| `cases/registry/schema.py` | Changes | `MIGRATION_V4_TO_V5_BODY`, `STEPS[4]`, `SCHEMA_VERSION = 5`. |
| `cases/registry/forecasts.py` | New | `SqliteForecastStore` (source + sink), `read_forecasts`. |
| `cases/registry/sqlite.py` | Changes | `self.forecasts = SqliteForecastStore(session)`. |
| `cases/registry/run_reader.py` | Changes | `RunRows.forecasts: tuple[ForecastRow, ...] \| None = None` (I7). |
| `runner/forecast_step.py` | New | `ForecastSource`, `ForecastSink`, `ForecastStep` (R9; I5). |
| `runner/pipeline.py` | Changes | Keyword-only `forecast: ForecastStep \| None` with no default; called in `finish`. |
| `runner/cli.py`, `runner/agent_pipeline.py`, `evals/smoke_days_1_7.py` | Changes | Build `ForecastStep` from settings, policy and `registry.forecasts`. |
| `config.py`, `.env.example` | Adds | The two settings (R10). |
| `dashboard/source.py` | Changes | `RunView.forecasts`, `Omitted.forecast_rows: int = 0`; `_filter_rows` omits refused rows (R15). |
| `dashboard/anticipation.py` | New (pure) | `score_episodes` (R14; I9). |
| `dashboard/forecast.py` | New (pure) | `build_forecast`, `active_warnings` (R11–R13, R15). |
| `dashboard/state.py`, `payloads.py` | Changes | `Cell.forecast` (R16); forecast `TypedDict`s incl. `ForecastOmitted`. |
| `dashboard/server.py` | Changes | Two `ASSETS` routes, `/api/forecast`, `_IGNORES_SNAPSHOT`. |
| `src/frontend/pronostico.html`, `forecast.js` | New | The Pronóstico window (R18). |
| `src/frontend/index.html`, `agentes.html`, `metricas.html`, `app.js`, `app.css` | Changes | Nav tab; Planta ⚠; styles. |
| `tests/forecast_builders.py` | New | `SYN`, `plan_rows`, `fc`, `fr`, `ft`, `failing_sink`. |

## Types and interfaces

### `domain/forecast.py`
```python
type ForecastStatus = Literal["warm_up", "no_target", "suppressed", "no_crossing", "warning"]
class Thresholds3(FrozenModel):        # units behind, positive
    media: float
    alta: float
    critica: float
class ForecastPoint(FrozenModel):
    snapshot_id: str
    scheduled_at: NaiveDatetime
    gap_units: float
    thresholds: Thresholds3 | None     # None when that shift's plan is 0
class ForecastBasis(FrozenModel):
    rate: float
    plan_per_snapshot: float | None
    window_first: str
    window_last: str
    points: PositiveInt                # W
    horizon: PositiveInt               # H (Q-135)
class ForecastWarning(FrozenModel):
    target_level: Severity
    crossing_snapshot_id: str
    crossing_at: NaiveDatetime
    hours: float
class ForecastRow(FrozenModel):
    seq: PositiveInt
    snapshot_id: str
    combination: Combination
    scheduled_at: NaiveDatetime
    gap_units: float
    gap_severity: Severity
    effective_severity: Severity
    status: ForecastStatus
    target_level: Severity | None
    thresholds: Thresholds3 | None
    points: tuple[ForecastPoint, ...]
    basis: ForecastBasis | None
    warning: ForecastWarning | None
```
- Validator (`ValueError`): `warm_up` ⇔ `basis is None`, and `warm_up` ⇒ `points == ()`; `warning is not None` ⇔ `status == "warning"`; `target_level is None` ⇔ gap severity `critica`; `target_level` is never `ninguna`.
- **Persisted contract:** stored as JSON in the registry; every field added later needs a default (as `RunReport`, 015), or older rows fail validation and the table reads as `unavailable` (R12).

### `domain/calendar.py`
```python
def scheduled_time(shift: Shift, position: ShiftPosition) -> datetime: ...
def future_snapshots(shifts: Iterable[Shift], snapshot_id: str, horizon: int) -> tuple[tuple[Shift, ShiftPosition, str], ...]: ...
```
`future_snapshots` orders with `calendar_order`; `ValueError` naming an unknown `snapshot_id` (as `snapshot_position`).

### `metrics/forecast.py`
```python
@dataclass(frozen=True)
class ForecastConfig:
    window: int                        # >= 2, re-checked in __post_init__
    horizon: int                       # >= 1
@dataclass(frozen=True)
class WindowBase:
    progress: Mapping[Combination, int]   # progress after seq n - W
    first_snapshot_id: str                # seq n - W + 1
def threshold_units(shift_plan: int, thresholds: Thresholds) -> Thresholds3 | None: ...
def forecast_snapshot(
    snapshot_id: str,
    seq: int,
    metrics: Mapping[Combination, CombinationMetrics],
    raised: frozenset[Combination],
    base: WindowBase | None,              # None = warm-up (n < W)
    calendar: Sequence[Shift],            # the forecast calendar (R4)
    ctx: PlantContext,
    config: ForecastConfig,
) -> tuple[ForecastRow, ...]: ...          # nine rows, canonical order
```
- Gap, gap severity, minimum severity and progress at N come from `metrics` (official values). Effective = `effective_severity(minimum, c in raised)` (`domain.cases`), so Q-134 is unit-tested here (E7).
- Future gaps: `cumulative_plan(ctx.plan, ctx.shifts, …)` (full shift list: the plan is plant data) and `gap_pct` / `gap_severity`; future snapshot ids come only from `calendar`. Pure: no I/O, no clock (NFR-04).

### `cases/registry` (schema v5, store, reader)
```sql
CREATE TABLE gap_forecasts (
    seq         INTEGER NOT NULL,
    snapshot_id TEXT NOT NULL,
    modelo      TEXT NOT NULL,
    mercado     TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('warm_up','no_target','suppressed','no_crossing','warning')),
    payload     TEXT NOT NULL,
    PRIMARY KEY (seq, modelo, mercado)
)
```
- No `;` inside the body (`_migrate` split rule). `payload` = `ForecastRow.model_dump_json()`.
- `SqliteForecastStore` (satisfies `ForecastSource` and `ForecastSink` structurally):
  - `open_seq(snapshot_id)` = `session.require_open(snapshot_id)`;
  - `released_through(seq)` = `ReleasedUnit`s of `released_units` with `seq ≤ ?`, by `seq, idx`;
  - `snapshot_at(seq)` = `processed_snapshots.snapshot_id` at that seq (the open unit's id for the open seq), `ValueError` if none;
  - `savepoint()` = `session.savepoint("forecast")`;
  - `save(snapshot_id, rows)`: every row's `seq` is the open seq and its `snapshot_id` matches (`ValueError`); `DELETE … WHERE seq = ?`, then insert.
- `read_forecasts(conn)`: `None` when the table does not exist **or** any payload fails `ForecastRow.model_validate_json` (R12, C4); else rows by `seq, rowid`. `run_reader._read` calls it; `_NEEDS` unchanged (optional table). `RunRows.forecasts` defaults to `None`, so `tests/dashboard_builders.py:32` and `source.py:159` keep working.

### `runner/forecast_step.py`
```python
class ForecastSource(Protocol):
    def open_seq(self, snapshot_id: str) -> int: ...
    def released_through(self, seq: int) -> tuple[ReleasedUnit, ...]: ...
    def snapshot_at(self, seq: int) -> str: ...
class ForecastSink(Protocol):
    def savepoint(self) -> AbstractContextManager[None]: ...
    def save(self, snapshot_id: str, rows: Sequence[ForecastRow]) -> None: ...
@dataclass(frozen=True)
class ForecastStep:
    config: ForecastConfig
    source: ForecastSource
    sink: ForecastSink
    calendar: tuple[Shift, ...]        # forecast calendar, fixed at wiring (R4)
    ctx: PlantContext
    @classmethod
    def build(cls, config: ForecastConfig, source: ForecastSource, sink: ForecastSink,
              ctx: PlantContext, policy: HeldOutPolicy) -> ForecastStep: ...
    def run(self, decision: SnapshotDecision) -> None: ...
```
- `build`: `calendar` = `calendar_order(ctx.shifts)` without `policy.refused_shifts` (all shifts when open).
- `run`: inside `sink.savepoint()`: `n = open_seq`; `base = None` if `n < W`, else `WindowBase(count_progress(released_through(n − W)), snapshot_at(n − W + 1))`; `raised` = `{case.combination for case in decision.delta.cases if case.raised}`; `forecast_snapshot(...)`; `sink.save`. `except Exception` → `logger.warning("forecast skipped for %s (%s)", sid, type(e).__name__)`; nothing re-raised (R9). `KeyboardInterrupt` passes.
- `SnapshotDecision` is imported from `runner.pipeline` under `TYPE_CHECKING` only, to avoid a cycle (`pipeline` imports `ForecastStep`).

### `runner/pipeline.py`
- `ThresholdPipeline.__init__(…, ledger=None, *, forecast: ForecastStep | None)` and `from_registry(registry, ctx, ledger=None, *, forecast: ForecastStep | None)`: no default, so mypy flags every caller. `ReleaseLog` unchanged.
- `finish(decision)`: notices, marks (unchanged), then `if self._forecast is not None:` require `decision.delta` (`ValueError`), `self._forecast.run(decision)`.
- Callers: `runner/cli._wire_thresholds` and `runner/agent_pipeline.build_agent_pipeline` (both hold `settings` and the policy), `evals/smoke_days_1_7.py` (its policy), each `ForecastStep.build(ForecastConfig(window=settings.early_warning_window_snapshots, horizon=settings.early_warning_horizon_snapshots), registry.forecasts, registry.forecasts, ctx, policy)`. `tests/incident_runs.py`, `tests/unit/runner/test_pipeline*.py`, `tests/integration/test_*_runner.py` pass `forecast=None`. `build_agent_pipeline`'s signature does not change.

### `dashboard/anticipation.py` and `dashboard/forecast.py`
```python
def score_episodes(rows: Sequence[ForecastRow], at: int) -> AccuracyBlock: ...
def active_warnings(rows: Sequence[ForecastRow], at: int) -> tuple[ForecastRow, ...]: ...
def build_forecast(view: RunView, calendar: Calendar, at: int) -> ForecastPayload: ...
```
- `score_episodes`: group by combination, one pass in seq order building episodes and crossings, match by scheduled time (R14). Reads only stored rows; no settings, no `metrics`, no golden data.
- `active_warnings`: rows at seq `at` with a warning, sorted by `(hours, combination index)`. `state.py` uses it for the cell marker, so Planta and Pronóstico agree by construction.
- `build_forecast`: combinations from `calendar.combinations`; thresholds become gap values (`-units`); labels and numbers per I11; `heldout` = `ForecastOmitted` from `view.omitted` (014's three counts + `forecast_rows`).

### `DashboardApp` and the cell
- `ASSETS` adds `/pronostico` and `/forecast.js`; `_API_ROUTES` adds `/api/forecast`; `_IGNORES_SNAPSHOT: Final = frozenset({"/api/metrics", "/api/forecast"})` replaces the single-route test.
- `Cell` gains `forecast: CellForecast | None` (`{target_level, label}`). `/api/state` and `/api/agents` keep 014's `HeldOut`.

## API
`GET /api/forecast?at=N` (shape; the examples are normative):
```json
{"at": 8, "latest": 8, "positions": [1, 2, 3, 4, 5, 6, 7, 8], "registry": "ok", "state": "ok",
 "heldout": {"open": true, "omitted": {"snapshots": 0, "notices": 0, "trace_lines": 0, "forecast_rows": 0}},
 "warnings": [{"modelo": "Pickup", "mercado": "Local", "target_level": "media", "label": "S010 · 22:00 (en 8 h)",
   "hours": 8, "basis": {"rate": "10.00", "plan_per_snapshot": "12.00", "window": "S005–S008", "threshold": "7.2"}}],
 "combinations": [{"modelo": "Pickup", "mercado": "Local", "status": "warning", "gap_severity": "ninguna",
   "effective_severity": "ninguna", "target_level": "media",
   "history": [{"seq": 8, "snapshot_id": "S008", "gap": -4.0, "lines": {"media": -7.2, "alta": -14.4, "critica": -25.2}}],
   "projection": [{"snapshot_id": "S009", "time": "18:00", "gap": -6.0, "lines": {"media": -7.2, "alta": -14.4, "critica": -25.2}}],
   "warning": {"target_level": "media", "label": "S010 · 22:00 (en 8 h)"}}],
 "accuracy": {"counts": {"fulfilled": 0, "not_fulfilled": 0, "pending": 1, "missed": 0, "no_forecast": 0},
   "mean_lead_hours": null,
   "episodes": [{"modelo": "Pickup", "mercado": "Local", "level": "media", "first": "S008", "last": "S008",
     "outcome": "pending", "crossing": null, "lead_hours": null}]}}
```
- `lines` is null where the shift plan is 0. In `unavailable`, `warnings`, `combinations` and `episodes` are `[]` and counts 0.

## Data flow
```
run:  decide → [judgment → redecide] → finish: notices.save → mark_reported
      → ForecastStep.run: savepoint { open_seq → released_through(n−W) → forecast_snapshot → save }   (one unit of work)
      exception → rollback to savepoint, WARNING, snapshot still commits
read: request → at check → load_view (run rows + forecasts, mode=ro, held-out rows omitted) → resolve_at
      → build_forecast (active_warnings, charts, score_episodes) → JSON
client: BroadcastChannel {mode, at} → fetch ?at=N | "Seguir en vivo" → poll (015 R15)
```

## Design notes
- **Why `metrics/forecast.py`.** It composes `cumulative_plan`, `gap_pct`, `gap_severity` and `effective_severity`: the same rules, in the package that owns them, so a threshold change moves official and projected severity together.
- **Why rows in `domain/forecast.py`.** `cases.registry` and `dashboard` may import `domain` but not `metrics`; the row is data, the forecast is the rule.
- **Why `finish` and a separate step (I5, I6).** `finish` is the one call that receives the final decision in both pipelines (Q-27). A combined collaborator with no default makes every construction site an explicit choice; the narrow source protocol keeps `ReleaseLog` as is.
- **Why only progress at n − W (I4, C1).** Progress at N is already the official metric; one bounded read replaces re-counting the whole series, and nothing depends on earlier forecast rows.
- **Why write-time truncation (Q-133).** No refused id ever reaches the registry, so the dashboard filter stays 014's whole-row rule; the cost is that boundary rows depend on the guard state.
- **Why a savepoint (Q-136).** The forecast is advisory: losing one snapshot's rows is better than aborting a run that already produced its notices (NFR-10).
- **Why Anticipación in the viewer (I9).** It is a pure count over stored rows, like 015's live noise; there is no golden truth to evaluate against, so no stored evaluation file exists to read.
- **Why a payload column.** Points and basis are nested and read whole; `status` stays a column for the CHECK and for inspection.

## Alternatives (rejected)
- **Linear fit of the gap.** Wrong when the plan changes (E2) or is 0 (E3); the plan is known, so only the release rate is estimated.
- **Holt or exponential smoothing.** More parameters to tune on about 42 points per combination, with no held-out tuning allowed.
- **Anticipatory notice in the outbox** (the 2026-11-01 draft). It would enter deliverables, `RunOutput` and the noise count (Q-119).
- **`tendencia` in the 009 brief.** It would put a forecast before the model that decides raises (Q-119).
- **Read-time redaction of held-out ids** (the first Q-133). It needs point- and warning-level filtering and an extra count; replaced by write-time truncation.
- **A backtest CLI.** Anticipación computes the same numbers as of any N.

## Constraints (non-negotiable)
- R19 layer rules. No model, no network, no new library. The dashboard writes nothing and never creates the table.
- Tests use `tests/fixtures/` and synthetic builders only; never days 8–10.
- Each test cites its spec id; helpers come `from forecast_builders import ...`, never `from tests....`; basenames unique.

## Docs rows (applied in T11)
- **STRUCTURE add:** `domain/forecast.py`, the `domain/calendar.py` and `metrics/plan.py` additions, `metrics/forecast.py`, `cases/registry/forecasts.py`, `runner/forecast_step.py`, the `schema.py` (v5), `run_reader.py`, `pipeline.py` rows; `dashboard/forecast.py`, `dashboard/anticipation.py`; `src/frontend/{pronostico.html, forecast.js}`. The `domain/perspectives.py` row: "not extended by 016 (Q-119)".
- **Dependency lines:** R19's rules.
- **README:** a "Forecast window" section under "Live dashboard" and the ADR-0023 decision line.

## Risks
- **Schema bump.** Every registry opened by the writer migrates to v5; older code fails on a v5 file with the existing version error. Pinned-4 tests change (spec Acceptance).
- **Caller churn.** The no-default keyword touches every `ThresholdPipeline` construction; mypy lists them.
- **Persisted contract.** A field added to `ForecastRow` without a default turns older registries `unavailable` (never a 500).
- **Frontend drift.** The `TypedDict`s and E15 fix the shape; T8 checks by hand.
- **mypy order:** T1 (domain, calendar, settings) → T2 (pure forecast) → T3 (schema, store) → T4 (step + pipeline + callers) → T5 (reader + source) → T6 (builders + cell) → T7 (server) → T8 (frontend).
