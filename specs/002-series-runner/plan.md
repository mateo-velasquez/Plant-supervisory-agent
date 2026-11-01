# 002 · Series runner — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/enums.py` | Add `ShiftPosition` (`mid`, `closing`) and `AnomalyKind`. |
| `domain/models.py` | Add `Anomaly` (frozen) and `SnapshotCommit` (frozen dataclass). |
| `domain/calendar.py` | **New.** `snapshot_position`, moved from `metrics/plan.py`, now returning `(Shift, ShiftPosition)`. |
| `metrics/plan.py` | Loses `snapshot_position` (no re-export). `cumulative_plan` is unchanged. |
| `metrics/engine.py` | Imports `snapshot_position` from `domain.calendar`; passes `shift.turno_id` and `position is ShiftPosition.CLOSING` to `cumulative_plan`. |
| `metrics/delay.py` | Q-19: elapsed clamped at 0 in `projected_yard_arrival`. |
| `metrics/progress.py` | Q-20: `count_progress` counts each `unidad_id` once, in the combination of its first occurrence. |
| `ingestion/snapshot.py` | Add `parse_snapshot(data, source)`; `load_snapshot(path)` delegates to it. |
| `ingestion/arrivals.py` | **New.** `Arrival` and `load_arrivals(path) -> list[Arrival]`. |
| `ingestion/hashing.py` | **New.** `content_hash(data) -> str`. |
| `runner/__init__.py` | **New.** Package marker; no re-exports. |
| `runner/ports.py` | **New.** `ProcessedStore` (unit of work over a `SnapshotCommit`) and `SnapshotPipeline` protocols. |
| `runner/memory_store.py` | **New.** `InMemoryProcessedStore`. |
| `runner/checks.py` | **New.** Pure anomaly checks: shift mismatch, stage entry after the snapshot, unit identity. |
| `runner/series.py` | **New.** `RunSummary`, `RunAborted`, `run_series`. |

- `ingestion/shift_index.py` / `ShiftIndex` from the draft is **dropped**: `domain/calendar.py` replaces it.
- No new setting. `archivo` resolves against the directory of `llegadas.csv`, and the caller (the spec 012 CLI) builds that path from `settings.data_dir` following the `data/README.md` layout.

