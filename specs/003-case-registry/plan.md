# 003 · Case registry and lifecycle — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/cases.py` | **New.** `CaseState` (Spanish values, ADR-0005), `CaseEvent`, `effective_severity`, `Case`, `CaseHistoryRow`, `case_id_for`. Pure types; effective severity is computed here and nowhere else. |
| `cases/__init__.py` | **New.** Package marker; no re-exports. |
| `cases/lifecycle.py` | **New.** `Observation`, `Step`, `next_state` (pure transition function), `step`, `mark_reported`. Pure: no I/O. |
| `cases/registry.py` | **New.** `_SCHEMA` and `SCHEMA_VERSION` constants, `CaseRepository` protocol, `_Session` (connection + open unit of work + the single write guard), `SqliteRegistry` (`ProcessedStore` + `processing`), and its collaborators `SqliteCaseRepository` and `SqliteReleaseStore`. Imports no `lifecycle`. |
| `cases/tracker.py` | **New.** `TrackedEvent`, `CaseDelta`, `CaseTracker` (`track` with re-run, `mark_reported`). |
| `config.py` | `Settings.registry_path` property (`output_dir / "registry.sqlite3"`). |

- `runner/memory_store.py` stays as the runner's fake. There is **no** `InMemoryRegistry`: tests use `SqliteRegistry(":memory:")`, or a `tmp_path` file for reopen and resume.
- No change to `runner/ports.py`, `runner/series.py` or `metrics/*`.

