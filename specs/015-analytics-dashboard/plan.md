# 015 · Metrics window of the live dashboard — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `evaluation/summary_file.py` | New (leaf) | `EVAL_NAME`, `SectionCounts`, `StoredNoise`, `StoredSummary`, `read_summary`, `write_summary_json`, private `_write_atomic` (R10; I10). |
| `evaluation/summary.py` | Changes | `EvalSummary.deliverables`; `write_summary` delegates to `write_summary_json`; `_JSON_NAME` moves out. |
| `evaluation/cli.py` | Changes | `run_eval` passes `registry=str(registry.resolve())` (Q-114). |
| `telemetry/trace.py` | Adds | `STAMP_FORMAT`, `ISO_Z_FORMAT`, `TRACE_NAME`; `trace_path` uses `STAMP_FORMAT`. |
| `telemetry/run_report.py` | New (moved) | `Status`, `Tokens`, `Arrivals`, `RunScope`, `SeriesScope`, `RunReport`, `report_path`, `write_report` (now atomic) from `runner/summary.py`; new `REPORT_NAME`, `read_report`, private `_write_atomic` (I5, I10). |
| `runner/summary.py` | Refactor | Imports the moved names it uses; re-exports `report_path` only (012 test). Keeps `Mode`, `RunOutcome`, `build_report`, `render_report`; `ISO_Z_FORMAT` now from `telemetry.trace`. |
| `runner/cli.py` | Changes | Imports `RunReport`, `report_path`, `write_report` from `telemetry.run_report`. |
| `dashboard/heldout.py` | Adds | `json_shown`; `line_shown` delegates to it (I6). |
| `dashboard/source.py` | Adds | `lines_as_of`, `day_label` (moved), `deliverables_as_of`, `author_of`, `DayLookup`, `day_lookup` (I3, I11). |
| `dashboard/state.py` | Refactor | Uses the `source` helpers; no behavior change (014 tests unchanged). |
| `dashboard/panels.py` | New | `AccuracyPanel`, `RunItem`, `RunsPanel`, `load_accuracy`, `load_runs` (R11–R13; I4, I8, I13). |
| `dashboard/metrics.py` | New | `build_metrics` and its private builders (R3–R9, R12). |
| `dashboard/payloads.py` | Adds | The metrics `TypedDict`s (API below). |
| `dashboard/server.py` | Changes | Two `ASSETS` routes; `/api/metrics`; `DashboardApp` gains `evals_dir`, `runs_dir`. |
| `src/frontend/metricas.html`, `metrics.js` | New | The Métricas window (R15). |
| `src/frontend/index.html`, `agentes.html`, `dom.js`, `app.css` | Changes | Nav link; an SVG helper in `dom.js` if the sparkline's is not reusable; styles. |
| `tests/metrics_builders.py` | New | `call`, `metric_line` (C, LN with `totals_usd`), `metric_view` (MV), `CAL`, `eval_file` (EVAL), `MT`. |

## Types and interfaces