## Types and interfaces
```python
# domain/enums.py
class ShiftPosition(StrEnum):
    MID = "mid"
    CLOSING = "closing"

class AnomalyKind(StrEnum):
    REPEATED_WITH_DIFFERENT_CONTENT = "repeated_with_different_content"  # Q-10
    SHIFT_MISMATCH = "shift_mismatch"                                    # Q-18
    STAGE_ENTRY_AFTER_SNAPSHOT = "stage_entry_after_snapshot"            # Q-19
    UNIT_COMBINATION_CHANGED = "unit_combination_changed"                # Q-20

# domain/models.py
class Anomaly(FrozenModel):
    kind: AnomalyKind
    snapshot_id: str
    detail: str

@dataclass(frozen=True)
class SnapshotCommit:
    """Everything the store records atomically when a snapshot's unit of work succeeds."""
    snapshot_id: str
    content_hash: str
    anomalies: tuple[Anomaly, ...]
    new_units: Mapping[str, Combination]     # first sightings in this snapshot only

# domain/calendar.py
def snapshot_position(shifts: Iterable[Shift], snapshot_id: str) -> tuple[Shift, ShiftPosition]:
    """Raises ValueError naming `snapshot_id` if it is neither a mid nor a closing snapshot."""

# ingestion/snapshot.py
def parse_snapshot(data: bytes, source: Path) -> Snapshot:
    """UTF-8 JSON bytes to Snapshot; DataLoadError names `source` and the field."""
def load_snapshot(path: Path) -> Snapshot:   # unchanged behaviour: parse_snapshot(path.read_bytes(), path)

# ingestion/arrivals.py
class Arrival(FrozenModel):
    """Row of llegadas.csv; `archivo` is already resolved against the CSV's directory."""
    orden: PositiveInt
    snapshot_id: str
    archivo: Path
    recibido: NaiveDatetime          # validated, informative only

def load_arrivals(path: Path) -> list[Arrival]:
    """utf-8-sig; unique positive `orden`; bare portable `archivo`; sorted by `orden`."""

# ingestion/hashing.py
def content_hash(data: bytes) -> str:
    """Lowercase hex SHA-256 of raw bytes."""

# runner/ports.py
class ProcessedStore(Protocol):
    def get_hash(self, snapshot_id: str) -> str | None: ...
    def known_units(self) -> Mapping[str, Combination]: ...    # seeds the identity map; {} when fresh
    def record_anomaly(self, anomaly: Anomaly) -> None: ...    # skip path only (Q-10 different hash)
    def processing(self, commit: SnapshotCommit) -> AbstractContextManager[None]:
        """Unit of work: on a clean exit records hash, anomalies and new units atomically; on any exception, nothing.

        Every registry write for this snapshot must use the same connection inside this block; the
        composition root passes one store instance to the runner and the pipeline. Raises ValueError
        on entry if `commit.snapshot_id` is already marked.
        """

class SnapshotPipeline(Protocol):
    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        """Side effects outside the database (notifier delivery) must happen only after the commit."""

# runner/memory_store.py
class InMemoryProcessedStore:        # satisfies ProcessedStore structurally
    def __init__(self, hashes: Mapping[str, str] | None = None) -> None: ...   # seed id -> hash (E9)
    def get_hash(self, snapshot_id: str) -> str | None: ...
    def known_units(self) -> Mapping[str, Combination]: ...
    def record_anomaly(self, anomaly: Anomaly) -> None: ...
    @contextmanager
    def processing(self, commit: SnapshotCommit) -> Iterator[None]: ...
    def recorded_anomalies(self) -> tuple[Anomaly, ...]: ...    # test accessor, not in the port

# runner/checks.py
def check_shift(snapshot: Snapshot, shift: Shift) -> Anomaly | None: ...
def check_stage_entries(snapshot: Snapshot) -> tuple[Anomaly, ...]: ...
def check_unit_identity(
    snapshot: Snapshot, first_seen: Mapping[str, Combination]
) -> tuple[tuple[Anomaly, ...], dict[str, Combination]]:
    """Anomalies for units seen with a combination other than their first, and this snapshot's new sightings."""

# runner/series.py
@dataclass(frozen=True)
class RunSummary:
    processed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()

class RunAborted(Exception):
    """Run stopped at `snapshot_id`; earlier snapshots stay processed, this one does not."""
    snapshot_id: str
    cause: Exception
    summary: RunSummary
    def __init__(self, snapshot_id: str, cause: Exception, summary: RunSummary) -> None: ...
    # str(): "run aborted at <snapshot_id>: <cause>"

def run_series(
    arrivals: Sequence[Arrival],
    shifts: Sequence[Shift],
    store: ProcessedStore,
    pipeline: SnapshotPipeline,
) -> RunSummary: ...
```

### `run_series` algorithm
1. Sort `arrivals` by `orden`.
2. **Upfront (Q-21):** for every arrival, check that `archivo` exists and resolve `(shift, position)` with `snapshot_position`, keeping the result. Collect every missing file and every unknown id. If there are any, raise one `DataLoadError` listing them all; nothing else runs.
3. `first_seen = dict(store.known_units())`.
4. For each `(arrival, shift, position)`, inside one `try` that turns any `Exception` into `RunAborted(arrival.snapshot_id, exc, summary_so_far) from exc`:
   1. `data = arrival.archivo.read_bytes()` and `h = content_hash(data)`. The bytes are read once and not parsed yet.
   2. `stored = store.get_hash(arrival.snapshot_id)`.
      - If `stored == h`: append to `skipped`, log INFO, continue.
      - If `stored is not None` (a different hash): build the Q-10 anomaly, call `store.record_anomaly`, add it to the summary, log WARNING, append to `skipped`, continue.
   3. `snapshot = parse_snapshot(data, arrival.archivo)`. If `snapshot.snapshot_id != arrival.snapshot_id`, raise `DataLoadError` naming the file and both ids.
   4. Run `check_shift`, `check_stage_entries` and `check_unit_identity(snapshot, first_seen)`. Add the anomalies to the summary and log one WARNING each.
   5. Build `commit = SnapshotCommit(arrival.snapshot_id, h, anomalies, new_units)`, then run `with store.processing(commit): pipeline.process(snapshot, shift, position)`.
   6. `first_seen.update(new_units)`, append to `processed`, log INFO.
5. Return the `RunSummary`.