## Types and interfaces
```python
# domain/cases.py
class CaseState(StrEnum):
    """Case lifecycle states (§3); values are the data contract's."""
    OPEN = "abierto"
    FOLLOW_UP = "en_seguimiento"
    ESCALATED = "escalado"
    RESOLVED = "resuelto"

    @property
    def is_active(self) -> bool: ...               # every state but RESOLVED

class CaseEvent(StrEnum):
    """What happened to a case at one snapshot; declaration order is emission order."""
    OPENED = "opened"
    ESCALATED = "escalated"
    SEVERITY_CHANGED = "severity_changed"
    RESOLVED = "resolved"

def effective_severity(minimum: Severity, raised: bool) -> Severity:
    """max(minimum, critica if raised); the only place this is computed (FR-15)."""

def case_id_for(snapshot_id: str, combination: Combination) -> str:
    """`<snapshot_id>-<modelo>-<mercado>`, e.g. `S012-Pickup-Brasil`."""

class Case(FrozenModel):
    """One case as of its last evaluated snapshot."""
    case_id: str
    combination: Combination
    opened_at: str                                  # opening snapshot_id
    state: CaseState
    minimum_severity: Severity                      # at last_snapshot_id
    raised: bool                                    # raise in force at last_snapshot_id
    max_severity_since_report: Severity | None      # None right after a mark (Q-28)
    clean_streak: NonNegativeInt
    last_snapshot_id: str
    last_reported_at: str | None = None
    last_reported_state: CaseState | None = None
    last_reported_severity: Severity | None = None
    resolved_at: str | None = None

    @computed_field
    @property
    def current_severity(self) -> Severity:         # effective_severity(minimum, raised) (Q-26)
        ...
    # Validators (ValueError): max is None or max >= current; max is None only if last_reported_at is set;
    # resolved_at is set iff state is RESOLVED; the three last_reported_* are all None or all set.

class CaseHistoryRow(FrozenModel):
    """A case evaluated at one snapshot."""
    case_id: str
    snapshot_id: str
    state: CaseState
    minimum_severity: Severity
    raised: bool
    gap_units: float
    gap_pct: float | None
    delay_days: float | None
    bottleneck: Stage | None
    clean_streak: NonNegativeInt

    @computed_field
    @property
    def effective_severity(self) -> Severity: ...   # effective_severity(minimum, raised)

# cases/lifecycle.py
@dataclass(frozen=True)
class Observation:
    """One combination at one snapshot, as the lifecycle sees it."""
    snapshot_id: str
    metrics: CombinationMetrics
    raised: bool

@dataclass(frozen=True)
class Step:
    """Result of evaluating one case at one snapshot."""
    case: Case
    history: CaseHistoryRow
    events: tuple[CaseEvent, ...]                   # in CaseEvent declaration order

def next_state(current: CaseState | None, *, critical: bool, resolvable: bool) -> CaseState:
    """§3 transition table; None means opening (Q-08); ValueError from RESOLVED."""
    match current:
        case CaseState.RESOLVED: raise ValueError(...)
        case _ if resolvable: return CaseState.RESOLVED
        case CaseState.ESCALATED: return CaseState.ESCALATED
        case _ if critical: return CaseState.ESCALATED
        case None: return CaseState.OPEN
        case _: return CaseState.FOLLOW_UP

def step(case: Case | None, obs: Observation, resolution: ResolutionThresholds) -> Step | None:
    """Open (case None and a deviation), advance (active case) or None; ValueError on a resolved or already-evaluated case."""

def mark_reported(case: Case, snapshot_id: str) -> Case:
    """Store state and current severity as last reported, and empty the max (Q-28)."""

# cases/registry.py
SCHEMA_VERSION: Final = 1
_SCHEMA: Final = """..."""                          # DDL below, run with executescript on a new file

class CaseRepository(Protocol):
    """What CaseTracker needs from the registry."""
    def current_snapshot(self) -> str | None: ...
    def current_unit(self) -> int | None: ...      # token of the open unit of work; new on every processing entry
    def active_cases(self) -> tuple[Case, ...]: ...
    def get_case(self, case_id: str) -> Case | None: ...
    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]: ...
    def save_case(self, case: Case, row: CaseHistoryRow) -> None: ...
    def update_case(self, case: Case) -> None: ...

class _Session:
    """Shared connection and open unit of work; owned by SqliteRegistry."""
    conn: sqlite3.Connection
    open: tuple[str, int] | None                    # (snapshot_id, seq) of the open unit of work
    unit: int | None                                # in-process counter bumped on every processing entry; never persisted
    def require_open(self, snapshot_id: str) -> int: ...   # the single write guard; returns seq

class SqliteRegistry:
    """Single-writer SQLite registry; satisfies ProcessedStore structurally."""
    cases: SqliteCaseRepository
    releases: SqliteReleaseStore
    def __init__(self, path: str | Path) -> None: ...   # ":memory:" or a file; ValueError on another schema version
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(self, *exc: object) -> None: ...       # closes

    # ProcessedStore (spec 002), unchanged signatures
    def get_hash(self, snapshot_id: str) -> str | None: ...
    def known_units(self) -> Mapping[str, Combination]: ...
    def record_anomaly(self, anomaly: Anomaly) -> None: ...      # outside processing only; INSERT OR IGNORE
    @contextmanager
    def processing(self, commit: SnapshotCommit) -> Iterator[None]: ...

    def current_snapshot(self) -> str | None: ...                # snapshot of the open unit of work
    def current_unit(self) -> int | None: ...                    # token of the open unit of work
    def recorded_anomalies(self) -> tuple[Anomaly, ...]: ...     # insertion order

class SqliteCaseRepository:
    """Cases and history on the registry's session; satisfies CaseRepository."""
    def __init__(self, session: _Session) -> None: ...
    def current_snapshot(self) -> str | None: ...
    def current_unit(self) -> int | None: ...
    def active_cases(self) -> tuple[Case, ...]: ...              # sorted in Python by all_combinations() index
    def get_case(self, case_id: str) -> Case | None: ...
    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]: ...   # processing order (seq)
    def save_case(self, case: Case, row: CaseHistoryRow) -> None: ...    # guarded; upsert case and row
    def update_case(self, case: Case) -> None: ...               # guarded; report baseline only, no history row

class SqliteReleaseStore:
    """Released units on the registry's session (FR-05, Q-20)."""
    def __init__(self, session: _Session) -> None: ...
    def record_releases(self, snapshot: Snapshot) -> None: ...   # guarded
    def released_so_far(self) -> tuple[ReleasedUnit, ...]: ...   # by processing seq, then list index

# cases/tracker.py
@dataclass(frozen=True)
class TrackedEvent:
    case_id: str
    event: CaseEvent

@dataclass(frozen=True)
class CaseDelta:
    """Lifecycle outcome of one snapshot, for spec 004; the last one for a snapshot wins (Q-27)."""
    snapshot_id: str
    events: tuple[TrackedEvent, ...]        # all_combinations() order, then CaseEvent order
    cases: tuple[Case, ...]                 # every case evaluated at this snapshot, resolved ones included

class CaseTracker:
    def __init__(self, repo: CaseRepository, resolution: ResolutionThresholds) -> None: ...
    def track(
        self,
        snapshot_id: str,
        metrics: Mapping[Combination, CombinationMetrics],
        raises: frozenset[Combination],
    ) -> CaseDelta: ...
    def mark_reported(self, case_id: str, snapshot_id: str) -> None: ...

# config.py
class Settings(BaseSettings):
    ...
    @property
    def registry_path(self) -> Path:
        """Registry SQLite file, derived from output_dir."""
        return self.output_dir / "registry.sqlite3"
```

