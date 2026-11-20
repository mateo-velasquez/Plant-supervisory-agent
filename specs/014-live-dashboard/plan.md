# 014 · Live dashboard with replay — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `cases/registry/readonly.py` | New | `open_readonly(path, *, timeout)`, `check_columns(conn, required)`; shared by every read-only reader. |
| `cases/registry/notices.py` | Changes | `is_deliverable(item)` next to `DELIVERABLE_FILTER`; `read_deliverables` uses `open_readonly` / `check_columns`. |
| `cases/registry/notice_reader.py` | Refactor | Uses `open_readonly` / `check_columns`; same messages. |
| `cases/registry/run_reader.py` | New | `read_run_rows(path) -> RunRows | None` (I3). |
| `domain/verbatim.py` | Adds | `verbatim_spans(text, fragment)`. |
| `telemetry/trace.py` | Adds | `CorruptTraces`, `TextBy`, `index_attempts`, `text_by` (moved from `trace_query`); `read_trace_files(..., *, drop_partial_tail=False)`. |
| `telemetry/trace_query.py` | Refactor | Imports the moved names; behavior unchanged. |
| `dashboard/__init__.py` | New | Package docstring only. |
| `dashboard/heldout.py` | New (moved) | Id patterns, `UnsafeId`, `validate_ids`, `shown_ids`, `select_shown` from `notify/html.py`; `notice_ids_valid`, `case_shown`, `history_shown`, `line_shown`. |
| `dashboard/payloads.py` | New | `TypedDict`s of the state and agents payloads and the events. |
| `dashboard/source.py` | New | `Calendar`, `Omitted`, `RunView`, `load_view` (filtered rows, traces, attempts). |
| `dashboard/state.py` | New | `build_state` (R3–R7). |
| `dashboard/agents.py` | New | `build_agents`, `conversation`, `segments`, `explain_hook` (R8–R11). |
| `dashboard/server.py` | New | `FRONTEND_DIR`, `ASSETS`, `CSP`, `Response`, `DashboardApp`, `make_server`, `serve_dashboard`. |
| `config.py` | Changes | Adds `dashboard_port`; removes `html_dir`. |
| `runner/cli.py` | Changes | Adds `DashboardOptions`, `_dashboard`, `CliDeps.serve`; removes `HtmlOptions`, `_html`, the `html` subparser. |
| `notify/html.py` | Deleted | — |
| `src/frontend/*` | New | `index.html`, `agentes.html`, `app.css`, `dom.js` (shared `h()`, fetch, BroadcastChannel), `app.js` (Planta), `agents.js` (Agentes). |
| `tests/dashboard_builders.py` | New | `run_rows(...)` and `RESUMED` (T5); `HOST`, `app_of`, `get_json` (T10); `FakeServe` (T11). |

Kept from this branch: `domain/text.escape_controls` (used by `trace_render` and the `UnsafeId` message), `notify/atomic.write_atomic` (used by `FileNotifier`), `domain/cases.case_snapshot_id` (used by `shown_ids`), `_fail` through `write_safe`.

## Types and interfaces

### `open_readonly`, `check_columns`
```python
@contextmanager
def open_readonly(path: Path, *, timeout: float = READ_TIMEOUT_S) -> Iterator[sqlite3.Connection]: ...
def check_columns(conn: sqlite3.Connection, path: Path, required: Mapping[str, frozenset[str]]) -> None: ...
```
- `open_readonly` connects with `f"{path.resolve().as_uri()}?mode=ro"`, `uri=True`, `autocommit=True` and the given `timeout`, runs `BEGIN`, yields, and then commits or rolls back. A missing file raises `ValueError(f"{path}: registry not found")` before connecting.
- `READ_TIMEOUT_S = 2.0` is a module constant: an internal read setting, not a domain threshold.
- `check_columns` raises the existing `notice_reader` messages (`table X not found` / `lacks [...]`).
- `read_deliverables` and `notice_reader` keep their messages; their 004/013 tests stay green.

### `is_deliverable`
`is_deliverable(item: Notice | ShiftReport) -> bool`: true for a `ShiftReport` or for `tipo is NoticeType.ALERT`. Its docstring says it mirrors `DELIVERABLE_FILTER`, and E23 checks that they agree.