`KeyboardInterrupt` and other `BaseException`s are not caught. They leave the `with` block by exception, so the store records nothing.

### Log messages (logger `plant_monitor.runner.series`)

| Level | Message |
|---|---|
| INFO | `"<id> processed: <turno_id> <position>"` |
| INFO | `"<id> skipped: already processed"` |
| WARNING | `"<id> repeated with different content (hash <new>); first processed version (hash <stored>) kept"` |
| WARNING | `"<id> <kind>: <detail>"` for every other anomaly |

## Where the anomaly checks live, and why
- **`runner/checks.py`**, importing only `domain` (enforced by a layer test). The checks are pure functions over `Snapshot`, `Shift` and a plain mapping, so they need nothing beyond builders.
- **Not `ingestion`:** ingestion validates one file against its schema. Unit identity is series state across snapshots, and a shift mismatch needs the calendar, so neither fits a per-file loader. Ingestion stays a set of loaders that succeed or raise.
- **Not `domain`:** `domain` holds data-contract types and pure lookups (`calendar.py`). Run-time policy (what counts as an anomaly, at what granularity) belongs to the layer that orchestrates the run.
- **Not `metrics`:** metrics compute numbers per snapshot. The numeric consequences of Q-19 and Q-20 do live in `metrics` (the clamp and first release wins), so the numbers are right whichever caller uses them.
- **`check_unit_identity` returns only the new sightings.** The runner merges them, and the same mapping is `SnapshotCommit.new_units`, so the store persists exactly what the runner learned.

## Design notes
- **ADR-0008** records the three decisions behind this spec: idempotency by content hash with first-wins (Q-10), the store unit of work over a `SnapshotCommit` (Q-23), and non-fatal data anomalies (Q-18, Q-19, Q-20).
- **Pipeline pattern:** the runner only orders, deduplicates, checks and delegates. `runner/series.py` never imports `metrics` or `cases`: it imports only `domain`, `ingestion` and `runner` (enforced by a layer test). The `runner` package as a whole may import `metrics` later, when the composition root wires the pipeline (STRUCTURE.md).
- **Read once, hash, parse the same bytes:** dedupe works on bytes, so a byte-identical repeat costs one hash and no validation, and a corrupt re-send of a processed snapshot cannot abort the run (E9). Because the hashed bytes are the parsed bytes, the stored hash always matches the content the pipeline saw.
- **The port seam carries everything spec 003 must persist:**
  - the hash, the snapshot's anomalies and its new units in the `SnapshotCommit`;
  - the skip-path anomaly through `record_anomaly`;
  - identity back through `known_units()`.

  Spec 003 can therefore plug SQLite in without changing the runner, provided its store honours the unit-of-work contract.
- **`SnapshotCommit`, `Anomaly` and `AnomalyKind` live in `domain`**, not `runner`, so the spec 003 store (outside `runner`) can accept and persist them without importing `runner`, as the dependency rule requires. `Arrival` lives in `ingestion/arrivals.py`: only ingestion and the runner use it, and `domain` keeps the data-contract types.
- **One connection per snapshot:** every registry write of a snapshot must go through the store's connection inside `processing`, and the composition root (spec 012) passes the same instance to the runner and the pipeline.
- **Side effects after commit:** the pipeline must not deliver notices before its unit of work commits. Otherwise a failure and resume would resend an `alerta_inmediata` (FR-21: at most one per case). Spec 004 may return outgoing notices from `process` or write them to an outbox table that a notifier drains after commit. The 002 signature does not change.
- **`RunAborted` wraps every per-arrival `Exception`** (read, parse, id mismatch, pipeline, commit), so callers have one exception to catch for "stopped mid-series, resumable". Upfront failures raise `DataLoadError` directly, because there is nothing to resume. Non-`Exception` errors such as `KeyboardInterrupt` propagate unwrapped.
- **Shift resolved once:** the upfront pass validates calendar membership and keeps `(shift, position)`, so the loop has no "unknown snapshot" path.
- **Defensive sort in `run_series`:** FR-01 is enforced where processing happens, not only in the loader.
- **No wall clock:** neither `runner` nor the checks call `datetime.now()`. E16 would fail if they did, because the test machine's clock is months after March 2026.
- **`snapshot_position` returns the `Shift`**, so the runner hands the pipeline the full row without a second lookup. `cumulative_plan` keeps its `is_closing: bool` to limit the churn in 001.
- **Future, no change in 002:** `compute_metrics` still calls `snapshot_position` itself. In spec 004 it could instead take the shift and position from the runner (through the pipeline), leaving one source for "`turnos.csv` wins".
- **Spec 003 and the in-memory store:** spec 003 either replaces `InMemoryProcessedStore` with its in-memory registry (SQLite `:memory:`) or keeps it as a test fake. Either way, it adds its implementations to the `store_factory` fixture of the contract test.