### `evaluation/summary_file.py`
```python
EVAL_NAME: Final = re.compile(r"eval-(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json")
class SectionCounts(BaseModel):          # frozen, extra="ignore"
    gated: dict[str, int] = {}
    not_gated: dict[str, int] = {}
class StoredNoise(BaseModel):            # frozen, extra="ignore"
    errors: int
class StoredSummary(BaseModel):          # frozen, extra="ignore"
    registry: str
    capabilities: list[str]
    covered_shifts: list[str]
    alerts: SectionCounts
    news: SectionCounts
    causes: SectionCounts = SectionCounts()
    noise: StoredNoise
    gating_errors: int
    exit_code: int
    deliverables: int | None = None
def read_summary(path: Path) -> StoredSummary: ...
def write_summary_json(data: Mapping[str, object], directory: Path, at: datetime) -> Path: ...
```
- Imports only stdlib, pydantic and (if ever needed) `domain`. Nothing from `golden`, `scoring`, `causes`, `results`, `noise`: the writer takes the plain JSON values of `EvalSummary.to_json()`, so the scored types stay in `summary.py`.
- `write_summary_json`: the naive-time `ValueError`, `mkdir(parents=True, exist_ok=True)`, the name `eval-<UTC stamp>.json`, `json.dumps(ensure_ascii=False, indent=2) + "\n"` as UTF-8 bytes, then `_write_atomic`. Same bytes as today (005 E34a).
- `read_summary`: bytes → `model_validate_json`. `OSError`, `UnicodeDecodeError` and `ValidationError` become `ValueError(f"{path.name} is not a readable evaluation summary")`. `capabilities` stays `list[str]` so a capability added later still parses.
- `_write_atomic(target, data)`: `tempfile.mkstemp(dir=target.parent, prefix=".", suffix=".tmp")`, write, `os.replace`, unlink the temp on any error (the pattern of `notify/atomic.write_atomic`, duplicated because the layer rule forbids `evaluation → notify`).

### `EvalSummary.deliverables`
`deliverables: int | None = None` is the last field, so every keyword constructor still works. `evaluate(...)` passes `len(run.alerts) + len(run.reports)`; `to_json` appends `"deliverables"` after `"exit_code"`. `write_summary(summary, directory, at)` = `write_summary_json(summary.to_json(), directory, at)`.

### `telemetry/trace.py` constants
```python
STAMP_FORMAT: Final = "%Y%m%dT%H%M%SZ"
ISO_Z_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"
TRACE_NAME: Final = re.compile(r"trace-(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.jsonl")
```
`trace_path` formats with `STAMP_FORMAT` (same output). One home for each, importable by `runner`, `dashboard` and `telemetry/run_report.py`.

### `telemetry/run_report.py`
```python
Status = Literal["ok", "aborted", "interrupted"]
REPORT_NAME: Final = re.compile(r"run-(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json")
class Tokens(BaseModel): ...              # moved verbatim, incl. 'of'
class Arrivals(BaseModel): ...
class RunScope(BaseModel): ...
class SeriesScope(BaseModel): ...
class RunReport(BaseModel): ...           # 'mode: TraceMode'
def report_path(directory: Path, started: datetime) -> Path: ...
def write_report(report: RunReport, path: Path) -> None: ...
def read_report(path: Path) -> RunReport: ...  # ValueError "<name> is not a readable run report"
```
- `write_report`: `(model_dump_json(indent=2) + "\n").encode("utf-8")` through its own `_write_atomic` (same pattern; `telemetry` may not import `notify`). The parent directory is still created.
- `runner/summary.py` imports `Arrivals`, `RunReport`, `RunScope`, `SeriesScope`, `Status`, `Tokens` for its own code and re-exports `report_path as report_path` for `tests/unit/runner/test_run_summary.py`. Nothing else is re-exported; `runner/cli.py` moves to the new home in the same commit.

### `json_shown`
`json_shown(value: object, policy: HeldOutPolicy) -> bool`: true when the guard is open, or when no `_TOKEN_RE` token in any string of `value` (keys included, via `_strings`) is in `refused_snapshots | refused_shifts`. `line_shown` keeps its id-pattern checks, then calls `json_shown(line.model_dump(mode="json"), policy)`.

### `dashboard/source.py` helpers
```python
def lines_as_of(view: RunView, at: int) -> list[TraceLine]: ...
def day_label(shift: Shift) -> str: ...
def deliverables_as_of(view: RunView, at: int) -> tuple[NoticeAt, ...]: ...
def author_of(view: RunView, notice: Notice) -> TextBy: ...
@dataclass(frozen=True)
class DayLookup:
    labels: tuple[str, ...]                 # calendar order, unique
    by_snapshot: Mapping[str, str]          # snapshot_medio / snapshot_cierre -> label
    by_shift: Mapping[str, str]             # turno_id -> label
def day_lookup(calendar: Calendar) -> DayLookup: ...
```
- `lines_as_of`: today's `cost_as_of` filter (every line at `latest`; else lines of shown positions ≤ `at`).
- `deliverables_as_of`: `view.deliverables` with `seq ≤ at`, order kept.
- `author_of`: `text_by(notice.notice_id, view.committed.get(notice.snapshot_id), view.mode)`.
- `state.py`: `_current` and `_days` use `day_label` (and `day_lookup` where it fits), `_kpis` and `_feed` use `deliverables_as_of`, `_notice_item` uses `author_of`.