### `step` algorithm
1. **No case.** If `case is None`:
   - If `not obs.metrics.has_deviation`, return `None` (E2).
   - Otherwise `eff = effective_severity(min, raised)` and `state = next_state(None, critical=eff is CRITICAL, resolvable=False)` (Q-08).
   - Streak 0, `max = eff`, `case_id = case_id_for(obs.snapshot_id, combination)`.
   - Events: `opened`, plus `escalated` when the state is `escalado`.
2. **Guards.** Raise `ValueError` naming the case if `case.state` is `resuelto`, or if `case.last_snapshot_id == obs.snapshot_id` (E18).
3. `eff = effective_severity(...)`, `streak = 0 if has_deviation else case.clean_streak + 1`.
4. `resolvable = streak >= resolution.snapshots_sin_desvio and not obs.raised` (§3, Q-25).
5. `new_state = next_state(case.state, critical=eff is CRITICAL, resolvable=resolvable)`.
6. Events:
   - `escalated` if `new_state` is `escalado` and `case.state` is not;
   - `severity_changed` if `eff != case.current_severity`;
   - `resolved` if `new_state` is `resuelto`.
7. The new `Case`: `max = eff if case.max_severity_since_report is None else max(case.max_severity_since_report, eff)` (Q-28), `resolved_at = obs.snapshot_id` if resolved, and the last reported fields copied unchanged.
8. The history row is built from `obs.metrics` and the values above.

### `mark_reported` (pure)
A validated copy of `case` (never a bare `model_copy`, which skips the `Case` validator; the same applies to every `Case` built in `step`) with `last_reported_at = snapshot_id`, `last_reported_state = case.state`, `last_reported_severity = case.current_severity` and `max_severity_since_report = None`. Every other field is unchanged, including `last_snapshot_id` (E24b).

### `processing` algorithm (`SqliteRegistry`)
1. If a unit of work is open, raise `RuntimeError` naming it.
2. If `get_hash(commit.snapshot_id)` is not `None`, raise `ValueError` naming the snapshot. No transaction has been opened.
3. `BEGIN IMMEDIATE`. Set `seq = COALESCE(MAX(seq), 0) + 1` from `processed_snapshots`, `session.open = (commit.snapshot_id, seq)`, and bump the in-process `session.unit` counter.
4. `yield`. Writes in the block go through `session.require_open` and stamp rows with `seq`.
5. **On any `BaseException`** from the block: `ROLLBACK`, then re-raise.
6. **On a clean exit:**
   - insert into `processed_snapshots` (`snapshot_id`, `content_hash`, `seq`);
   - `INSERT OR IGNORE` each commit anomaly;
   - `INSERT OR IGNORE` each `new_units` entry;
   - `COMMIT`.
   If any of these raise, `ROLLBACK` and re-raise.
7. `finally`: `session.open = None`.

`session.require_open(snapshot_id)` raises `RuntimeError` when no unit of work is open, `ValueError` naming both ids when `snapshot_id` differs, and otherwise returns `seq`. It is the only write guard; both collaborators call it.