## Test strategy
- **Domain:**
  - `tests/unit/domain/test_calendar.py`: E20, moved from `tests/unit/metrics/test_plan.py` (removed there).
  - `tests/unit/domain/test_anomaly_types.py`: `Anomaly`, `SnapshotCommit` and the `AnomalyKind`/`ShiftPosition` values.
- **Metrics:**
  - `test_delay.py` and `test_bottleneck.py`: E16 metrics part (new), and E16b plus the bottleneck parts (characterization).
  - `test_progress.py`: E17b. `test_engine.py`: E17 and E21 metrics parts (E21 is characterization).
- **Ingestion:**
  - `test_snapshot_loader.py`: E6b; the existing tests stay as they are.
  - `test_arrivals.py`: a synthetic `llegadas.csv` written in `tmp_path` with `encoding="utf-8-sig"` (BOM). Covers E2 loader part, E3, E4 (a–h) and E5, plus `Arrival` validation.
  - `test_hashing.py`: E6.
- **Runner:**
  - `test_store_contract.py`: E19 as a contract test parametrized over a `store_factory` fixture (only `InMemoryProcessedStore` in 002), plus in-memory-specific `recorded_anomalies` checks.
  - `test_checks.py`: E15–E18 and E21 check parts, with in-memory `Snapshot` builders and no files.
  - `test_series.py`: E1, E2 runner part, E7–E15, and the runner parts of E16, E17, E21 and E22.
    - Builders: `snapshot_payload`, `unit_payload`, `released_payload` and `write_snapshot` move to `tests/builders.py`, and `test_snapshot_loader.py` imports them from there.
    - Calendars: the fixture `turnos.csv`, plus a synthetic one with a T17 row for S034.
    - `FakePipeline` records `(snapshot_id, turno_id, position)` and can raise a given exception on a given id.
    - `SpyStore` wraps the in-memory store and counts `processing` and `record_anomaly` calls.
    - `caplog` checks logger `plant_monitor.runner.series`.
- **Import boundaries** (`tests/unit/test_import_boundaries.py`):
  - The `anthropic`/`mcp` scan is extended to `ingestion` and the whole `runner` package.
  - Layer checks, using the same AST scanner extended to report `plant_monitor.<subpackage>`: `domain` imports nothing from the project; `ingestion` imports only `domain` (and itself); `runner/checks.py` imports only `domain`.
- **Not covered:** real-data runs (an eval) and the SQLite store (spec 003).

## Risks
- **Spec 003 transaction:** the in-memory store cannot prove that the pipeline's writes and the commit are atomic. The SQLite store must open the transaction in `processing`, record the hash, anomalies and `new_units` in it, and share it with every registry write of that snapshot. Otherwise a crash between them breaks resume (NFR-10).
- **MCP server in a separate process (ADR-0007):** if registry write tools run in the MCP server's own process, their writes cannot join the runner's transaction, and SQLite may answer "database is locked". **Open for spec 006 / ADR-0007 (Q-24):** use an in-process MCP transport, or have the tools return write requests that the coordinator applies in-process inside the unit of work.
- **Spec 003 must persist released units in release order:** Q-20 makes `count_progress` order-dependent. If the registry returns `released_so_far` unordered, a unit released under two combinations could count in the wrong one.
- **Spec 003 must persist `new_units` with the hash:** if a persistent store kept hashes but not units, the anomaly set would depend on where a run resumed. Spec 005 evals compare those sets.
- **Anomaly noise:** `stage_entry_after_snapshot` and `unit_combination_changed` fire per unit and per snapshot, so many cases in the real data would grow the WARNING log. A rerun records a different-hash anomaly again. Spec 003 may deduplicate or aggregate.
- **Moving `snapshot_position`** touches implemented 001 code and tests. It is done first, as a pure refactor with the suite green, before any 002 feature.