### `dashboard/panels.py`
```python
@dataclass(frozen=True)
class AccuracyPanel:
    state: Literal["ok", "none", "omitted"]
    file: str | None
    evaluated_at: str | None        # "YYYY-MM-DDTHH:MM:SSZ" from the name stamp
    summary: StoredSummary | None
    earlier: int
    unreadable: int
    # __post_init__: ValueError when state == "ok" and summary is None
@dataclass(frozen=True)
class RunItem:
    file: str | None
    mode: TraceMode
    status: Literal["ok", "aborted", "interrupted", "running"]
    started_at: str
    duration_seconds: float | None
@dataclass(frozen=True)
class RunsPanel:
    items: tuple[RunItem, ...]
    unreadable: int
    omitted: int
def load_accuracy(evals_dir: Path, registry_path: Path, policy: HeldOutPolicy) -> AccuracyPanel: ...
def load_runs(runs_dir: Path, traces_dir: Path, policy: HeldOutPolicy) -> RunsPanel: ...
```
- `load_accuracy`: names fully matching `EVAL_NAME`, reversed; `read_summary` (a `ValueError` adds to `unreadable`); match by resolved paths; for the chosen file only, `json_shown(json.loads(bytes), policy)`, false → `omitted`, `summary=None`.
- `load_runs`: each `REPORT_NAME` file read once (`read_report` plus `json.loads` of the same bytes for `json_shown`). The set of report stamps is taken from the **names** before reading, so an unreadable or omitted report still pairs with its trace (R13). A `TRACE_NAME` stamp outside that set adds a `running` item. Sorted by `started_at`, formatted with `ISO_Z_FORMAT`.
- Neither function creates a directory or lets one file's `OSError` escape.

### `build_metrics`
```python
def build_metrics(view: RunView, calendar: Calendar, at: int,
                  accuracy: AccuracyPanel, runs: RunsPanel) -> MetricsPayload: ...
```
- `_cost` (R3–R6): group `lines_as_of(view, at)` by snapshot; per shown position ≤ `at`, `run_totals(point_lines)`. Keep `Decimal` running sums of `.usd`; format with `format_usd` only when writing. `unplaced = run_totals(all).usd − Σ point usd`. `by_agent` feeds `usd` (display only).
- `_days` (R7, `day_lookup`), `_authors` (R8, `author_of`), `_noise` (R9: `RunOutput` in a `try`; `ValueError` → `{"state": "invalid", "error": type(e).__name__}`), `_accuracy` (R11: `current = len(view.deliverables) + view.omitted.notices`), `_runs` (R13), `_heldout` (R12).
- `cache_pct`: `(Decimal(100 * read) / Decimal(denominator)).quantize(Decimal("0.1"))`.

### `DashboardApp`
- Keyword `evals_dir: Path`, `runs_dir: Path`; `from_settings` passes `settings.evals_dir`, `settings.runs_dir`. No test builds `DashboardApp` directly today.
- `/api/metrics` goes through `_api`: `at` checked before I/O; `snapshot` checked only for the 014 routes (I12). Then `load_view`, `resolve_at`, `load_accuracy`, `load_runs`, `build_metrics`, inside the existing last-resort `except`.
- `ASSETS` adds `"/metricas": ("metricas.html", _HTML)` and `"/metrics.js": ("metrics.js", _JS)`.

## API