### `read_run_rows`
```python
@dataclass(frozen=True)
class ProcessedRow: snapshot_id: str; seq: int
@dataclass(frozen=True)
class CaseRow: case_id: str; combination: Combination; opened_at: str
@dataclass(frozen=True)
class HistoryAt: seq: int; row: CaseHistoryRow
@dataclass(frozen=True)
class NoticeAt: seq: int; idx: int; item: Notice | ShiftReport
@dataclass(frozen=True)
class RunRows:
    processed: tuple[ProcessedRow, ...]   # seq order
    cases: tuple[CaseRow, ...]
    history: tuple[HistoryAt, ...]        # seq order
    notices: tuple[NoticeAt, ...]         # (seq, idx) order, every kind and tipo
class RegistryBusy(ValueError): ...
def read_run_rows(path: Path) -> RunRows | None: ...
```
- A missing file returns `None` and is never created.
- `sqlite3.OperationalError` "database is locked" raises `RegistryBusy("dashboard: registry busy")`.
- Any other `sqlite3.Error`, a missing table or column, or a payload that does not parse raises `ValueError(f"dashboard: {path.name} is not a readable registry ({type(e).__name__})")`, with no stored values in it (I7).

### `verbatim_spans`
`verbatim_spans(text: str, fragment: str) -> tuple[tuple[int, int], ...]`: the non-overlapping matches of `r"\s+".join(map(re.escape, fragment.split()))` in `text`. Returns `()` for a blank fragment. It agrees with `contains_verbatim`.

### `telemetry/trace.py` additions
```python
class CorruptTraces(ValueError): ...
type TextBy = Literal["agent", "template", "unknown"]
def index_attempts(files: Sequence[TraceFile]) -> tuple[dict[str, tuple[str, TraceLine]], dict[str, tuple[tuple[str, TraceLine], ...]]]: ...
def text_by(notice_id: str, line: TraceLine | None, mode: TraceMode) -> TextBy: ...
def read_trace_files(directory: Path, *, drop_partial_tail: bool = False) -> tuple[TraceFile, ...]: ...
```
- `index_attempts` walks the files and lines in order. It returns committed lines by snapshot, and aborted lines by snapshot, in order. The first duplicate committed line raises `CorruptTraces(f"two committed lines for {sid} ({first_file}, {second_file})")`. `trace_query` keeps its per-notice behavior by indexing once.
- `drop_partial_tail=True` drops a non-empty segment after the last `\n` of each file. Its error message is unchanged (`<name> is not a readable trace file (<ErrorClass>)`); the dashboard prefixes `traces: ` and strips the parenthesis (I7).

### `dashboard/heldout.py`
```python
SNAPSHOT_ID, SHIFT_ID, CASE_ID, NOTICE_ID  # moved verbatim ([0-9], never \d)
class UnsafeId(ValueError): ...            # "dashboard: invalid <field>: <escape_controls(value)>"
@dataclass(frozen=True)
class ShownIds: snapshots: frozenset[str]; shifts: frozenset[str]
def validate_ids(item: Notice | ShiftReport) -> None: ...
def notice_ids_valid(notice: Notice) -> bool: ...
def shown_ids(item: Notice | ShiftReport) -> ShownIds: ...
def select_shown(items, policy) -> tuple[tuple[Notice | ShiftReport, ...], int]: ...
def case_shown(row: CaseRow, policy: HeldOutPolicy) -> bool: ...
def history_shown(row: HistoryAt, policy: HeldOutPolicy) -> bool: ...
def line_shown(line: TraceLine, policy: HeldOutPolicy) -> bool: ...
```
- `line_shown`: the line is shown when the guard is open. Otherwise `snapshot_id` and `turno_id` must match their patterns, and no token of `re.compile(r"\b(?:S[0-9]{3}|T[0-9]{2})\b")` in `line.model_dump_json()` may be refused.

### `dashboard/source.py`
```python
@dataclass(frozen=True)
class Calendar:
    shifts: tuple[Shift, ...]                 # calendar order, refused removed
    combinations: tuple[Combination, ...]     # plan combos in all_combinations() order
    @classmethod
    def load(cls, plant_dir: Path, policy: HeldOutPolicy) -> Calendar: ...
@dataclass(frozen=True)
class Omitted: snapshots: int; notices: int; trace_lines: int
@dataclass(frozen=True)
class RunView:
    registry: Literal["ok", "missing"]
    rows: RunRows                               # filtered (R13); empty when missing
    deliverables: tuple[NoticeAt, ...]          # is_deliverable + select_shown
    lines: tuple[tuple[str, TraceLine], ...]    # (file, line), filtered
    committed: Mapping[str, TraceLine]
    aborted: Mapping[str, tuple[TraceLine, ...]]
    trace_error: str | None
    mode: TraceMode
    omitted: Omitted
    policy_open: bool
    def positions(self) -> tuple[int, ...]: ...
    def resolve_at(self, at: int | None) -> int: ...
def load_view(registry_path: Path, traces_dir: Path, policy: HeldOutPolicy) -> RunView: ...
```
`load_view` reads the rows (and lets `RegistryBusy` and `ValueError` through), reads the traces with `drop_partial_tail=True`, applies R13 and calls `index_attempts`. A `CorruptTraces` or a trace `ValueError` sets `trace_error` and empties `committed` / `aborted`.