The connection uses explicit transaction control (`sqlite3.connect(path, autocommit=True)` with explicit `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`) and `PRAGMA foreign_keys = ON`.

### Case writes (`SqliteCaseRepository`)
- **`save_case(case, row)`:**
  0. Re-validate `case` (a `Case` built with `model_construct` is rejected) and require `row.case_id == case.case_id` (`ValueError` naming both), before any write.
  1. If `case.last_snapshot_id != row.snapshot_id`, raise `ValueError` naming both (E23h).
  2. `seq = session.require_open(row.snapshot_id)` (E23a, E23d).
  3. `INSERT INTO cases … ON CONFLICT (case_id) DO UPDATE SET …` every column but `case_id`.
  4. `INSERT INTO case_history … ON CONFLICT (case_id, snapshot_id) DO UPDATE SET …` every column but the key and `seq`.
  5. An `IntegrityError` from `one_active_case_per_combination` becomes `ValueError` naming the combination (E4).
  - Never `INSERT OR REPLACE`: it deletes and reinserts the row, which breaks the foreign keys spec 008 will hang on `cases`.
- **`update_case(case)`:** `session.require_open(case.last_reported_at)` (a `None` there is a `ValueError`), then `UPDATE cases SET last_reported_at, last_reported_state, last_reported_severity, max_severity_since_report WHERE case_id = ?`. Zero rows updated raises `ValueError` naming the case (E23g). No other column changes; no history row.
- **Reads** rebuild `Case` and `CaseHistoryRow` from stored `minimum_severity` and `raised`. The stored `current_severity` and `effective_severity` columns exist for querying only and are never read back into the models.
- **`active_cases()`** selects `WHERE state <> 'resuelto'` and sorts in Python by the combination's index in `all_combinations()`. Never `ORDER BY modelo, mercado`: SQLite's byte-wise text order is not the enum declaration order that `all_combinations()` follows.

### `CaseTracker.track` algorithm
1. If `repo.current_snapshot() != snapshot_id`, raise `RuntimeError` (E29c). The check runs before any read, so a call with nothing to write still fails.
2. **Pre-snapshot state (Q-27).** The memo is `(unit, snapshot_id, metrics, active_before, marked)`, keyed by `repo.current_unit()`. If it belongs to the current unit: a non-empty `marked` raises `RuntimeError` (track after `mark_reported`); `metrics` different from the stored ones (by value) raises `ValueError`; otherwise reuse `active_before`. If it belongs to another unit (new snapshot, or a retry after a rollback), read `active = repo.active_cases()` and replace the memo.
3. `by_combo = {c.combination: c for c in active}`. Any active combination missing from `metrics` raises `ValueError` naming the case (E29d).
4. For each `combo` in `all_combinations()` that is in `metrics`:
   - `s = step(by_combo.get(combo), Observation(snapshot_id, metrics[combo], combo in raises), resolution)`.
   - If `s` is not `None`: `repo.save_case(s.case, s.history)`, then collect `s.case` and a `TrackedEvent` per event.
5. Return the `CaseDelta`.

With the same `metrics`, every call for a snapshot evaluates the same combinations and produces the same case IDs (openings depend on the minimum only), so each upsert overwrites exactly the rows the earlier call wrote. A retry after a rollback runs in a new unit, so it starts a fresh memo and no stale `marked` set blocks it.

### `CaseTracker.mark_reported` algorithm
1. If `repo.current_snapshot() != snapshot_id`, raise `RuntimeError` (E24c).
2. `case = repo.get_case(case_id)`; `None` raises `ValueError` naming it (E24c).
3. An active case with `last_snapshot_id != snapshot_id` (not tracked yet at this snapshot) raises `ValueError` naming it. A resolved case is allowed (E24b).
4. `repo.update_case(lifecycle.mark_reported(case, snapshot_id))`, and add `case_id` to the memo's `marked` set for the current unit.