`GET /api/metrics?at=N` (shape; numbers illustrative, the examples are normative):
```json
{"at": 10, "latest": 10, "positions": [1, 2], "registry": "ok", "trace_error": null,
 "heldout": {"open": true, "omitted": {"snapshots": 0, "notices": 0, "trace_lines": 0, "evals": 0, "run_reports": 0}},
 "cost": {"state": "ok", "unplaced_usd": "0.00000000",
   "points": [{"seq": 4, "snapshot_id": "S004",
               "usd": {"investigator": "0.00080000", "coordinator": "0.00080000"}, "cumulative_usd": "0.00240000",
               "tokens": {"input": 12000, "output": 800, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0},
               "cache_pct": "0.0", "latency_ms": 0}],
   "totals": {"usd": "0.00760000", "model_calls": 19, "input": 57000, "output": 3800, "cache_read": 0,
              "cache_write_5m": 0, "cache_write_1h": 0, "cache_pct": "0.0", "latency_ms": 0}},
 "days": [{"label": "3/2/2026", "alerts": 1, "reports": 3, "reports_with_news": 1, "reports_without_news": 2}],
 "authors": {"agent": 6, "template": 0, "unknown": 0},
 "noise": {"state": "ok", "errors": 0, "repeats": [], "duplicate_alerts": []},
 "accuracy": {"state": "ok", "file": "eval-20260303T120000Z.json", "evaluated_at": "2026-03-03T12:00:00Z",
   "earlier": 1, "unreadable": 0, "stale": false, "deliverables": 8, "current_deliverables": 8,
   "summary": {"capabilities": ["agent"], "covered_shifts": ["T05"],
     "sections": {"alerts": {"gated": {"hit": 2}, "not_gated": {}}, "news": {"gated": {}, "not_gated": {}},
                  "causes": {"gated": {}, "not_gated": {}}},
     "noise_errors": 0, "gating_errors": 0, "exit_code": 0}},
 "runs": {"unreadable": 0, "items": [{"file": "run-20260302T230000Z.json", "mode": "agent", "status": "ok",
   "started_at": "2026-03-02T23:00:00Z", "duration_seconds": 1.0}]}}
```
- `accuracy.summary`, `stale`, `deliverables` and `current_deliverables` are null in `none` and `omitted`.
- `noise` in the invalid state is exactly `{"state": "invalid", "error": "<ErrorClass>"}`.

## Data flow
```
request: method → Host → route → at check → load_view (014) → resolve_at
         → load_accuracy(evals_dir) + load_runs(runs_dir, traces_dir) → build_metrics → json.dumps(ensure_ascii=True)
client:  BroadcastChannel("plant-monitor") {mode, at} → fetch ?at=N | "Seguir en vivo" → poll without at (1.5 s)
         503 busy → keep the last good payload
```

## Design notes
- **Why read the eval file instead of evaluating (Q-103).** Evaluating needs the golden set, logbooks and held-out loading, owned by `evals/run_eval.py`; a live poll must not re-score. `deliverables` tells the user when the stored result is behind the registry.
- **Why a leaf `summary_file` (Q-118).** `evaluation/summary.py` imports `golden`, `scoring`, `causes` and `results`. Reading a stored file needs none of that, so the reader, the stored model and the byte-level writer live in a module the dashboard can import without loading the scorer (E20 probe). Writer and reader still share one module (Q-104).
- **Why name-level imports (F2).** A module-level allowlist would admit any future name added to `evaluation.noise` or `summary_file`. Naming the six imports keeps the dashboard a consumer of exactly what it uses.
- **Cumulative = Planta by arithmetic (F1).** Planta sums `row.totals.usd` per line; `by_agent` sums per call and can differ by rounding. Summing point `totals` and carrying the remainder in `unplaced_usd` makes last cumulative + unplaced = `totals.usd` exactly, with no special case at `latest`.
- **Null versus zero (I7).** A 0 bar claims a snapshot cost nothing; a missing line means "not traced" (014 X1, Q-100).
- **Held-out eval hides the panel (R12, X5).** Falling back to an older file would show a stale result as current.
- **"Running" from file names (R13, F3).** 012 names trace and report after the same start and writes the report last, and now writes it atomically (I10), so a report name exists only once the report is complete. Pairing by name, not by readable content, keeps a broken or omitted report from showing as a running run.
- **Charts in SVG (Q-111).** `createElementNS` with numeric attributes keeps the CSP and sink scan unchanged.