### `dashboard/payloads.py`
`TypedDict`s with total keys: `StatePayload`, `Header`, `Day`, `ShiftCell`, `SnapshotCell`, `Kpis`, `Cost`, `Cell`, `CaseView`, `NoticeItem`, `ReportItem`, `HeldOut`, `AgentsPayload`, `SnapshotEntry`, `Selected`, and one `TypedDict` per event kind, joined in `type Event = DecisionEvent | ThinkingEvent | LogbookReadEvent | ...`. No `dict[str, JsonValue]` in the dashboard signatures. Proposals and `casos_activos` rows are passed as stored: `JsonValue` only in those two fields.

### `dashboard/state.py`
`build_state(view: RunView, calendar: Calendar, at: int) -> StatePayload`, with the private `_header`, `_days`, `_kpis`, `_cells` (tie-break of R6), `_feed` and `_cost(lines)` (`run_totals` → `Cost`).

### `dashboard/agents.py`
```python
def build_agents(view: RunView, logbooks: LogbookStore, at: int, snapshot: str | None) -> AgentsPayload: ...
def conversation(line: TraceLine, logbooks: LogbookStore) -> list[Event]: ...
def segments(text: str, fragments: Sequence[str]) -> list[tuple[str, bool]]: ...
def explain_hook(hook: TraceHook) -> str | None: ...
```

| Hook pattern (full match) | `reason_es` |
|---|---|
| `tool (?P<tool>\S+) is not allowed for the (?P<agent>investigator\|coordinator)` | `El {coordinador\|investigador} no tiene permiso para usar {tool}: cada agente solo usa sus herramientas.` |
| `(?P<case>\S+): no news since last report` | `{case} no tiene novedades desde el último informe: el aviso no se repite.` |
| `texto for (?P<case>\S+) names cause (?P<named>\S+); its causa is (?P<causa>\S+)` | `El texto de {case} nombra la causa {named}, pero la causa registrada es {causa}.` |
| `texto for (?P<case>\S+) states .+: below notice severity \(.+\)` | `El texto de {case} declara una severidad menor que la del aviso.` |

### `dashboard/server.py`
```python
FRONTEND_DIR: Final = Path(__file__).resolve().parents[2] / "frontend"
ASSETS: Final[Mapping[str, tuple[str, str]]]  # route -> (file name, content type), R14
CSP: Final = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
              "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
ALLOWED_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})
@dataclass(frozen=True)
class Response: status: int; headers: tuple[tuple[str, str], ...]; body: bytes
class DashboardApp:
    def __init__(self, *, calendar: Calendar, logbooks: LogbookStore, policy: HeldOutPolicy,
                 registry_path: Path, traces_dir: Path, assets: Mapping[str, bytes]) -> None: ...
    @classmethod
    def from_settings(cls, settings: Settings, frontend_dir: Path = FRONTEND_DIR) -> DashboardApp: ...
    def handle(self, method: str, target: str, host: str | None) -> Response: ...
def make_server(app: DashboardApp, port: int) -> ThreadingHTTPServer: ...   # binds 127.0.0.1 only
def serve_dashboard(app: DashboardApp, port: int, on_ready: Callable[[int], None]) -> None: ...
```
- `from_settings` runs R1 steps 2–5. It loads every asset's bytes once and raises `ValueError("dashboard: frontend asset not found: <name>")`.
- `handle` runs in this order:
  1. method (405);
  2. Host: `host.rsplit(":", 1)[0]` when it ends in `:<digits>`, compared with `ALLOWED_HOSTS` (403);
  3. route (404);
  4. the asset, or the API: `RegistryBusy` → 503, `ValueError` → 500.
- `serve_dashboard` calls `server = make_server(app, port)`, then `on_ready(server.server_address[1])`, then `serve_forever()`, and finally `server_close()`.
- The handler class maps every `do_*` to `handle`, and its `log_message` is a no-op.

