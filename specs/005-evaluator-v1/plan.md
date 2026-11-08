# 005 · Evaluator v1 — Plan

## Modules

| File | Responsibility |
|---|---|
| `config.py` | `heldout_open` and `heldout_first_shift` fields. Derived path properties with no new environment variable: `plant_dir`, `snapshots_dir`, `logbooks_dir`, `rules_dir`, `evals_dir`. |
| `domain/calendar.py` | **Adds** `HeldOutPolicy` with `from_calendar` (raises `ValueError`). Specs 006 and 012 reuse it. |
| `cases/registry/notices.py` | **Adds** the `DELIVERABLE_FILTER` constant (shared with `pending()`) and the module-level `read_deliverables(path)`: read-only, `mode=ro`, never bootstraps. |
| `ingestion/rows.py` | **New** `iter_rows`: a streaming generator with the same validation and messages as `read_rows`, which becomes `list(iter_rows(...))`. |
| `ingestion/held_out.py` | **New.** `check_ids(policy, *, shifts, snapshots, where)` raises `DataLoadError`. |
| `ingestion/arrivals.py` | **Adds** `load_arrivals_until(path, policy)`. `load_arrivals` is unchanged. |
| `ingestion/logbooks.py` | **New.** `read_logbook_texts(directory, turno_ids, policy)`. Spec 006's store must load through it. |
| `evaluation/__init__.py` | **New.** Package marker; no re-exports. |
| `evaluation/output.py` | **New.** `RunOutput`. |
| `evaluation/sources.py` | **New.** `load_run_output(path, policy)`: `read_deliverables` + held-out refusal + split. No SQL. |
| `evaluation/golden.py` | **New.** `Capability`, golden models, `GoldenSet`, `Labeled`, `load_golden` (duplicate-key-safe YAML, golden-evidence check), `contains_verbatim`. |
| `evaluation/results.py` | **New.** `Section`, `Result`, `tally`, `ALERT_ERRORS`, `NEWS_ERRORS`. |
| `evaluation/scoring.py` | **New.** `score_alerts`, `score_news` (return `Result`s), gating by capability. |
| `evaluation/noise.py` | **New.** `count_noise`; no golden data; never imports `cases.novelty`. |
| `evaluation/summary.py` | **New.** `EvalSummary`, `evaluate`, `exit_code`, `render_table`, `write_summary`. |
| `evaluation/timeline.py` | **New.** `CaseTimeline`, `case_timeline`: cases ordered by first appearance in calendar (snapshot) order, then `case_id`. |
| `evaluation/cli.py` | **New.** `run_eval(*, ...)`, keyword-only; no `config` import. |
| `evals/run_eval.py` | **New.** Thin: `argparse`, `get_settings()`, `sys.exit(run_eval(...))`. |
| `evals/smoke_days_1_7.py` | **New.** Thin A3 composition; on demand, never in CI. |
| `evals/golden/` | **New.** `incidents.md` (A1, with authoring notes), `day_01.yaml`, `day_03.yaml` (T07–T09), `day_04.yaml` (T10). |
| `.env.example` | `HELDOUT_OPEN`, `HELDOUT_FIRST_SHIFT`. |

- No behavior change to `metrics`, `notify` or `runner`, nor to the existing `cases` behavior (`pending()` keeps its contract).
- ADR-0011 (written separately by the main session) records the outbox as source, independent noise, golden keyed by opening snapshot, and `requires` vs `depends_on`.
- **Deferred to spec 008:** `evaluation/causes.py` (`score_causes`, `CauseCheck`, cause results) and the gathering of notice-evidence logbooks in `run_eval`.