### Schema sketch (`_SCHEMA` in `cases/registry.py`)
```sql
CREATE TABLE processed_snapshots (
    snapshot_id  TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    seq          INTEGER NOT NULL UNIQUE              -- processing order
);
CREATE TABLE anomalies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,    -- insertion order
    kind        TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    detail      TEXT NOT NULL,
    UNIQUE (kind, snapshot_id, detail)
);
CREATE TABLE known_units (
    unidad_id TEXT PRIMARY KEY,                       -- first sighting wins (INSERT OR IGNORE)
    modelo    TEXT NOT NULL,
    mercado   TEXT NOT NULL
);
CREATE TABLE released_units (
    seq         INTEGER NOT NULL,                     -- processing seq of the snapshot
    idx         INTEGER NOT NULL,                     -- position in liberadas
    snapshot_id TEXT NOT NULL,
    unidad_id   TEXT NOT NULL,
    modelo      TEXT NOT NULL,
    mercado     TEXT NOT NULL,
    hora        TEXT NOT NULL,                        -- ISO 8601
    PRIMARY KEY (seq, idx)
);
CREATE TABLE cases (
    case_id                   TEXT PRIMARY KEY,
    modelo                    TEXT NOT NULL,
    mercado                   TEXT NOT NULL,
    opened_at                 TEXT NOT NULL,
    state                     TEXT NOT NULL,
    minimum_severity          TEXT NOT NULL,
    raised                    INTEGER NOT NULL,
    current_severity          TEXT NOT NULL,          -- derived; for queries only
    max_severity_since_report TEXT,                   -- NULL right after a mark (Q-28)
    clean_streak              INTEGER NOT NULL,
    last_snapshot_id          TEXT NOT NULL,
    last_reported_at          TEXT,
    last_reported_state       TEXT,
    last_reported_severity    TEXT,
    resolved_at               TEXT
);
CREATE UNIQUE INDEX one_active_case_per_combination
    ON cases (modelo, mercado) WHERE state <> 'resuelto';   -- FR-12 backstop
CREATE TABLE case_history (
    case_id            TEXT NOT NULL REFERENCES cases (case_id),
    snapshot_id        TEXT NOT NULL,
    seq                INTEGER NOT NULL,
    state              TEXT NOT NULL,
    minimum_severity   TEXT NOT NULL,
    raised             INTEGER NOT NULL,
    effective_severity TEXT NOT NULL,                 -- derived; for queries only
    gap_units          REAL NOT NULL,
    gap_pct            REAL,
    delay_days         REAL,
    bottleneck         TEXT,
    clean_streak       INTEGER NOT NULL,
    PRIMARY KEY (case_id, snapshot_id)
);
```
- The schema lives in code as `_SCHEMA: Final`, so there is no package-data question. The version is `SCHEMA_VERSION`.
- On open:
  - `user_version == 0`: run `_SCHEMA` and set `PRAGMA user_version = SCHEMA_VERSION` in one transaction.
  - `user_version == SCHEMA_VERSION`: use the file as is.
  - Anything else: close the connection and raise `ValueError` (E21b).

## Design notes
- **Reconciliation with spec 002, in three points:**
  1. **A single unit of work.** The draft's `unit_of_work(snapshot_id)` and `mark_processed` are gone. `processing(commit)` from spec 002's `ProcessedStore` is the only transaction boundary. It opens the SQLite transaction on entry, shares it with every registry write of the snapshot, and records hash, anomalies and units on a clean exit (Q-23, ADR-0008).
  2. **Released units, reduced (old T16).** `known_units()` is identity (first sighting). Progress follows first *release* (Q-20, 002 E21). So releases get their own table in release order, and `count_progress` stays the one place that deduplicates.
  3. **An anomalies table** with `UNIQUE (kind, snapshot_id, detail)` and `INSERT OR IGNORE`, so rerunning the Q-10 skip path does not duplicate. This closes 002's open note.
