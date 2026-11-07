# 004 · Notices and shift reports — Plan

## Modules

| File | Responsibility |
|---|---|
| `domain/causes.py` | **New.** `CauseCategory` (§6 catalog, Spanish values), `Cause` (`categoria`, `etapa: Stage \| None`), `Evidence` (`bitacora`, `fragmento`). Spec 008 reuses them. |
| `domain/notices.py` | **New.** `NoticeType`, `Origin`, `Reason`, `notice_id_for`, `report_id_for`, `Notice`, `ActiveCaseRow`, `ShiftReport`, `PendingDelivery`. Pure types with the contract validators. |
| `cases/facts.py` | **New.** `CaseFacts`: a case, its current metrics (or none) and its cause row (Q-32). Imports only `domain`. |
| `cases/novelty.py` | **New.** `NewsReason`, `NewsItem`, `case_order`, `alerted_case_ids`, `alerts_for`, `news_reasons`, `expected_news`, `report_set`, `active_rows`. Pure; spec 010's hooks import it. `CaseDelta` is imported only under `TYPE_CHECKING`, so importing it never loads the tracker, the registry or `sqlite3`. |
| `cases/templates.py` | **New.** Spanish `texto` templates and number formatting. Pure; imports `domain`, `cases.facts` and `cases.novelty`. |
| `cases/notice_builder.py` | **New.** `reasons_for`, `origin_for`, `default_cause`, `case_notice`, `ShiftClose`, `SnapshotNotices`, `build_snapshot_notices`. Pure. |
| `cases/registry/` | **T0** package split (`schema.py`, `session.py`, `sqlite.py`, `cases_repo.py`, `releases.py`, re-exported from `__init__.py`); the session class becomes `Session` (package-internal, no underscore, since sibling modules import it). **T8:** `schema.py` gets `SCHEMA_VERSION = 2` and the `notices` table; `session.py` adds `Session.savepoint(name)`; new `notices.py` (`SqliteNoticeStore`); `cases_repo.py` adds `resolved_unreported()` and `last_deviation_row()` to `SqliteCaseRepository` only (`CaseRepository`, the tracker's port, is unchanged); `sqlite.py` exposes `registry.notices`. |
| `notify/__init__.py` | **New.** Package marker; no re-exports. |
| `notify/port.py` | **New.** `Notifier` protocol. |
| `notify/console.py`, `notify/file.py`, `notify/composite.py` | **New.** `ConsoleNotifier`, `FileNotifier`, `CompositeNotifier`. |
| `runner/ports.py` | Adds the `PostCommit` protocol. |
| `runner/series.py` | `run_series(..., *, post_commit=None)`; calls it before the upfront checks and after each committed snapshot. |
| `runner/outbox.py` | **New.** `PendingNotices` protocol and `OutboxDispatcher` (implements `PostCommit`). |
| `runner/pipeline.py` | **New.** `ReleaseLog`, `NoticeSink` and `NoticeCaseReader` protocols; module-level `shift_close` and `deviation_rows`; `ThresholdPipeline` (implements `SnapshotPipeline`). |
| `config.py` | `Settings.notices_dir` property (`output_dir / "notices"`). |

- No change to `cases/lifecycle.py`, `cases/tracker.py` or `metrics/*`.
- ADR-0010 (`docs/adr/0010-notice-outbox-delivery-after-commit.md`) records the transactional outbox.

## Types and interfaces
```python
# domain/causes.py
class CauseCategory(StrEnum):
    """Cause catalog of §6; values are the data contract's."""
    LINE_STOP = "parada_de_linea"
    MISSING_PARTS = "faltante_de_piezas"
    REWORK = "retrabajo"
    QUALITY_HOLD = "retencion_de_calidad"
    ABSENTEEISM = "ausentismo"
    UNDECLARED = "no_declarada"

class Cause(FrozenModel):
    """Category and stage of a cause; stage is None when the data show none (Q-17)."""
    categoria: CauseCategory
    etapa: Stage | None

class Evidence(FrozenModel):
    """A logbook citation: logbook id and verbatim fragment."""
    bitacora: str
    fragmento: str

# domain/notices.py
class NoticeType(StrEnum):
    """Notice types of the contract (FR-25, Q-14)."""
    ALERT = "alerta_inmediata"
    SHIFT_REPORT = "informe_de_turno"
    NO_NOTICE = "sin_aviso"

class Origin(StrEnum):
    THRESHOLD = "umbral"
    AGENT = "agente"

class Reason(StrEnum):
    """'motivo' values; declaration order is list order (Q-31)."""
    GAP = "gap"
    DELAY = "retraso"
    LOGBOOK = "bitacora"

def notice_id_for(snapshot_id: str, tipo: NoticeType, case_id: str) -> str:
    """'<snapshot_id>-<tipo>-<case_id>', e.g. 'S003-alerta_inmediata-S001-Sedán-Local'."""

def report_id_for(turno_id: str) -> str:
    """'<turno_id>-informe', e.g. 'T01-informe'."""

class Notice(FrozenModel):
    """One per-case notice decision in the output contract (FR-25); never model_copy(update=...)."""
    notice_id: str
    snapshot_id: str
    case_id: str
    modelo: Model
    mercado: Market
    tipo: NoticeType
    severidad: Severity                 # current (effective) severity
    severidad_maxima: Severity          # max since the previous report
    estado: CaseState
    origen: Origin
    motivo: tuple[Reason, ...]
    causa: Cause
    evidencia: tuple[Evidence, ...]
    texto: str
    # Validators (ValueError): notice_id == notice_id_for(...); motivo unique and in Reason order;
    # origen is AGENT iff LOGBOOK in motivo; motivo empty iff severidad is NONE;
    # severidad_maxima >= severidad; ALERT implies estado ESCALATED and severidad CRITICAL.

class ActiveCaseRow(FrozenModel):
    """One row of a report's 'casos_activos' (FR-23); values of the current snapshot."""
    case_id: str
    modelo: Model
    mercado: Market
    gap_unidades: float
    gap_pct: float | None
    retraso_dias: float | None
    severidad: Severity
    severidad_maxima: Severity
    estado: CaseState                   # validator: active states only
    etapa_cuello: Stage | None          # current bottleneck, not the cause's stage

class ShiftReport(FrozenModel):
    """End-of-shift report (FR-22); its JSON is the contract spec 011 validates."""
    turno_id: str
    snapshot_id: str
    novedades: tuple[Notice, ...]
    casos_activos: tuple[ActiveCaseRow, ...]
    # Validators (ValueError): every news item is SHIFT_REPORT with this snapshot_id;
    # case_id unique within novedades and within casos_activos.

@dataclass(frozen=True)
class PendingDelivery:
    """A stored notice waiting for delivery."""
    notice_id: str
    item: Notice | ShiftReport

# cases/facts.py
@dataclass(frozen=True)
class CaseFacts:
    """A case with what its notices need: current metrics and the cause row of Q-32."""
    case: Case
    current: CombinationMetrics | None  # this snapshot's metrics; None for a case not evaluated at it
    cause_row: CaseHistoryRow           # the case's last history row with a deviation (Q-32)
    # __post_init__ (ValueError naming the case): cause_row.case_id == case.case_id;
    # cause_row.minimum_severity >= MEDIUM; current, if set, is for case.combination.

    @property
    def cause_stage(self) -> Stage | None: ...   # cause_row.bottleneck
    @property
    def cause_gap_only(self) -> bool: ...        # known only if cause_row is at this snapshot; else False

# cases/novelty.py
class NewsReason(StrEnum):
    """Why a case is news (§4); declaration order is list order; not part of the contract."""
    NEW = "new"
    RESOLVED = "resolved"
    STATE_CHANGED = "state_changed"
    SEVERITY_CHANGED = "severity_changed"
    PEAK = "peak"

@dataclass(frozen=True)
class NewsItem:
    case: Case
    reasons: tuple[NewsReason, ...]     # never empty

def case_order(case: Case) -> tuple[int, str]: ...      # (all_combinations() index, opened_at)
def alerted_case_ids(delta: CaseDelta) -> tuple[str, ...]: ...      # 'escalated' events, delta order
def alerts_for(delta: CaseDelta, metrics: Mapping[Combination, CombinationMetrics]) -> tuple[Case, ...]: ...
def news_reasons(case: Case) -> tuple[NewsReason, ...]: ...
def expected_news(cases: Iterable[Case]) -> tuple[NewsItem, ...]: ...    # sorted by case_order
def report_set(evaluated: Iterable[Case], resolved_unreported: Iterable[Case]) -> tuple[Case, ...]: ...
def active_rows(cases: Iterable[Case], metrics: Mapping[Combination, CombinationMetrics]) -> tuple[ActiveCaseRow, ...]: ...

# cases/templates.py
def format_units(value: float) -> str: ...      # '−12 u', '−2,5 u', '+6 u', '0 u'
def format_pct(value: float | None) -> str: ... # '−38 %', 'sin plan en el turno'
def format_delay(days: float | None) -> str: ...
def cause_text(cause: Cause, facts: CaseFacts) -> str: ...
def alert_text(facts: CaseFacts, snapshot_id: str, motivo: tuple[Reason, ...], cause: Cause) -> str: ...
def news_text(facts: CaseFacts, reasons: tuple[NewsReason, ...], cause: Cause) -> str: ...
def silent_text(case: Case) -> str: ...

# cases/notice_builder.py
def reasons_for(facts: CaseFacts) -> tuple[Reason, ...]: ...     # Q-31; ValueError if current metrics are needed and missing
def origin_for(motivo: tuple[Reason, ...]) -> Origin: ...
def default_cause(stage: Stage | None) -> Cause: ...             # no_declarada (§6, Q-17)
def case_notice(tipo: NoticeType, facts: CaseFacts, snapshot_id: str) -> Notice: ...
    # ValueError: ALERT without current metrics; SHIFT_REPORT for a case that is not news; NO_NOTICE for one that is

@dataclass(frozen=True)
class ShiftClose:
    """Closing-snapshot input: the shift and the registry's resolved-unreported cases, unfiltered."""
    turno_id: str
    resolved_unreported: tuple[Case, ...]

@dataclass(frozen=True)
class SnapshotNotices:
    """Everything one snapshot decides."""
    decisions: tuple[Notice, ...]   # alerts first, then one non-alert decision per case in case_order
    report: ShiftReport | None      # only at a closing snapshot
    to_mark: tuple[str, ...]        # the report set, in case_order; empty at a mid snapshot

def build_snapshot_notices(
    delta: CaseDelta,
    metrics: Mapping[Combination, CombinationMetrics],
    cause_rows: Mapping[str, CaseHistoryRow],    # last row with a deviation per case_id (Q-32)
    close: ShiftClose | None,
) -> SnapshotNotices: ...

# cases/registry/schema.py
SCHEMA_VERSION: Final = 2

# cases/registry/session.py
class Session:
    """Shared connection and open unit of work; owned by SqliteRegistry (was '_Session')."""
    ...                                                   # 003 members unchanged
    @contextmanager
    def savepoint(self, name: str) -> Iterator[None]: ... # SAVEPOINT; RELEASE; on error ROLLBACK TO + RELEASE

# cases/registry/cases_repo.py
class SqliteCaseRepository:
    ...                                                   # 003 methods unchanged; CaseRepository unchanged
    def resolved_unreported(self) -> tuple[Case, ...]: ...                 # resuelto, not reported as resuelto; case_order
    def last_deviation_row(self, case_id: str) -> CaseHistoryRow | None: ... # latest seq with minimum >= media

# cases/registry/notices.py
class SqliteNoticeStore:
    """Notice decisions and the delivery outbox on the registry's session (ADR-0010)."""
    def __init__(self, session: Session) -> None: ...
    def save(self, snapshot_id: str, decisions: Sequence[Notice], report: ShiftReport | None) -> None: ...  # guarded
    def for_snapshot(self, snapshot_id: str) -> tuple[Notice | ShiftReport, ...]: ...   # save order
    def pending(self) -> tuple[PendingDelivery, ...]: ...         # outside processing only; (seq, idx)
    def mark_delivered(self, notice_id: str, at: datetime) -> None: ...   # outside processing; aware 'at'
    def delivered_at(self, notice_id: str) -> datetime | None: ...

# cases/registry/sqlite.py
class SqliteRegistry:
    cases: SqliteCaseRepository
    releases: SqliteReleaseStore
    notices: SqliteNoticeStore                            # new collaborator on the shared session

# notify/port.py
class Notifier(Protocol):
    """Output channel for delivered notices (FR-26)."""
    def alert(self, notice: Notice) -> None: ...
    def report(self, report: ShiftReport) -> None: ...

# notify/console.py, notify/file.py, notify/composite.py
class ConsoleNotifier:
    def __init__(self, stream: TextIO | None = None) -> None: ...     # None means sys.stdout at call time
class FileNotifier:
    def __init__(self, directory: Path) -> None: ...                  # informe_<turno_id>.json, alertas.jsonl
class CompositeNotifier:
    def __init__(self, notifiers: Sequence[Notifier]) -> None: ...

# runner/ports.py
class PostCommit(Protocol):
    """Work the runner triggers outside any unit of work: at run start and after each commit."""
    def after_commit(self) -> None: ...

# runner/outbox.py
class PendingNotices(Protocol):
    """What the dispatcher needs from the notice store; SqliteNoticeStore satisfies it structurally."""
    def pending(self) -> tuple[PendingDelivery, ...]: ...
    def mark_delivered(self, notice_id: str, at: datetime) -> None: ...

class OutboxDispatcher:
    """Delivers pending notices in order after each commit (ADR-0010); implements PostCommit."""
    def __init__(
        self, notices: PendingNotices, notifier: Notifier, clock: Callable[[], datetime] = _utc_now
    ) -> None: ...
    def after_commit(self) -> None: ...     # flush(), never raises Exception
    def flush(self) -> int: ...             # number delivered in this flush

# runner/pipeline.py
class ReleaseLog(Protocol):
    def released_so_far(self) -> tuple[ReleasedUnit, ...]: ...
    def record_releases(self, snapshot: Snapshot) -> None: ...

class NoticeSink(Protocol):
    def save(self, snapshot_id: str, decisions: Sequence[Notice], report: ShiftReport | None) -> None: ...

class NoticeCaseReader(Protocol):
    """Case reads the notice step needs beyond the tracker's port; SqliteCaseRepository satisfies it."""
    def resolved_unreported(self) -> tuple[Case, ...]: ...
    def last_deviation_row(self, case_id: str) -> CaseHistoryRow | None: ...

def shift_close(shift: Shift, position: ShiftPosition, reader: NoticeCaseReader) -> ShiftClose | None:
    """At a closing snapshot, the shift and its raw resolved-unreported cases; None at a mid snapshot."""

def deviation_rows(case_ids: Iterable[str], reader: NoticeCaseReader) -> dict[str, CaseHistoryRow]:
    """Last history row with a deviation per case (Q-32); ValueError naming a case that has none."""

class ThresholdPipeline:
    """Threshold-only SnapshotPipeline: metrics, lifecycle and notice decisions inside the unit of work."""
    def __init__(
        self,
        ctx: PlantContext,
        releases: ReleaseLog,
        cases: CaseRepository,
        reader: NoticeCaseReader,
        notices: NoticeSink,
    ) -> None: ...                          # builds CaseTracker(cases, ctx.thresholds.resolucion)
    @classmethod
    def from_registry(cls, registry: SqliteRegistry, ctx: PlantContext) -> ThresholdPipeline: ...
        # passes registry.cases as both 'cases' and 'reader'
    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None: ...

# runner/series.py
def run_series(
    arrivals: Sequence[Arrival],
    shifts: Sequence[Shift],
    store: ProcessedStore,
    pipeline: SnapshotPipeline,
    *,
    post_commit: PostCommit | None = None,
) -> RunSummary: ...

# config.py
class Settings(BaseSettings):
    @property
    def notices_dir(self) -> Path:
        """Directory of the file notifier, derived from output_dir."""
        return self.output_dir / "notices"
```

### `ThresholdPipeline.process`
```python
def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
    # Inside the runner's 'processing' unit of work: database writes only, no external I/O.
    sid = snapshot.snapshot_id
    metrics = compute_metrics(snapshot, self._releases.released_so_far(), self._ctx)
    self._releases.record_releases(snapshot)
    delta = self._tracker.track(sid, metrics, frozenset())            # once; spec 008 adds raises
    close = shift_close(shift, position, self._reader)               # raw resolved_unreported(); None at mid
    ids = [case.case_id for case in delta.cases]
    if close is not None:
        ids += [case.case_id for case in close.resolved_unreported]
    rows = deviation_rows(ids, self._reader)                          # read after track: current rows included
    built = build_snapshot_notices(delta, metrics, rows, close)      # values before marking (FR-23)
    self._notices.save(sid, built.decisions, built.report)            # once per snapshot
    for case_id in built.to_mark:                                     # the report set only
        self._tracker.mark_reported(case_id, sid)
    # Outside the transaction: run_series calls post_commit.after_commit() after the commit,
    # and OutboxDispatcher delivers the pending alerts and report to the notifiers.
```

### `build_snapshot_notices` algorithm
1. `facts[id] = CaseFacts(case, metrics[case.combination], cause_rows[id])` for every case in `delta.cases` (`ValueError` naming the case if its metrics or cause row are missing).
2. `alerts_for(delta, metrics)`, in delta event order; one `case_notice(ALERT, facts[id], sid)` each.
3. Targets: at a mid snapshot, the delta cases. At a closing snapshot, `report_set(delta.cases, close.resolved_unreported)`; a target not in the delta gets `CaseFacts(case, None, cause_rows[id])`.
4. For each target in `case_order`:
   - skip it if it was alerted and `close is None` (mid snapshot: the alert is its only decision);
   - `case_notice(SHIFT_REPORT, f, sid)` if `news_reasons(f.case)` is not empty, else `case_notice(NO_NOTICE, f, sid)`.
   An alerted case is always news (it is new, or its normalized state changed), so at a closing snapshot it gets its news entry and never `sin_aviso`. A resolved-unreported case is always news (`resolved`).
5. At a closing snapshot: `novedades` = the `SHIFT_REPORT` decisions of step 4, in the same order; `casos_activos = active_rows(active delta cases, metrics)`; `report = ShiftReport(close.turno_id, sid, novedades, casos_activos)`; `to_mark` = the report set's IDs.
6. At a mid snapshot: `report = None`, `to_mark = ()`.

### Novelty
```python
def news_reasons(case: Case) -> tuple[NewsReason, ...]:
    """Every §4 reason that makes the case news against its last report, in NewsReason order."""
    reasons: list[NewsReason] = []
    reported = case.last_reported_at is not None
    if not reported:
        reasons.append(NewsReason.NEW)
    if case.state is CaseState.RESOLVED and case.last_reported_state is not CaseState.RESOLVED:
        reasons.append(NewsReason.RESOLVED)
    if reported and case.state.is_active and _norm(case.state) != _norm(case.last_reported_state):
        reasons.append(NewsReason.STATE_CHANGED)
    if reported and case.current_severity != case.last_reported_severity:
        reasons.append(NewsReason.SEVERITY_CHANGED)
    peak = case.max_severity_since_report
    if peak is not None and peak > case.current_severity:
        reasons.append(NewsReason.PEAK)
    return tuple(reasons)
# '_norm' maps OPEN and FOLLOW_UP to FOLLOW_UP; other states map to themselves.
```
- `report_set`: validate each `resolved_unreported` entry (`resuelto` and `last_reported_state != resuelto`, else `ValueError` naming it); build `{case_id: case}` from `resolved_unreported`, then overwrite with `evaluated`; return the values sorted by `case_order`.
- `alerts_for`: `alerted_case_ids(delta)` mapped to the delta's cases; `ValueError` naming a case whose combination is missing from `metrics`.

### `reasons_for` (Q-31)
1. `E = facts.case.current_severity`. If `E` is `ninguna`, return `()`.
2. If `facts.current` is `None`, raise `ValueError` naming the case.
3. `gap` if `current.gap_severity == E`; `retraso` if `current.delay_severity == E`; `bitacora` if `case.raised` and `case.minimum_severity < critica`.

### Cause and text (Q-17, Q-32)
- `case_notice` sets `causa = default_cause(facts.cause_stage)` and `evidencia = ()`.
- `cause_gap_only` is `True` only when `facts.current` is set, `facts.cause_row.snapshot_id == facts.case.last_snapshot_id` (the cause snapshot is this one), `current.gap_severity >= media` and `current.delay_severity < media`.
- `news_text` for a resolved case writes `resuelto en <resolved_at>` plus `pico de <máxima>` when `PEAK` is in the reasons, and nothing for `SEVERITY_CHANGED`.

### Schema version 2 (`cases/registry/schema.py`)
003's DDL is unchanged; this is added, and `PRAGMA user_version = 2`:
```sql
CREATE TABLE notices (
    notice_id    TEXT PRIMARY KEY,                 -- notice_id_for / report_id_for
    snapshot_id  TEXT NOT NULL,
    seq          INTEGER NOT NULL,                 -- processing seq of the snapshot
    idx          INTEGER NOT NULL,                 -- save order within the snapshot
    kind         TEXT NOT NULL CHECK (kind IN ('notice', 'report')),
    tipo         TEXT NOT NULL,                    -- 'informe_de_turno' for the report row
    case_id      TEXT,                             -- NULL exactly for the report row
    payload      TEXT NOT NULL,                    -- contract JSON of the Notice or ShiftReport
    delivered_at TEXT,                             -- offset-aware ISO 8601; NULL until delivered
    CHECK ((case_id IS NULL) = (kind = 'report')),
    CHECK (kind = 'notice' OR tipo = 'informe_de_turno'),
    UNIQUE (seq, idx)
);
CREATE UNIQUE INDEX one_alert_per_case
    ON notices (case_id) WHERE tipo = 'alerta_inmediata';   -- §4 backstop
```
- Deliverable means `kind = 'report' OR tipo = 'alerta_inmediata'`; it is computed in `pending()`, not stored.
- On open, version 0 creates the schema, version 2 is used as is, anything else (including 1) raises `ValueError` naming the file, the version found and 2, and leaves the file untouched (003 algorithm, new constant).

### `SqliteNoticeStore` algorithms
- **`save(snapshot_id, decisions, report)`:**
  1. `seq = session.require_open(snapshot_id)` (E26a).
  2. Every decision's and the report's `snapshot_id` must equal `snapshot_id`; otherwise `ValueError` naming both, before any write (E26b).
  3. Inside `session.savepoint("notices_save")`:
     - `DELETE FROM notices WHERE seq = ?` (a re-save replaces the set, E26d);
     - a plain `INSERT` per decision (`kind = 'notice'`, `idx = 0..n-1`), then the report (`kind = 'report'`, `tipo = 'informe_de_turno'`, `case_id` NULL, `idx = n`), with `payload = model_dump_json()`.
  4. An `IntegrityError` on the primary key becomes `ValueError` naming the `notice_id` ("belongs to another snapshot", E26h); one from `one_alert_per_case` becomes `ValueError` naming the `case_id` (E26c). The savepoint has already rolled back, so nothing is written even if the caller catches the error.
  - 003's "never `INSERT OR REPLACE`" rule protects foreign keys that point at `cases`. Nothing references `notices`, so delete-and-insert inside a savepoint is safe here.
- **`pending()`:** `RuntimeError` if a unit of work is open. `SELECT notice_id, kind, payload FROM notices WHERE (kind = 'report' OR tipo = 'alerta_inmediata') AND delivered_at IS NULL ORDER BY seq, idx`; `kind = 'report'` parses as `ShiftReport`, otherwise `Notice`.
- **`mark_delivered(notice_id, at)`:** `RuntimeError` if a unit of work is open; `ValueError` if `at.tzinfo is None` or `at.utcoffset() is None`. `UPDATE notices SET delivered_at = ? WHERE notice_id = ? AND delivered_at IS NULL` with `at.isoformat()`; with zero rows, `ValueError` if the ID does not exist, else a no-op. The connection is in autocommit mode, so the statement is its own transaction.
- **`Session.savepoint(name)`:** `SAVEPOINT name`; on a clean exit `RELEASE name`; on any `BaseException` `ROLLBACK TO name`, `RELEASE name`, re-raise. It works inside the open `BEGIN IMMEDIATE` transaction of `processing`.

### Case reads (`SqliteCaseRepository`)
- `resolved_unreported()`: `WHERE state = 'resuelto' AND (last_reported_state IS NULL OR last_reported_state <> 'resuelto')`, sorted in Python by `case_order`.
- `last_deviation_row(case_id)`: `WHERE case_id = ? AND minimum_severity IN ('media', 'alta', 'critica') ORDER BY seq DESC LIMIT 1`. The set is spelled out because text order is not severity order. Inside `processing` after `track`, the current snapshot's row is visible on the same connection.

### `OutboxDispatcher.flush`
```python
def flush(self) -> int:
    """Deliver pending notices in order; stop at the first failure and leave the rest pending."""
    try:
        pending = self._notices.pending()
    except Exception:
        logger.exception("could not read pending notices")
        return 0
    for done, item in enumerate(pending):
        try:
            if isinstance(item.item, ShiftReport):
                self._notifier.report(item.item)
            else:
                self._notifier.alert(item.item)
            self._notices.mark_delivered(item.notice_id, self._clock())
        except Exception:
            logger.exception("delivery of %s failed; %d notices left pending", item.notice_id, len(pending) - done)
            return done
    return len(pending)
```
`KeyboardInterrupt` is a `BaseException`, so it is never caught here. The default clock returns `datetime.now(UTC)`.

### `run_series` change
1. Call `_after_commit(post_commit)` once, **before** `_resolve_upfront`, so notices committed by an earlier run are delivered even when this run's input is bad (E36e).
2. `_handle_arrival` returns `True` when it processed (committed) the snapshot, `False` when it skipped it.
3. In the loop, the `RunAborted` wrapping stays around `_handle_arrival` only. After it returns `True`, call `_after_commit(post_commit)`, outside the wrapping.
4. `_after_commit` does nothing for `None`; otherwise it calls `after_commit()` and logs any `Exception` with `logger.exception`, so the run continues. `KeyboardInterrupt` propagates.

### Adapters
- **File, shared write:** `directory.mkdir(parents=True, exist_ok=True)`; `fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")`; write the bytes through `os.fdopen(fd, "wb")` and close it; `os.replace(tmp, target)`; on any exception, unlink `tmp` (ignoring a missing file) and re-raise. Bytes, never text mode, so line endings are LF on every OS.
- **File, report:** bytes = `report.model_dump_json(indent=2).encode("utf-8") + b"\n"`, target `informe_<turno_id>.json`.
- **File, alert:** read `alertas.jsonl` as bytes if present; if any line's `notice_id` equals `n.notice_id`, return. Otherwise bytes = existing lines plus `n.model_dump_json()`, joined with `b"\n"` and ending with exactly one `b"\n"`.
- **Console:** `encoding = getattr(stream, "encoding", None) or "utf-8"`; write `text.encode(encoding, "backslashreplace").decode(encoding)`, so it never raises on encoding.

### Composition (for spec 012; used by the integration tests)
```python
with SqliteRegistry(settings.registry_path) as registry:
    pipeline = ThresholdPipeline.from_registry(registry, ctx)
    notifier = CompositeNotifier((FileNotifier(settings.notices_dir), ConsoleNotifier()))
    dispatcher = OutboxDispatcher(registry.notices, notifier)
    summary = run_series(arrivals, shifts, registry, pipeline, post_commit=dispatcher)
```

## Design notes
- **Code computes, the model judges (ADR-0002).** Which cases alert, which are news, which are silent, which are active, the `motivo`, the `origen` and the default cause are deterministic code. Spec 008 lets the agent write `texto` and the cited cause and raise severity; the selection rules stay here.
- **Transactional outbox (ADR-0010, Q-23 amended).** `process()` runs inside `processing`, so it cannot deliver without breaking "nothing before commit". Each decision is a row written in the snapshot's transaction; after the commit, `OutboxDispatcher` delivers and marks. A rollback leaves no row, so nothing is ever sent for an uncommitted snapshot. A crash after the commit leaves rows pending, and the next run's start-of-run flush delivers them, before even checking its own input.
- **Why not a post-commit hook alone.** Delivering straight from a hook after the commit, with no durable record, loses notices when the process dies between the commit and the send: the snapshot is marked processed, so the resume skips it and nothing rebuilds its notices. That is the "loses a snapshot's effects on resume" failure ADR-0008 rejected for marking outside the transaction. The hook is still needed, as the trigger; the outbox makes it safe.
- **At-least-once, made harmless.** The only duplicate is a send whose `delivered_at` mark did not happen. `notice_id` is deterministic, and the file adapter skips or overwrites by it, so the file output is identical (E45). The console can show a duplicate line; that is accepted.
- **Ports and Adapters (FR-26).** `Notifier` is the port; console and file are adapters; `notify` imports only `domain`. The runner owns delivery through `OutboxDispatcher`; the pipeline never holds a notifier.
- **Composite.** `CompositeNotifier` fans one delivery out to several channels behind the same port, so the dispatcher stays channel-agnostic. A failure stops the item and the whole item is retried, so only durable, idempotent channels may raise inside it: the file adapter may; the console never raises on encoding.
- **Registry collaborator.** `SqliteNoticeStore` lives on the shared `Session` like `cases` and `releases`, so its writes join the snapshot's transaction and go through the single write guard. Its reads for delivery (`pending`) and its one write (`mark_delivered`) run only outside `processing`, like `record_anomaly` on the skip path.
- **Explicit row kind.** `kind` says whether a row is a per-case decision or the report, enforced by `CHECK`s; deliverability is derived from `kind` and `tipo`, so it cannot disagree with them.
- **Delete-and-insert per snapshot.** `save` is called once per snapshot after the final build and replaces the set, inside a savepoint. No foreign key points at `notices`, so 003's upsert rule is not needed here, and `UNIQUE (seq, idx)` holds because the snapshot's rows are deleted first.
- **No foreign key from `notices.case_id` to `cases`.** The report row has no case, and the store is tested on its own. Every per-case notice is built from a case saved in the same unit of work.
- **Narrow ports.** `CaseRepository` stays the tracker's port. The notice step's extra reads (`resolved_unreported`, `last_deviation_row`) sit behind `NoticeCaseReader` in `runner/pipeline.py`, next to `ReleaseLog` and `NoticeSink`, and `SqliteCaseRepository` satisfies all of them structurally.
- **Novelty reads baselines, not events.** News compares against the last report, which can be several snapshots back. Reading `last_reported_*` and the max makes `expected_news` a pure function of the registry state that spec 010's hooks can call as the expected answer, together with `report_set` and `alerted_case_ids`.
- **Import weight.** `CaseFacts` lives in `cases/facts.py` (domain only), and `novelty` imports `CaseDelta` only for type checking, so hooks and templates load no SQLite code.
- **Q-32 in one read.** `last_deviation_row` after `track` returns this snapshot's row when the case has a deviation now, and the latest earlier one otherwise, so one rule covers active, clean and resolved cases. The stage never comes from older rows, which would be stale.
- **Closing glue is reusable.** `shift_close` and `deviation_rows` are module-level functions, so spec 008's agent pipeline composes the same steps without subclassing `ThresholdPipeline`.
- **Determinism (NFR-04).** IDs derive from snapshot, type and case; decisions follow `case_order`; texts are templates with fixed rounding. Only `delivered_at` reads the clock, it is injected, and it is operational metadata, not contract output.
- **Dependency rule.** `cases` imports only `domain` and `metrics.thresholds`. `notify` imports only `domain`. `runner/pipeline.py` imports `cases`, `metrics.engine` and `domain`; `runner/outbox.py` imports `notify.port` and `domain`. `docs/STRUCTURE.md` gains `runner → notify`.
- **ADRs.** ADR-0010 records the outbox (context Q-23, alternatives: post-commit hook alone, delivery inside the transaction, two-phase marking). ADR-0003 and ADR-0008 stand.

## Test strategy
- **Domain** (`tests/unit/domain/test_notices.py`): E1–E3, enum values, JSON key sets.
- **Facts and novelty** (`tests/unit/cases/test_facts.py`, `tests/unit/cases/test_novelty.py`): E4–E18, E20f and E46. Cases are built directly as `Case` objects (a `case_with(...)` builder may go in `tests/builders.py`); deltas are built as `CaseDelta` values; E7 uses `SqliteRegistry(":memory:")` and the real tracker. One test checks that importing `plant_monitor.cases.novelty` in a fresh interpreter does not load `sqlite3`.
- **Builder and templates** (`tests/unit/cases/test_notice_builder.py`, `tests/unit/cases/test_templates.py`): E19, E20a–e, E21–E23 and E37–E39. Exact strings are asserted for E21 and E22.
- **Store** (`tests/unit/cases/test_notice_store.py`, plus `test_registry.py` for E24, E29 and the updated E21): E24–E29, on `:memory:` and `tmp_path` files; each test closes its registry (Windows).
- **Notifiers** (`tests/unit/notify/`): E30–E33 with `tmp_path`, `io.StringIO`, a cp1252 `TextIOWrapper` and a monkeypatched `os.replace`.
- **Settings** (`tests/test_config.py`): E34.
- **Runner** (`tests/unit/runner/test_outbox.py`, `tests/unit/runner/test_series.py`): E35 with a fake store and a recording notifier; E36 with `InMemoryProcessedStore`; `caplog` for ERROR logs.
- **Pipeline** (`tests/unit/runner/test_pipeline.py`): E40 with the fixture plant and synthetic snapshots, calling `registry.processing` directly.
- **Integration** (`tests/integration/test_notices_runner.py`): E41–E45 over the fixture plant files and snapshots written with `tests/builders.py`. A shared fixture builds the E41 arrivals; a `RecordingNotifier` and fault-injecting wrappers (`NoticeSink`, `PendingNotices`, notifier) live in the test module.
- **Import boundaries** (`tests/unit/test_import_boundaries.py`): add `notify` to the SDK scan and a layer test (`notify` → `domain` only); the module-level `cases` check already covers the new `cases` modules; `runner/series.py` keeps its current allowance.
- **Not covered:** model text and causes (008), hooks (010), schema validation with retry (011).

## Risks
- **Spec 008 must replace a hard stop.** `cause_text` raises `ValueError` for any category but `no_declarada`; 008 must add the cited-cause sentence before the agent sets causes, or the first cited cause aborts the snapshot.
- **At-least-once window.** A death between a successful send and `mark_delivered` re-sends one notice. Mitigated by deterministic `notice_id` and the idempotent file adapter (E45); the console may repeat a line.
- **A delivery failure that never heals** (e.g. a read-only output directory) blocks every later delivery, because order is preserved. Each flush logs an ERROR; pending rows survive in the registry and are delivered once the cause is fixed.
- **Schema bump.** Version 2 rejects 003 files. With no migrations, the run starts from a fresh file; E24c pins the message. The 003 E21 test reads the constant instead of a literal 1.
- **Novelty drift.** If spec 010's hooks reimplemented the rules, they would drift. Hooks must import `cases/novelty.py` (`news_reasons`, `expected_news`, `report_set`, `alerted_case_ids`); spec 010 should test that.
- **Re-marking (003 risk), closed.** Only the report set is marked, and `resolved_unreported()` excludes cases already reported as resolved (E42).
- **Q-27 and the agent (specs 007 and 008).** Agent tools must contribute `texto` and `causa` to an in-memory draft of the snapshot's notices; `save` runs once per snapshot, after the final `track` and the final build, and replaces the snapshot's set. Notices are never edited with `model_copy(update=...)`, which skips the validators; a changed notice is rebuilt.
- **Gap-only phrase for older cause snapshots.** History rows do not store gap and delay severities, so a clean or resolved case whose last deviation was gap-only gets "sin etapa cuello identificada" without "solo por gap" (E22l). Storing those severities in `case_history` was considered and deferred: it would change 003's schema and tests.
- **Mid `informe_de_turno` vs the report.** A mid decision can say "goes to the report" for a change the close does not count (E17). The report is authoritative; evaluators must not count mid decisions as expected news.
- **Console encoding on Windows.** Characters the console cannot encode (on cp1252, `−`; `Sedán` and `×` do encode) are escaped instead of raising (E32b); spec 012 should still set UTF-8 output.