## Types and interfaces
```python
# config.py
class Settings(BaseSettings):
    ...                                                   # existing fields unchanged
    heldout_open: bool = False                            # HELDOUT_OPEN: product guard (FR-40, Q-37)
    heldout_first_shift: str = Field(default="T22", min_length=1)   # HELDOUT_FIRST_SHIFT
    @property
    def plant_dir(self) -> Path: ...       # data_dir / "planta"
    @property
    def snapshots_dir(self) -> Path: ...   # data_dir / "snapshots"
    @property
    def logbooks_dir(self) -> Path: ...    # data_dir / "bitacoras"
    @property
    def rules_dir(self) -> Path: ...       # data_dir / "reglas"
    @property
    def evals_dir(self) -> Path: ...       # output_dir / "evals"

# domain/calendar.py
@dataclass(frozen=True)
class HeldOutPolicy:
    """Held-out ids derived from the calendar (FR-40, Q-37); refusals apply only while closed."""
    held_out_shifts: frozenset[str]
    held_out_snapshots: frozenset[str]
    allowed_snapshots: frozenset[str]
    is_open: bool
    known_shifts: frozenset[str]            # every turno_id of the calendar, held out or not

    @classmethod
    def from_calendar(cls, shifts: Iterable[Shift], first_shift: str, is_open: bool) -> HeldOutPolicy: ...
        # ValueError naming first_shift when it is not in the calendar
    @property
    def refused_shifts(self) -> frozenset[str]: ...      # held_out_shifts, or empty when open
    @property
    def refused_snapshots(self) -> frozenset[str]: ...   # held_out_snapshots, or empty when open

# cases/registry/notices.py
DELIVERABLE_FILTER: Final = "(kind = 'report' OR tipo = 'alerta_inmediata')"
_READ_COLUMNS: Final = frozenset({"seq", "idx", "kind", "tipo", "payload"})

def read_deliverables(path: Path) -> tuple[Notice | ShiftReport, ...]:
    """Deliverable rows of a registry file in (seq, idx) order; read-only, never bootstraps; ValueError on a bad file."""
# SqliteNoticeStore.pending() builds its WHERE from DELIVERABLE_FILTER + " AND delivered_at IS NULL".

# ingestion/rows.py
def iter_rows[M: FrozenModel](path: Path, model: type[M]) -> Generator[tuple[int, M]]:
    """Validate CSV rows lazily with their physical line; the missing-columns check runs on the first next()."""
def read_rows[M: FrozenModel](path: Path, model: type[M]) -> list[tuple[int, M]]:
    """Unchanged contract: list(iter_rows(path, model))."""

# ingestion/held_out.py
def check_ids(
    policy: HeldOutPolicy, *, shifts: Iterable[str], snapshots: Iterable[str], where: str
) -> None:
    """DataLoadError naming 'where' and the first refused id (sorted), with 'held out'."""

# ingestion/arrivals.py
def load_arrivals_until(path: Path, policy: HeldOutPolicy) -> list[Arrival]:
    """Stream 'llegadas.csv' and stop right after the row that completes the allowed snapshots."""

# ingestion/logbooks.py
def read_logbook_texts(directory: Path, turno_ids: Iterable[str], policy: HeldOutPolicy) -> dict[str, str]:
    """'<turno_id>.txt' texts ('utf-8-sig'); ids not in 'known_shifts' (exact match), then refused ids, fail before any file is opened."""

# evaluation/output.py
class RunOutput(FrozenModel):
    """What a run emitted, in processing order (Q-33); duplicates are allowed, for the scorer to find."""
    alerts: tuple[Notice, ...]
    reports: tuple[ShiftReport, ...]
    # Validators (ValueError): every alert is ALERT; alert notice_ids unique; report turno_ids unique.

# evaluation/sources.py
def load_run_output(path: Path, policy: HeldOutPolicy) -> RunOutput:
    """read_deliverables, held-out refusal and split; ValueError from the reader becomes DataLoadError."""

# evaluation/golden.py
class Capability(StrEnum):
    """What a run can produce beyond thresholds; closed set (Q-34)."""
    AGENT = "agent"

class GoldenModel(BaseModel):
    """Base of every golden model: frozen, extra keys forbidden; strictness is per field."""
    model_config = ConfigDict(frozen=True, extra="forbid")

type SnapshotId = Annotated[StrictStr, StringConstraints(pattern=r"^S\d{3}$")]
type ShiftId = Annotated[StrictStr, StringConstraints(pattern=r"^T\d{2}$")]
type QuestionId = Annotated[StrictStr, StringConstraints(pattern=r"^Q-\d{2,}$")]
type ItemId = Annotated[StrictStr, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]*$")]
type Justification = Annotated[StrictStr, AfterValidator(_cites_rule)]   # stripped, non-empty, 'criterio' + number
type Fragment = Annotated[StrictStr, StringConstraints(min_length=1)]
# Enums and tuples are lax (YAML strings → enums, lists → tuples); a bare str is never a tuple.

class CaseKey(GoldenModel):
    modelo: Model
    mercado: Market
    abre_en: SnapshotId
    @property
    def case_id(self) -> str: ...           # case_id_for(abre_en, Combination(modelo, mercado))

class GoldenItem(GoldenModel):
    justification: Justification
    id: ItemId | None = None
    depends_on: tuple[QuestionId, ...] = ()     # unique; tracking only
    requires: tuple[Capability, ...] = ()       # unique; gating by capability

class ExpectedAlert(GoldenItem):
    case: CaseKey
    snapshot_id: SnapshotId
    motivo: tuple[Reason, ...] | None = None

class ExpectedNews(GoldenItem):
    turno_id: ShiftId
    case: CaseKey
    estado: CaseState
    severidad: Severity
    severidad_maxima: Severity              # >= severidad; resuelto implies severidad ninguna

class ExpectedEvidence(GoldenModel):
    bitacora: ShiftId
    fragmento: Fragment

class ExpectedCause(GoldenItem):
    case: CaseKey
    notice: Literal[NoticeType.ALERT, NoticeType.SHIFT_REPORT]
    turno_id: ShiftId | None = None         # required iff SHIFT_REPORT
    categoria: CauseCategory
    etapa: Stage | None                     # required, nullable (no default)
    evidencia: ExpectedEvidence | None = None   # required iff categoria is not no_declarada

class GoldenFile(GoldenModel):
    covers: tuple[ShiftId, ...]             # non-empty, unique
    alerts: tuple[ExpectedAlert, ...] = ()
    news: tuple[ExpectedNews, ...] = ()
    causes: tuple[ExpectedCause, ...] = ()
    notes: str | None = None

@dataclass(frozen=True)
class Labeled[T: GoldenItem]:
    label: str                              # '<file>#<id>' or '<file>#<section>[<i>]'
    item: T

@dataclass(frozen=True)
class GoldenSet:
    covered_shifts: tuple[str, ...]         # calendar order
    alerts: tuple[Labeled[ExpectedAlert], ...]
    news: tuple[Labeled[ExpectedNews], ...]
    causes: tuple[Labeled[ExpectedCause], ...]

type LogbookSource = Callable[[frozenset[str]], Mapping[str, str]]

def contains_verbatim(text: str, fragment: str) -> bool: ...
def load_golden(
    directory: Path, shifts: Sequence[Shift], policy: HeldOutPolicy, logbooks: LogbookSource
) -> GoldenSet:
    """Parse, held-out check, file checks, cross-file checks, then golden evidence (one logbooks call)."""

# evaluation/results.py
class Section(StrEnum):
    ALERTS = "alerts"
    NEWS = "news"

@dataclass(frozen=True)
class Result:
    """One scored fact; contributions are summed by 'tally'."""
    section: Section
    label: str | None                       # None for extra, unscored, missing_report, unscored_report
    case_id: str | None                     # None for missing_report and unscored_report
    where: str                              # snapshot_id (alerts) or turno_id (news)
    contributions: Mapping[str, int]        # e.g. {'hit': 1, 'motivo_mismatch': 1}, {'duplicates': 2}
    depends_on: tuple[str, ...] = ()
    gated: bool = True
    ref: str | None = None                  # notice_id of an extra or unscored alert

ALERT_ERRORS: Final = frozenset({"missing", "wrong_snapshot", "duplicates", "extra"})
NEWS_ERRORS: Final = frozenset({"missing", "extra", "missing_report"})

def tally(
    results: Iterable[Result], *, gated: bool | None = None, question: str | None = None
) -> dict[str, int]: ...
def errors(counts: Mapping[str, int], keys: frozenset[str]) -> int: ...

# evaluation/scoring.py
def score_alerts(
    run: RunOutput, golden: GoldenSet, shifts: Sequence[Shift], capabilities: frozenset[Capability]
) -> tuple[Result, ...]: ...
def score_news(
    run: RunOutput, golden: GoldenSet, capabilities: frozenset[Capability]
) -> tuple[Result, ...]: ...

# evaluation/noise.py
@dataclass(frozen=True)
class RepeatedNews:
    turno_id: str
    case_id: str
    previous_turno_id: str

@dataclass(frozen=True)
class NoiseScore:
    repeats: tuple[RepeatedNews, ...]
    duplicate_alerts: tuple[tuple[str, int], ...]   # reported only; never gating
    @property
    def errors(self) -> int: ...            # len(repeats)

def count_noise(run: RunOutput) -> NoiseScore: ...

# evaluation/summary.py
@dataclass(frozen=True)
class EvalSummary:
    registry: str
    golden: str
    capabilities: frozenset[Capability]
    covered_shifts: tuple[str, ...]
    alerts: tuple[Result, ...]
    news: tuple[Result, ...]
    noise: NoiseScore
    @property
    def gating_errors(self) -> int: ...     # errors(tally(alerts, gated=True)) + news likewise + noise.errors
    def to_json(self) -> dict[str, object]: ...   # per section: gated, not_gated, by_question tallies + results

def evaluate(
    run: RunOutput, golden: GoldenSet, shifts: Sequence[Shift], *,
    capabilities: frozenset[Capability], registry: str, golden_dir: str,
) -> EvalSummary: ...
def exit_code(summary: EvalSummary) -> int: ...      # 0 or 1
def render_table(summary: EvalSummary) -> str: ...
def write_summary(summary: EvalSummary, directory: Path, at: datetime) -> Path: ...  # aware 'at'

# evaluation/timeline.py
@dataclass(frozen=True)
class CaseTimeline:
    case_id: str
    first_reported_in: str | None
    alerted_at: tuple[str, ...]
    resolved_in: str | None

def case_timeline(run: RunOutput) -> tuple[CaseTimeline, ...]: ...

# evaluation/cli.py
def run_eval(
    *, registry: Path, golden_dir: Path, shifts_path: Path, logbooks_dir: Path,
    first_held_out_shift: str, held_out_open: bool, capabilities: frozenset[Capability],
    out_dir: Path, now: datetime, out: TextIO, err: TextIO,
) -> int: ...                               # 0, 1 or 2
```