### `main` (dashboard branch)
- `@dataclass(frozen=True) class DashboardOptions` has no fields. `parse_args -> RunOptions | TraceOptions | DashboardOptions`.
- `CliDeps.serve: Callable[[DashboardApp, int, Callable[[int], None]], None] = serve_dashboard`.
- `_dashboard(settings, deps) -> int`:
  - builds `app = DashboardApp.from_settings(settings)`;
  - calls `deps.serve(app, settings.dashboard_port, on_ready)`, where `on_ready(port)` writes `dashboard: http://127.0.0.1:{port}/ (Ctrl+C to stop)\n` through `write_safe`;
  - `KeyboardInterrupt` → 0; an `OSError` → `_fail("dashboard: cannot listen on 127.0.0.1:<port> (<ErrorClass>)")`; `DataLoadError` / `ValueError` during setup → `_fail`.

### `Settings.dashboard_port`
`dashboard_port: int = Field(default=8765, ge=1, le=65535)`, docstring "Local port of the dashboard (127.0.0.1 only)." Added to `.env.example`. `html_dir` is removed.

### Frontend link forms (E21)
The only allowed `.href =` and `window.open(` forms are `"/agentes"` and `` `/agentes#${sid}` `` where `sid` passed `/^S[0-9]{3}$/`. The scan accepts exactly these two forms.

## API

`GET /api/state?at=N` (shape; numbers illustrative, the examples are normative):
```json
{"at": 12, "latest": 12, "positions": [1, 2, 3], "total": 12, "complete": true,
 "registry": "ok", "trace_error": null,
 "heldout": {"open": true, "omitted": {"snapshots": 0, "notices": 0, "trace_lines": 0}},
 "current": {"snapshot_id": "S012", "seq": 12, "turno_id": "T06", "turno": "noche", "inicio": "22:00", "fin": "06:00", "fecha": "3/3/2026"},
 "days": [{"label": "3/2/2026", "shifts": [{"turno_id": "T01", "turno": "mañana", "inicio": "06:00", "fin": "14:00",
           "snapshots": [{"snapshot_id": "S001", "processed": true, "alerts": 0, "report": false}]}]}],
 "kpis": {"active": 3, "combinations": 9, "critical": 1, "critical_combinations": ["Pickup × Local"],
          "alerts": 4, "reports": 6, "shifts": 6, "cost": {"usd": "0.00000000", "model_calls": 0, "tokens": 0}},
 "models": ["Sedán", "SUV", "Pickup"], "markets": ["Local", "Brasil", "Europa"],
 "cells": [{"modelo": "Pickup", "mercado": "Local", "status": "active",
            "case": {"case_id": "S010-Pickup-Local", "estado": "escalado", "severidad": "critica", "gap_unidades": -11.0,
                     "gap_pct": -36.66667, "retraso_dias": 0.0, "etapa_cuello": null, "causa": "no_declarada",
                     "etapa": null, "opened_at": "S010", "resolved_at": null},
            "series": [null, null, -11.0]}],
 "feed": [{"kind": "alert", "seq": 12, "notice_id": "…", "snapshot_id": "S012", "case_id": "S010-Pickup-Local",
           "modelo": "Pickup", "mercado": "Local", "severidad": "critica", "severidad_maxima": "critica", "estado": "escalado",
           "motivo": ["gap"], "origen": "umbral", "causa": {"categoria": "no_declarada", "etapa": null},
           "evidencia": [], "texto": "…", "author": "template"},
          {"kind": "report", "seq": 12, "report_id": "T06-informe", "turno_id": "T06", "snapshot_id": "S012",
           "novedades": ["<NoticeItem>"], "casos_activos": ["<rows as stored>"]}]}
```