## Alternatives (rejected)
- **Run report, option B: a minimal parser in `dashboard`** (`_RunHeader` with `mode`, `status`, `started_at`, `duration_seconds`). Nothing moves, but four field names are duplicated and can drift silently. Rejected by the user (Q-108).
- **`read_summary` inside `evaluation/summary.py`** (the first Q-104 wording). Importing it loads the scorer into the dashboard. Replaced by the leaf module (Q-118).
- **Reuse `notify/atomic.write_atomic`.** `evaluation` and `telemetry` may not import `notify`; moving it to `domain` would put file I/O in the pure layer.
- **Registry fingerprint for staleness.** Rejected (Q-117).

## Constraints (non-negotiable)
- Dependency rule as R16. No new setting. No write: `evals_dir`, `runs_dir` and the registry are never created by the dashboard.
- Tests use only `tests/fixtures/` plus files written in `tmp_path` with `write_summary` and `write_report`. Never `data/`, never the model.
- Each test cites its spec id. Helpers come `from metrics_builders import ...`, `from dashboard_builders import ...`, `from trace_builders import ...`, never `from tests....`. Basenames are unique.
- The JS is not unit-tested; E19 scans it.

## Docs rows (applied in T12)
- **STRUCTURE add:** `dashboard/metrics.py`, `dashboard/panels.py`; `evaluation/summary_file.py`; `telemetry/run_report.py` and the `runner/summary.py` row; the `telemetry/trace.py` constants; `heldout.json_shown` and the `source` helpers; `src/frontend/` (`metricas.html`, `metrics.js`).
- **Dependency lines:** "`dashboard` imports only `domain`, `cases.registry`, `telemetry`, `ingestion`, `logbooks`, `config` and, from `evaluation`, only `output.RunOutput`, `noise.count_noise`, `noise.NoiseScore` and `summary_file.{EVAL_NAME, StoredSummary, read_summary}` (015 R16)"; "`evaluation/summary_file.py` imports nothing from the project but `domain`". Add `dashboard → evaluation (output, noise, summary_file)` to the diagram.
- **Roadmap row 015:** link `specs/015-analytics-dashboard/`; scope "Métricas window of the live dashboard: cost, cache and latency per snapshot, alerts and reports per day, authors, live noise, latest stored evaluation, run durations; read-only"; FR 22, 37, 38, 39, 40; US 11, 12; ADR-0022, Q-101–Q-118; priority Could.
- **README:** a "Metrics window" section under "Live dashboard": how to open it, follow vs live, accuracy from `evals/run_eval.py` (command), staleness, "Ruido evaluado" vs "Ruido en vivo", held-out omission.

## Risks
- **`RunReport` fields.** Every field added to `RunReport` later must have a default, or older reports become unreadable (counted, never shown).
- **The run-report move (T6).** 012 tests pass unchanged. An import that stops resolving is a re-export bug, never a test edit.
- **Report line endings.** `write_report` used text mode, so on Windows the file had CRLF; the atomic byte write gives LF everywhere. No test or reader depends on it (JSON).
- **The `to_json` key order.** `"deliverables"` is appended; 005 E34a checks a subset.
- **Frontend drift from the JSON.** The `TypedDict`s and examples fix the shape; T9 checks by hand.
- **mypy order:** T1 (summary_file) → T2–T3 (shared helpers) → T4–T5 (`metrics`) → T6 (run report) → T7 (`panels`) → T8 (`server`) → T9 (frontend).