### `read_deliverables`
```python
if not path.is_file():
    raise ValueError(f"{path}: registry not found")       # checked before building the URI; nothing is created
try:
    with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:   # connect inside the try
        columns = {row[1] for row in conn.execute("PRAGMA table_info(notices)")}
        if missing := _READ_COLUMNS - columns:
            raise ValueError(f"{path}: table notices lacks {sorted(missing)}")   # covers a missing table too
        rows = conn.execute(
            f"SELECT kind, payload FROM notices WHERE {DELIVERABLE_FILTER} ORDER BY seq, idx"
        ).fetchall()
except sqlite3.Error as error:
    raise ValueError(f"{path}: not a readable registry ({error})") from error
# kind 'report' → ShiftReport.model_validate_json, else Notice; a ValidationError → ValueError naming the file.
```
- It checks the columns instead of `user_version`, so a later schema version that keeps these columns still reads. A real incompatibility fails loudly.

### `HeldOutPolicy.from_calendar`
1. `first = next((s for s in shifts if s.turno_id == first_shift), None)`; `None` → `ValueError`.
2. Held out: `{s for s in shifts if s.inicio >= first.inicio}`. Snapshots: the union of their `snapshot_medio` and `snapshot_cierre`. Allowed: those of the rest.
- Order comes from `inicio`, never from the id text, so a calendar listed out of order works (E4).