- **Registry split.** `SqliteRegistry` owns the connection, `processing`, the schema and the `ProcessedStore` methods. Each table group is a collaborator on the shared `_Session`: `registry.cases` (`SqliteCaseRepository`) and `registry.releases` (`SqliteReleaseStore`). The single write guard is `_Session.require_open`. Spec 008 adds `registry.causes` the same way. The tracker receives `registry.cases`, never the whole registry.
- **Structural typing, no `runner` import.** `SqliteRegistry` satisfies `ProcessedStore` structurally. `cases` never imports `runner`. `SnapshotCommit`, `Anomaly`, `ReleasedUnit` and `Snapshot` live in `domain` (spec 002 put them there for this reason). A mypy-checked assignment in the contract test proves conformance; another proves `SqliteCaseRepository` is a `CaseRepository`.
- **`store_factory`:** the contract test's factory takes no arguments, so it gets `lambda: SqliteRegistry(":memory:")` with id `sqlite_memory`. The in-memory-only `recorded_anomalies` tests stay in-memory-specific. `SqliteRegistry` has its own `recorded_anomalies()` for its own tests (E20).
- **Where the lifecycle runs.**
  - 003 delivers the pure lifecycle (`cases/lifecycle.py`) and `CaseTracker`, a thin service that reads active cases, calls `step` and writes.
  - It is **not** a `SnapshotPipeline`. Spec 004's `ThresholdPipeline` (`runner/pipeline.py`) composes `releases.released_so_far()` → `compute_metrics` → `releases.record_releases` → `tracker.track` (re-run by spec 008 when raises change) → notices from the last delta → `tracker.mark_reported`.
  - 003's integration test uses a minimal test pipeline in `tests/` with the first four steps.
- **State machine as one pure function.** `next_state` holds the whole §3 table, opening included (`current = None`, Q-08). It replaces the per-state behavior classes of the earlier draft: the table is small, a `match` reads like `criterio.md`, and a parametrized test covers every row. `docs/STRUCTURE.md` names the pattern "State machine (pure transition function)".
- **Effective severity in one place.** `effective_severity` in `domain/cases.py` computes it, and `Case.current_severity` and `CaseHistoryRow.effective_severity` are `@computed_field`s over it, so an inconsistent case cannot be built. The lifecycle and the tracker pass `raised` and never compute severities. SQLite stores the derived values for querying, but reads rebuild them from `(minimum_severity, raised)`.
- **`mark_reported` in the tracker.** The registry stores; the tracker applies the pure `lifecycle.mark_reported`. So `cases/registry.py` never imports `lifecycle`, and all case logic stays in `lifecycle` + `tracker`.
- **Write guards in the registry, not the tracker.** Every write goes through `_Session.require_open`, so a write outside `processing`, or for another snapshot, fails loudly (E23). The tracker adds one explicit check up front, so it also fails when it would write nothing (E29c, E24c).
- **Determinism (NFR-04).**
  - Case IDs derive from the opening snapshot and the combination.
  - Events, cases and `active_cases()` follow `all_combinations()` order, sorted in Python.
  - History and releases follow processing `seq`.
  - Nothing reads the wall clock.
- **`released_so_far()` inside a unit of work** sees the current snapshot's releases once `record_releases` has run, because it is the same connection. The pipeline reads before it records (E27). Reading after recording would still give the same progress, because the duplicates come after the first occurrence in `chain(released_so_far, liberadas)`.
- **Dependency rule.** Per module, `cases` imports only `plant_monitor.domain` and `plant_monitor.metrics.thresholds` (for `ResolutionThresholds`), plus itself and the standard library (`sqlite3`). It never imports `runner`, `agents`, `mcp_server`, `anthropic` or `mcp`, nor other `metrics` modules such as `metrics.engine`. The existing `layer_offenders` helper works at subpackage level (it would accept any `metrics.*`), so the test adds a module-level check.
- **For spec 004 (recorded here, not solved):**
  - Notice delivery "after commit" (Q-23) needs either an outbox table written inside `processing` or a post-commit hook in the runner, because `process()` runs inside `processing`.
  - `runner/pipeline.py` will import `cases`, so T19 adds `cases` to the runner's allowed imports in `docs/STRUCTURE.md`.