`GET /api/agents?at=N&snapshot=S010`:
```json
{"at": 10, "latest": 10, "trace_error": null, "heldout": {"open": true, "omitted": {"snapshots": 0, "notices": 0, "trace_lines": 0}},
 "kpis": {"investigator": 5, "coordinator": 5, "hook_blocks": 1, "cost": {"usd": "0.00760000", "model_calls": 19, "tokens": 60800}},
 "snapshots": [{"snapshot_id": "S010", "seq": 10, "turno_id": "T05", "agents": ["investigator", "coordinator"],
                "hook_blocks": 1, "model_calls": 5, "usd": "0.00200000", "previous_attempts": 0, "traced": true}],
 "selected": {"snapshot_id": "S010", "seq": 10, "turno_id": "T05", "previous_attempts": 0, "model_calls": 5, "usd": "0.00200000",
   "events": [
   {"lane": "code", "kind": "decision", "decision": "call", "decision_reason": "text_needed", "required": 4, "agents": ["investigator", "coordinator"]},
   {"lane": "investigator", "kind": "logbook_read", "turn": 1, "turno_id": "T05", "is_error": false, "error": null,
    "logbook": {"segments": [{"text": "…", "mark": false}, {"text": "…", "mark": true}]}, "note": null},
   {"lane": "investigator", "kind": "proposal", "proposal": {"id": "S010-p1", "tipo": "raise"}},
   {"lane": "investigator", "kind": "agent_cost", "agent": "investigator", "model_calls": 2, "usd": "0.00080000"},
   {"lane": "code", "kind": "validation", "applied": ["S010-p1"], "declined": []},
   {"lane": "coordinator", "kind": "tool_call", "turn": 1, "name": "apply_proposal", "proposal": "S010-p1", "is_error": false, "error": null},
   {"lane": "code", "kind": "hook_block", "agent": "coordinator", "phase": "pre_tool", "hook": "allowlist", "tool": "get_logbook",
    "turn": 2, "reason": "tool get_logbook is not allowed for the coordinator", "reason_es": "El coordinador no tiene permiso …"},
   {"lane": "coordinator", "kind": "tool_call", "turn": 3, "name": "emit_alert", "case_id": "S010-Pickup-Local", "texto": "…"},
   {"lane": "coordinator", "kind": "tool_call", "turn": 3, "name": "emit_shift_report", "items": [{"case_id": "…", "texto": "…"}]},
   {"lane": "coordinator", "kind": "agent_cost", "agent": "coordinator", "model_calls": 3, "usd": "0.00120000"},
   {"lane": "code", "kind": "registration", "agent": 4, "template": 0, "report_id": "T05-informe"}]}}
```
Other event kinds: `thinking` (`texts`), `control_error` (`messages`), `no_proposals`, and `tool_call` for any other tool (`arguments_json`, compact JSON). Argument values that are not strings come out as `null` in the typed fields.

## Data flow
```
startup: Settings → turnos.csv → HeldOutPolicy → Calendar (plan) → LogbookStore → assets loaded → bind 127.0.0.1 → on_ready(port)
request: method → Host name → route → load_view(open_readonly + timeout, one transaction; is_deliverable; traces drop_partial_tail;
         R13 filter; index_attempts) → resolve_at → build_state | build_agents (+ LogbookStore.get) → json.dumps(ensure_ascii=True)
client:  live poll (no at) | replay (at=N, ▶/⏸, step, slider, speed) → BroadcastChannel("plant-monitor") → Agentes
         503 busy → keep last good payload
```

## Design notes
- **Why stateless `at` (I1).** Replay holds no state on the server, so two windows and a reload all agree, the server stays GET-only and writes nothing, and every view is a pure function of (files, policy, N) that pytest can test. Play, pause and speed are UI timing. Planta posts `{mode, at}`. Agentes uses it while it is not pinned, and polls on its own when nothing is broadcast.
- **One transaction for everything (I3).** Deliverables come from `RunRows.notices`, so the feed, cells and KPIs describe the same committed state. `is_deliverable` sits next to `DELIVERABLE_FILTER`, and E23 locks the two together.
- **Why per-case notice rows give the cause (R6).** `case_causes` holds only the latest cited cause (an upsert). Every evaluated case gets a decision notice per snapshot, each with its `causa`.
- **Why Python builds events and segments (I2).** Their order, the hook/tool pairing and the whitespace-tolerant highlights are rules. Offsets would also break between Python code points and JS UTF-16, so the server sends text segments instead.
- **Held-out on trace lines by token scan (I5).** A field list would drift as the trace grows. The scan is strict and complete, and lines at allowed snapshots never name held-out ids in practice (Q-01).
- **Host name check (Q-98).** Binding to `127.0.0.1` does not stop DNS rebinding. The check compares only the host name, so port 0 in tests and any configured port pass.
- **URL after bind (R1).** `on_ready` reports the bound port, so the printed URL is true even for port 0, and nothing is printed when the bind fails.
- **Busy vs corrupt (R2).** The run writes in short transactions. A read that waits out the timeout is busy, not broken, so the client keeps its last payload instead of showing a corruption banner.
- **No caching (X5).** Each request rebuilds the view; correctness during a live run matters more.
- **Frontend outside the package (Q-96).** `uv_build` packages only `plant_monitor`, so the assets do not ship in a wheel. `uv run` uses the editable install, so `parents[2]` is `src/`, and startup fails with exit 2 if the assets are missing.