### `load_arrivals_until`
1. `ValueError` if `policy.allowed_snapshots` is empty.
2. `remaining = set(policy.allowed_snapshots)`; `with contextlib.closing(iter_rows(path, _ArrivalRow)) as rows:`, enumerate with `expected = 1`:
   - `row.orden != expected` → `DataLoadError(f"{path}, row {line}: field 'orden': {row.orden}, expected {expected}")`;
   - `row.snapshot_id in policy.held_out_snapshots` → `DataLoadError(f"{path}, row {line}: snapshot {id} is held out")`;
   - append the `Arrival` (same `archivo` resolution as `load_arrivals`); `remaining.discard(row.snapshot_id)`;
   - if `not remaining`, break; else `expected += 1`.
3. If the loop ended with `remaining` non-empty: `DataLoadError(f"{path}: ends before every allowed snapshot arrived; missing {sorted(remaining)}")`.
- `closing` makes the generator close its file on `break` and on errors (E6, Windows).
- It uses `held_out_snapshots`, not `refused_snapshots`: this reader is for days 1–7, whether or not the guard is open.

### `load_golden`
1. `files = sorted(directory.glob("*.yaml"))`; empty → `DataLoadError(f"{directory}: no golden .yaml files")`.
2. Per file: `yaml.load(text, Loader=_UniqueKeyLoader)`, where `_UniqueKeyLoader` is a `yaml.SafeLoader` subclass whose mapping constructor raises on a repeated key. A non-mapping top level is an error. Then `GoldenFile.model_validate(data)`; a `ValidationError` becomes `DataLoadError(f"{file.name}: {describe_validation_error(exc)}")`.
3. `check_ids(policy, shifts=…, snapshots=…, where=file.name)` over `covers`, every `turno_id`, `snapshot_id`, `abre_en` and `evidencia.bitacora`.
4. File checks (calendar membership and order only; shape is done by the regex in step 2). Snapshot order is the calendar position: shifts sorted by `inicio`, each giving (mid, closing).
5. Cross-file checks. Labels use `id` when present.
6. `cited = {c.evidencia.bitacora for c in causes if c.evidencia}`. If `cited` is non-empty, call `texts = logbooks(frozenset(cited))` once, then require `contains_verbatim(texts.get(b, ""), fragmento)` for each cause, raising `DataLoadError(f"{label}: fragment not found in {b}")`.
7. Return the `GoldenSet`, with `covered_shifts` in calendar order.