- **ADRs.** ADR-0003 (SQLite, single writer, processed mark sharing the transaction) and ADR-0008 (unit of work over `SnapshotCommit`) cover this design. No new ADR. The next free number is 0010.

## Test strategy
- **Domain** (`tests/unit/domain/test_cases.py`): `CaseState` and `CaseEvent` values, `case_id_for`, E6 (`effective_severity` and the computed fields), and the `Case`/`CaseHistoryRow` validators (T1).
- **Lifecycle** (`tests/unit/cases/test_lifecycle.py`): the parametrized `next_state` table, E1–E3, E4 (lifecycle part), E7–E15, E16 (pure part), E17, E18 and E32. A `metrics_with(minimum, **values)` builder gives synthetic `CombinationMetrics`. Thresholds come from `tests/fixtures/plant/umbrales.yaml`, never a literal 2.
- **Registry** (`tests/unit/cases/test_registry.py`): E4 (registry part), E20–E23, E25–E27, on `SqliteRegistry(":memory:")`, with `tmp_path` files for E20c, E21, E26 and E27 (reopen). Each test closes its registry, because Windows will not delete an open file in `tmp_path`.
- **Contract** (`tests/unit/runner/test_store_contract.py`): add `SqliteRegistry` to `store_factory` (E19) and a mypy-checked `store: ProcessedStore = SqliteRegistry(":memory:")`.
- **Tracker** (`tests/unit/cases/test_tracker.py`): E5, E16, E24, E29, E31, on `SqliteRegistry(":memory:")` inside `processing`.
- **Integration** (`tests/integration/test_registry_runner.py`): E30. It uses `run_series`, the fixture plant files, synthetic snapshots written with `tests/builders.py`, and a `TrackingPipeline` test class that can raise after `track` on a given snapshot.
- **Settings** (`tests/test_config.py`): E28.
- **Import boundaries** (`tests/unit/test_import_boundaries.py`): `cases` in the `anthropic`/`mcp` scan and a module-level `cases` check (T2); a runtime probe for `plant_monitor.cases.tracker` (T16).
- **Not covered:** real-data runs (spec 005 evals), raises from logbooks (spec 008), and Q-29.

## Risks
- **Effective severity computed in two places would drift.** It lives only in `domain/cases.py`, and the models derive it.
- **A write outside the unit of work** would survive a rollback and break resume (NFR-10). Every write goes through the one guard (E23), and E25 and E30 prove rollback and resume end to end.
- **`INSERT OR REPLACE` on upsert** would delete and reinsert case rows and break spec 008's foreign keys. The plan mandates `ON CONFLICT … DO UPDATE`.
- **Release order.** If `released_so_far()` were unordered, a unit released under two combinations could count in the wrong one (Q-20). Rows are keyed by `(seq, idx)` and read in that order (E27).
- **Same snapshot evaluated twice.** A re-run re-evaluates from the pre-snapshot state (E31); `step` still rejects stepping a case already at N (E18a), so a streak is never counted twice.
- **Re-run misuse (Q-27).** Checked in code after review: the tracker memo `(unit token, snapshot_id, metrics, active_before, marked)` is keyed by `SqliteRegistry.current_unit()` (exposed on `CaseRepository`), so a retry after rollback starts fresh; different `metrics` on a re-run → `ValueError`; `track` after `mark_reported` in the same unit → `RuntimeError`; `mark_reported` on an active case not tracked at that snapshot → `ValueError`. Still a caller contract: notices come only from the last delta.
- **Q-29** (raise at N on a case resolved at N) is open for spec 008.
- **Q-16** can falsely resolve a case on a plan-0 shift. It does not occur in T01–T21; revisit in W5.
- **Schema changes** after 003 (spec 008 adds cause tables) need a `SCHEMA_VERSION` bump. With no migrations, an old file is rejected (E21b) and the run starts from a fresh file.
- **Spec 004 delivery after commit** needs an outbox or a post-commit hook (see Design notes).
- **Spec 004 must mark only cases resolved within the current shift.** `mark_reported` accepts any resolved case, so re-marking one resolved in an earlier shift would empty its max again (found by `/verify-criteria`).