## Constraints (non-negotiable)
- Dependency rule as R16. The single writer is unchanged: every reader uses `open_readonly`. No `model_copy` in `dashboard`.
- Tests use only `tests/fixtures/` (`write_cli_data`, the `multi_agent_builders` scripts with `FakeModel`), never `data/`. CI never calls the model.
- Each test cites its spec id. Helpers come `from dashboard_builders import ...` / `from trace_builders import ...`, never `from tests....`. Basenames are unique.
- Server logic is tested without a socket (`handle`, `build_state`, `build_agents`), plus one real-socket test (E17). The JS is not unit-tested; E21 scans it.

## ADR-0021 text (the implementer transcribes it, renaming the file to `0021-local-read-only-live-dashboard.md`)
> **0021 · Local read-only live dashboard with replay** — Status: Accepted. Date: on merge.
>
> **Context.** The plant manager needs to see the run as it happens and to replay it for the demo. Static post-run pages were built on the branch and rejected for their look before merge; a prototype with JS was approved.
>
> **Decision.**
> - `plant-monitor dashboard` serves a local dashboard on `127.0.0.1:DASHBOARD_PORT` with the standard-library `http.server`. It reads `OUTPUT_DIR` only: the registry with `mode=ro` in one transaction and the trace files. It never calls the model or writes anything.
> - Endpoints are stateless and take an optional `at=<seq>`. The client owns live polling and replay, and syncs the Agentes window over `BroadcastChannel`.
> - Python builds every rule-bearing view. The frontend is small hand-written JS with no framework, library or build step, and inserts values only as text nodes. A test checks for the forbidden sinks.
> - Every response sends `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. The server accepts GET only, serves an explicit asset allowlist and checks the `Host` name.
> - With `HELDOUT_OPEN=false`, held-out and unverifiable items are omitted and counted.
> - The frontend lives in `src/frontend/`, outside the `plant_monitor` package. It does not ship in a wheel; the project runs from the repo with `uv run`, and startup fails if the assets are missing.
>
> **Consequences.** There is no new dependency. The JS is covered only by the sink scan and manual review. A registry or trace schema change must update `run_reader` and the read model. Rejected: static HTML pages (look), React or another framework (build step and dependencies), a server-held replay position (needs writes).

## Docs rows (applied in T13)
- **STRUCTURE remove:** `notify/html.py`; `html` and `HtmlOptions` from `runner/cli.py`; `html_dir` from `config.py`. Update `notify/atomic.py` (shared by `FileNotifier` only) and `domain/text.py` (shared by `trace_render` and `dashboard/heldout.py`).
- **STRUCTURE add:**
  - one row per `dashboard/*` module;
  - `src/frontend/` (assets, not packaged);
  - `cases/registry/readonly.py` and `run_reader.py`, and `notices.is_deliverable`;
  - `telemetry/trace.py` (`index_attempts`, `text_by`, `CorruptTraces`, `drop_partial_tail`);
  - `domain/verbatim.verbatim_spans`;
  - `config.py` `dashboard_port`;
  - `runner/cli.py` `dashboard`, `DashboardOptions`, `CliDeps.serve`.
- **Dependency line:** "`dashboard` imports only `domain`, `cases.registry`, `telemetry`, `ingestion`, `logbooks` and `config`; only `runner/cli.py` imports `dashboard`. `cases/registry/run_reader.py` and `readonly.py` import only `domain` and `cases.registry`." Add `cli → dashboard` to the diagram.
- **Roadmap row 014:** link `specs/014-live-dashboard/`, scope "`plant-monitor dashboard`: local live dashboard with replay (Planta, Agentes), read-only", ADR-0021, Q-84–Q-100.

## Risks
- **The frontend drifts from the JSON.** The `TypedDict`s and the examples fix the shape, and T12 checks the views by hand.
- **Windows sockets in CI.** E17 uses port 0 and `on_ready`, and shuts the server down in `finally`.
- **Shared reader refactor (T2).** `open_readonly` changes `read_deliverables` from autocommit selects to one `BEGIN … COMMIT`. The 004/013/005 tests must stay green unchanged; any message change is a bug.
- **mypy order.** T2 (shared helpers) → T3 (`run_reader`) → T4 (`heldout`) → T5 (`source`) → T6–T9 → T10 (`server`) → T11 (CLI).