### `score_alerts`
```python
scope = {s for t in golden.covered_shifts for s in snapshots_of(t, shifts)}
by_case = group run.alerts by case_id (run order)
unmet_cases = {i.item.case.case_id for i in all golden items if not set(i.item.requires) <= capabilities}
for labeled in golden.alerts:
    found = by_case.get(case_id, []); at = [a for a in found if a.snapshot_id == item.snapshot_id]
    if not found: contrib = {"missing": 1}
    elif not at: contrib = {"wrong_snapshot": 1}
    elif len(found) == 1: contrib = {"hit": 1} | ({"motivo_mismatch": 1} if item.motivo is not None and item.motivo != at[0].motivo else {})
    else: contrib = {"duplicates": len(found) - 1}
    yield Result(ALERTS, label, case_id, item.snapshot_id, contrib, item.depends_on,
                 gated=set(item.requires) <= capabilities)
for alert in run.alerts whose case_id matches no golden alert:
    key = "extra" if alert.snapshot_id in scope else "unscored"
    yield Result(ALERTS, None, alert.case_id, alert.snapshot_id, {key: 1},
                 gated=alert.case_id not in unmet_cases, ref=alert.notice_id)
```
`unmet_cases` gathers alert, news and cause items, so a case whose agent-only news is expected also releases its extra alerts.

### `score_news`
```python
reports = {r.turno_id: r for r in run.reports}
for turno in golden.covered_shifts:
    exp = news items of turno (by case_id)
    report = reports.get(turno)
    if report is None:
        yield Result(NEWS, None, None, turno, {"missing_report": 1})
        for each exp item: yield its {"missing": 1} result (gated by its requires); continue
    actual = {n.case_id: n for n in report.novedades}
    for each exp item: hit with mismatch keys for estado / severidad / severidad_maxima, or missing
    for case_id in actual - exp: yield Result(NEWS, None, case_id, turno, {"extra": 1}, gated=case_id not in unmet_cases)
for report in run.reports whose turno_id is not covered: yield Result(NEWS, None, None, turno_id, {"unscored_report": 1})
```

### `count_noise`
```python
for prev, cur in pairwise(run.reports):
    rows = {r.case_id: r for r in prev.casos_activos}
    for n in cur.novedades:
        r = rows.get(n.case_id)
        if (r is not None and n.estado is not CaseState.RESOLVED
                and _norm(r.estado) == _norm(n.estado) and r.severidad == n.severidad
                and n.severidad_maxima == n.severidad):
            repeats.append(RepeatedNews(cur.turno_id, n.case_id, prev.turno_id))
duplicate_alerts = [(case_id, m) for case_id, m in Counter(a.case_id for a in run.alerts).items() if m >= 2]
# '_norm' is local to evaluation/noise.py: OPEN → FOLLOW_UP, others unchanged.
```

### Tallies and the summary
- `tally(results, gated=g, question=q)` keeps the results with `g is None or r.gated is g` and `q is None or q in r.depends_on`, then sums their `contributions`.
- `to_json` builds, per section: `gated`, `not_gated` and `by_question` (one tally per question in any result's `depends_on`, sorted), plus `results` (label, case, where, contributions, gated, depends_on, ref). For noise: `repeats` and `duplicate_alerts`. Plus `gating_errors` and `exit_code`. `render_table` reads the same tallies.

### `run_eval`
1. `shifts = load_shifts(shifts_path)`; `policy = HeldOutPolicy.from_calendar(shifts, first_held_out_shift, held_out_open)`.
2. `run = load_run_output(registry, policy)`.
3. `golden = load_golden(golden_dir, shifts, policy, lambda ids: read_logbook_texts(logbooks_dir, ids, policy))`.
4. `summary = evaluate(run, golden, shifts, capabilities=…, registry=str(registry), golden_dir=str(golden_dir))`; write `render_table(summary)` to `out`; `path = write_summary(summary, out_dir, now)`; print `path`; return `exit_code(summary)`.
5. A `DataLoadError`, `ValueError` or `OSError` in steps 1–3 (sqlite3 errors arrive as `ValueError`): one line on `err`, return 2, nothing written.

### `evals/run_eval.py`
```python
def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)     # --registry PATH --golden DIR [--capabilities agent[,...]]
    s = get_settings()
    return run_eval(
        registry=args.registry, golden_dir=args.golden, shifts_path=s.plant_dir / "turnos.csv",
        logbooks_dir=s.logbooks_dir, first_held_out_shift=s.heldout_first_shift,
        held_out_open=s.heldout_open, capabilities=frozenset(args.capabilities),
        out_dir=s.evals_dir, now=datetime.now(UTC), out=sys.stdout, err=sys.stderr,
    )

if __name__ == "__main__":
    sys.exit(main())
```
- `--capabilities` parses a comma-separated list into `Capability` values; an unknown value is an argparse error (exit 2).

### `evals/smoke_days_1_7.py` (composition)
```python
def main() -> int:
    s = get_settings()
    try:
        shifts = load_shifts(s.plant_dir / "turnos.csv")
        ctx = PlantContext(plan=load_plan(s.plant_dir / "plan_produccion.csv", shifts), shifts=shifts,
                           standards=StandardsTable.from_rows(load_standards(s.plant_dir / "tiempos_estandar.csv")),
                           shipments=ShipmentsTable.from_rows(load_shipments(s.plant_dir / "embarques.csv")),
                           thresholds=load_thresholds(s.rules_dir / "umbrales.yaml"))
        policy = HeldOutPolicy.from_calendar(shifts, s.heldout_first_shift, s.heldout_open)
        arrivals = load_arrivals_until(s.snapshots_dir / "llegadas.csv", policy)
        out = s.evals_dir / f"smoke-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        out.mkdir(parents=True)                                   # fresh run directory; fails if it exists
        with SqliteRegistry(out / "registry.sqlite3") as registry:
            summary = run_series(arrivals, shifts, registry, ThresholdPipeline.from_registry(registry, ctx),
                                 post_commit=OutboxDispatcher(registry.notices, FileNotifier(out / "notices")))
            pending = registry.notices.pending()
        run = load_run_output(out / "registry.sqlite3", policy)    # after the registry is closed
    except (RunAborted, DataLoadError, ValueError) as exc:
        print(f"smoke run failed: {exc}")
        return 2
    # print processed / skipped / anomalies, then each CaseTimeline of case_timeline(run)
    if pending:
        print("pending notices:", ", ".join(p.notice_id for p in pending))
        return 1
    return 0
```

## Design notes
- **Independence (ADR-0011, Q-33).** The evaluator scores the contract, not internals. Noise is written out again over `ShiftReport` JSON, and `cases.novelty` is off limits by an import test (E38). The source reads stored decisions, not channel files: the outbox is the durable, ordered record, and the channels are at-least-once.
- **SQL stays in `cases/registry`.** `read_deliverables` sits beside `pending()` and shares `DELIVERABLE_FILTER`, so "deliverable" has one definition. It is read-only (an existence check before the URI, `mode=ro`) and never goes through `SqliteRegistry`, which bootstraps a version-0 file. It checks the columns it reads rather than the whole `user_version`, so unrelated schema bumps do not break evals. `evaluation/sources.py` keeps only the policy and the split.
- **Policy in `domain`, guard in `ingestion`.** `HeldOutPolicy` is pure calendar logic (`ValueError`), so `ingestion`, `evaluation`, spec 006's logbook store and spec 012's CLI share it without depending on `evaluation`. `check_ids` raises the loaders' `DataLoadError`, so it sits next to them. `ingestion` still imports only `domain`.
- **Arrivals without a configured cutoff (Q-37).** The reader stops when the allowed set is complete, so no second number has to agree with the calendar. Its one blind spot, a late repeat of an allowed snapshot, is documented and tested (E7g); it does not occur in days 1–7.
- **Golden keyed by opening snapshot (Q-34).** `case_id_for(abre_en, combination)` is the system's own deterministic id (NFR-04). Matching on it makes "opened at the wrong snapshot" visible, and it tells apart two cases of one combination in one report (E21).
- **Full criteria in the golden, gating by capability.** The golden says what `criterio.md` requires, §5 included, so it never has to be rewritten when the agent arrives. `requires` keeps the threshold-only baseline honest: unmet items are scored and shown, but do not gate. An extra on the same case is released too, because it is the visible side of the same unmet behavior (E39). `depends_on` is separate and tracking only, so a decision change shows per question without changing what gates (E32).
- **Results, then tallies.** Scorers return facts (`Result`), and every count comes from `tally`. Buckets (gated, not gated, per question) are filters, not parallel counters that can drift, and the JSON lists the facts behind each number.
- **Coverage is explicit.** Without `covers`, a run that drops a whole shift would score zero errors. Covered shifts make "nothing expected" a statement (E22b) and "nothing produced" an error (E22a).
- **Golden typing.** `extra = forbid` catches typos. Strict ids block YAML coercions (`abre_en: 1`). Lax enums and tuples map YAML naturally, and the duplicate-key loader blocks silent overwrites. Regexes check shape only; the calendar checks membership, coverage, order and held-out, so no check is repeated.
- **Golden evidence at load time.** A golden fragment that is not in its logbook makes the golden wrong, so loading fails (exit 2) instead of producing a score. The logbook source is injected, so tests use dicts and the CLI uses the guarded loader.
- **Dependency rule.** `evaluation` imports `domain` and `ingestion`. Only `evaluation/sources.py` touches `cases`, and only `read_deliverables`. `evaluation/cli.py` takes explicit keyword arguments, so `evaluation` never imports `config`. Composition with `runner`, `notify` and `metrics` happens only in `evals/` scripts. `docs/STRUCTURE.md` gains `evaluation → ingestion → domain`, the `sources.py → cases.registry.notices` exception, and `evals/ → everything (thin)`.
- **Determinism (NFR-04).** Golden files load in name order, results follow golden and run order, and the only clock is the injected `at`/`now`.
- **Type checking of `evals/`.** The scripts sit outside the package, so `mypy src tests evals` (CI, pre-commit, `/check`, `CLAUDE.md`).

## Test strategy
- **Settings** (`tests/test_config.py`): E36. Add `HELDOUT_OPEN` and `HELDOUT_FIRST_SHIFT` to the isolation fixture, plus one test that every `Settings` field's env name is in `.env.example`.
- **Domain** (`tests/unit/domain/test_calendar.py`): E4.
- **Registry** (`tests/unit/cases/test_notice_store.py`): E40 with a real `SqliteRegistry` on `tmp_path`, closed before reading; the 004 `pending()` tests stay unchanged.
- **Ingestion** (`tests/unit/ingestion/test_held_out.py`, `test_arrivals.py`, `test_rows.py`, `test_logbooks.py`): E5a/f, E6–E8, with `tmp_path` files written as bytes (BOM, CRLF). The existing `read_rows` and `load_arrivals` tests stay unchanged.
- **Source and output** (`tests/unit/evaluation/test_sources.py`, `test_output.py`): E9 (on E40's registry builder), E10.
- **Golden** (`tests/unit/evaluation/test_golden.py`): E1–E3, E5b–e, E30, with YAML written to `tmp_path` and dict logbook sources. One test per E2 sub-case (parametrized).
- **Scoring** (`tests/unit/evaluation/test_scoring.py`, `test_noise.py`, `test_results.py`): E11–E26, E32, E33, E39 on synthetic `RunOutput`s. `tests/eval_builders.py` (added to ruff's `known-local-folder`) provides `alert`, `news`, `row`, `report` and the golden item helpers on top of `notice_builders`.
- **Summary and timeline** (`tests/unit/evaluation/test_summary.py`, `test_timeline.py`): E33–E35.
- **CLI** (`tests/unit/evaluation/test_cli.py`): E37 with `io.StringIO` streams and a fixed `now`.
- **Import boundaries** (`tests/unit/test_import_boundaries.py`): E38. Add `evaluation` to `SDK_FREE_PACKAGES`; a module-level rule for `evaluation` with the `sources.py` exception; a scan that no `evaluation` module imports `sqlite3`; a subprocess probe that `plant_monitor.evaluation.scoring` loads no `plant_monitor.cases` and no `sqlite3`; `domain/calendar.py` stays domain-only (already covered).
- **Not in CI:** `evals/smoke_days_1_7.py` and evals over real data (NFR-07). Both scripts are type-checked and linted.

## Risks
- **Circular golden cases.** The smoke output is a starting point only. Every golden item is justified by §n plus numbers or a quote, computed by hand from days 1–7 data and the logbooks, and reviewed against `criterio.md` (`/verify-criteria`).
- **Golden effort.** Covering a whole shift means listing every news item of every case in it. With the full criteria, the Europe audit also needs every §5-driven item, marked `requires: [agent]`. Mitigation: build from the smoke timeline plus the A1 catalog, then verify each item by hand.
- **Extra exclusion is per case.** An unmet raise that also changes another case's news, through the report baseline, would show up as a gated extra on that other case. A §5 raise applies per case (Q-02), so golden files must list items for each affected case; review this when spec 008 lands.
- **Verbatim drift with spec 006.** The evaluator's whitespace normalization is its own. Spec 008 compares it with spec 006's rule on the golden fragments.
- **Logbook loader bypass.** The guard holds only if spec 006's `LogbookStore` loads through `read_logbook_texts`. Spec 006 should test that.
- **Late repeats not read.** A future `llegadas.csv` with a repeat after the allowed set completes would be silently shortened for the smoke run. It is documented and tested (E7g); the full-series CLI (spec 012) uses `load_arrivals`, not this reader.
- **Column coupling.** `read_deliverables` depends on five `notices` columns. Dropping or renaming one fails loudly (E40d).
