# 013 · Alert trace for the demo — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `domain/stored.py` | New | `StoredNotice`: one notice's stored facts, domain types only (I7). |
| `cases/registry/notice_reader.py` | New | `read_notice`: read-only `mode=ro`, one read transaction (ADR-0011, ADR-0019 pattern). |
| `cases/registry/cases_repo.py`, `causes_repo.py` | Refactor | Public `HISTORY_COLUMNS`, `history_from_row`, `ACTIVE_COLUMNS`, `active_from_row`, `CITED_COLUMNS`, `cited_from_row`. The column lists are tuples, joined at each SQL site (I6). |
| `telemetry/trace.py` | Adds | `TraceMode` (I9), `TraceFile`, `read_trace_files` (I10). |
| `telemetry/trace_query.py` | New | View dataclasses, `CorruptTraces`, `build_notice_trace`. Pure. |
| `telemetry/trace_render.py` | New | `escape_controls`, `render_notice_trace`. Pure. |
| `notify/console.py` | Refactor | Public `write_safe(text, stream)`; `ConsoleNotifier._write` calls it (I5). |
| `runner/summary.py` | Refactor | `Mode = TraceMode` (alias, I9). |
| `runner/cli.py` | Changes | `TraceOptions`, subcommand-aware `parse_args`, `_trace`, `_read_traces`; `main` dispatch; `_report` uses `read_trace_files`. |
| `tests/trace_builders.py` | New | Hand-built inputs; later `S010_EMIT_HOOKED`, `PRICES`, the directory fixtures and `traced`. |
| `tests/incident_runs.py` | Changes | `incident_run(..., path=":memory:")`. |
| `docs/demo.md` | New (draft) | Steps, timings, live command, candidate alerts, dry run. |
| Registry schema, trace schema, pipelines, `series.py` | Unchanged | — |

## Types and interfaces

### `StoredNotice`
`domain/stored.py`, `@dataclass(frozen=True)`:
- `notice: Notice`;
- `history: tuple[CaseHistoryRow, ...]` (the case's rows by `seq`);
- `order: Mapping[str, int]` (`processed_snapshots` id → `seq`);
- `causes: tuple[ActiveCause, ...]` (linked to the case, by `seq`);
- `links: Mapping[str, str]` (active cause id → `linked_at`);
- `cited: CitedCause | None`.

### `read_notice`
`cases/registry/notice_reader.py`:
- `read_notice(path: Path, notice_id: str) -> StoredNotice | ShiftReport | None`.
- `ValueError(f"{path}: registry not found")` when the path is not a file.
- Connection:
  - `sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, autocommit=True)` inside `closing`;
  - then `BEGIN`, every read, `COMMIT`, with `ROLLBACK` on any error. That gives one consistent state while a run may be committing.
- Column check: `_NEEDS: Mapping[str, frozenset[str]]`, built from the tuples. Each table is checked with `PRAGMA table_info`:
  - `notices`: `notice_id`, `kind`, `payload`;
  - `case_history`: `HISTORY_COLUMNS` + `seq`;
  - `processed_snapshots`: `snapshot_id`, `seq`;
  - `active_causes`: `ACTIVE_COLUMNS` + `seq`;
  - `active_cause_links`: `active_cause_id`, `case_id`, `linked_at`;
  - `case_causes`: `CITED_COLUMNS`.
- Errors: a missing table or column is a `ValueError` naming it, and `sqlite3.Error` becomes `ValueError`. No `user_version` check.
- Payloads are parsed with `Notice.model_validate_json` / `ShiftReport.model_validate_json`. A bad payload is a `ValueError(f"{path}: unreadable payload of {notice_id}")`, one line.

### `TraceFile`, `read_trace_files`, `TraceMode`
`telemetry/trace.py`:
- `TraceMode = Literal["agent", "thresholds_only"]`.
- `@dataclass(frozen=True) class TraceFile`: `name: str`, `lines: tuple[TraceLine, ...]`.
- `read_trace_files(directory: Path) -> tuple[TraceFile, ...]`: `sorted(directory.glob("trace-*.jsonl"))`, each through `read_trace`. A missing directory gives `()`.
  - A file that fails to parse (`ValueError`, which covers pydantic's `ValidationError` and `UnicodeDecodeError`) is re-raised as the one-line `ValueError(f"{name} is not a readable trace file ({type(exc).__name__})")`.
  - `OSError` propagates.
  - 012's `_report` keeps its `summary unavailable: …` path unchanged.

### `build_notice_trace`
`telemetry/trace_query.py`. Every type is a `@dataclass(frozen=True)` (I8):
- `class CorruptTraces(ValueError)`: message `two committed lines for <S> (<file>, <file>)`, with no prefix.
- `TextBy = Literal["agent", "template", "unknown"]`.
- `HistoryView`: `row: CaseHistoryRow`, `previous: CaseHistoryRow | None`, `at_notice: bool`, `opened_at: str` (the first row's snapshot).
- `CallView`: `call: TraceToolCall`, `this_case: bool`.
- `AgentView`: `agent: AgentName`, `outcome: str`, `trigger: str | None`, `calls: tuple[CallView, ...]`, `proposals: tuple[Mapping[str, JsonValue], ...]`.
- `AbortedAttempt`: `file: str`, `outcome: str`, `investigator_outcome: str | None`, `totals: TraceTotals`.
- `LineView`: `file: str`, `decision: str`, `decision_reason: str | None`, `agents: tuple[AgentView, ...]`, `no_agent: bool`, `hooks: tuple[TraceHook, ...]`, `totals: TraceTotals`.
- `Opening`: `snapshot_id: str`, `status: Literal["found", "no_line", "no_proposal"]`, `file: str | None`, `proposal: Mapping[str, JsonValue] | None`, `apply: TraceToolCall | None`.
  - Invalid combinations are refused by a `__post_init__` check, raising `ValueError`:
    - `found` ⇔ `file`, `proposal` and `apply` all set;
    - `no_proposal` ⇔ `file` set, the other two None;
    - `no_line` ⇔ all three None.
  - A check was chosen over three variant classes, because the renderer then needs one `match` on `status`.
- `CauseView`: `cause: ActiveCause`, `linked_at: str`, `lift_shown: bool`, `opening: Opening | None` (None in threshold-only mode).
- `NoticeTrace`:
  - fields `notice: Notice`, `history: HistoryView`, `cited: CitedCause | None` (only when R4 matches), `causes: tuple[CauseView, ...]`, `mode: TraceMode`, `line: LineView | None`, `aborted: tuple[AbortedAttempt, ...]`, `text_by: TextBy`;
  - methods `shown_snapshots() -> frozenset[str]` and `shown_shifts() -> frozenset[str]`, exactly the R11 sets.
- `build_notice_trace(stored: StoredNotice, traces: Sequence[TraceFile] | None) -> NoticeTrace`:
  - `traces=None` means threshold-only;
  - `ValueError` when no history row is at or before the snapshot, or a snapshot id is missing from `order`;
  - `CorruptTraces` on a duplicate committed line of a used snapshot.
- Private helpers:
  - `_applied(line) -> tuple[tuple[TraceToolCall, ValidatedProposal, Mapping[str, JsonValue]], ...]`: R6 step 1. Parsing goes through `ValidatedProposal.model_validate({"id": …, "proposal": rest})`; a `ValidationError` drops the item;
  - `_raise_match(line, cause) -> tuple[TraceToolCall, Mapping[str, JsonValue]] | None`: R6 steps 2–4;
  - `_marks(...)`: R8.

### `render_notice_trace`
`telemetry/trace_render.py`:
- `escape_controls(text: str) -> str`: R12 ranges to `\xHH`.
- `render_notice_trace(trace: NoticeTrace) -> str`: the R12 lines, each escaped, joined by `\n` with no final newline.
- Private helpers:
  - `_number(value: float) -> str`: `round_display(value) + 0.0`, formatted with `DECIMALS` places;
  - `_usd(value: Decimal) -> str`: `format(value.quantize(USD_DECIMALS), "f")`;
  - `_json(value: object) -> str`: R12 compact form;
  - `_tokens(totals: TraceTotals) -> str`: shared by the tokens and aborted lines.

### `write_safe`
`notify/console.py`: `write_safe(text: str, stream: TextIO) -> None`. It encodes with `getattr(stream, "encoding", None) or "utf-8"` and `backslashreplace`, then writes and flushes. `ConsoleNotifier._write` becomes a call to it with `text + "\n"`, so its output is byte-identical.

### `main` (trace branch)
`runner/cli.py`:
- `@dataclass(frozen=True) class TraceOptions`: `notice_id: str`.
- `parse_args(argv: Sequence[str] | None) -> RunOptions | TraceOptions`: adds the `trace` subparser with a positional `NOTICE_ID`; `run` is unchanged.
- `main`: parse (same `SystemExit` handling), then settings (same `ValidationError` message). Then `isinstance(opts, TraceOptions)` → `_trace(opts, settings)` inside the same `except (DataLoadError, ValueError, OSError, sqlite3.Error)` → `_fail` (2). No logging setup, no key check, no `mkdir`.
- `_trace(opts: TraceOptions, settings: Settings) -> int`, in order:
  1. `policy` from `load_shifts(settings.plant_dir / _SHIFTS_FILE)`, `heldout_first_shift`, `heldout_open`;
  2. `stored = read_notice(settings.registry_path, opts.notice_id)`;
  3. `None` → stderr `unknown notice_id: …`, return 1;
  4. `check_ids` on the notice, or on the `ShiftReport` (`snapshot_id`, `turno_id`) (R11);
  5. `ShiftReport` → stderr `report_id_for(turno_id)` and the `novedades` ids (R3), return 1;
  6. `traces = _read_traces(settings.traces_dir)`;
  7. `view = build_notice_trace(stored, traces)`; `except CorruptTraces as exc: raise ValueError(f"traces: {exc}") from exc`;
  8. `check_ids(policy, snapshots=view.shown_snapshots(), shifts=view.shown_shifts(), where=...)`;
  9. `write_safe(render_notice_trace(view) + "\n", sys.stdout)`, return 0.
- `_read_traces(directory: Path) -> tuple[TraceFile, ...] | None`: `read_trace_files`; `()` → None. A `ValueError` from it is re-raised as `ValueError(f"traces: {exc}")`, so stderr is one line.
- `_report`: `series_lines = [line for f in read_trace_files(settings.traces_dir) for line in f.lines]`.

### Test builders
`tests/trace_builders.py` (imports `from cli_builders import ...`, `from multi_agent_builders import ...`):
- From T1: hand-built inputs for E9, E10, X1–X4 and X10:
  - `history_row(...)`;
  - `committed_line(...)` (`TraceLine.model_validate` with defaults);
  - `trace_file(name, *lines)`;
  - `stored(notice, history, causes=(), links=None, cited=None, order=None)`, a `StoredNotice` whose `order` defaults to the rows' snapshots in order.

  Notices come from `notice_builders` where it fits.
- From T3:
  - `S010_EMIT_HOOKED`;
  - `PRICES: dict[str, Decimal]` (the spec values);
  - module-scoped fixtures `agent_dir` and `thresholds_dir` over `tmp_path_factory`, each returning the `Settings` it used;
  - `copied(settings, tmp) -> Settings`: `shutil.copytree` of `output_dir`, for tests that mutate it;
  - `traced(settings, notice_id, capsys) -> tuple[int, str, str]`.

## Data flow
```
argv → parse_args → TraceOptions
settings → turnos.csv → HeldOutPolicy
registry.sqlite3 (mode=ro, one read txn) → read_notice → StoredNotice | ShiftReport | None
                                       → check_ids (snapshot, evidence)
traces/trace-*.jsonl → read_trace_files → TraceFile[] | None
StoredNotice + TraceFile[] → build_notice_trace → NoticeTrace → check_ids (shown ids)
NoticeTrace → render_notice_trace → escape per line → write_safe(stdout)
```

## Design notes
- **Read-only by construction.** The reader never touches `SqliteRegistry`, whose constructor creates or migrates the file. A `?mode=ro` URI cannot write. E8 checks bytes and paths.
- **One read transaction.** A deferred `BEGIN` takes a shared lock at the first read and holds it to `COMMIT`. All tables are therefore read from one committed state, even while `run --speed` commits between snapshots.
- **No model, single writer untouched.** The trace never builds `CliDeps.model_factory`, the pipelines or the ledger (ADR-0003).
- **Notices are shown, never rebuilt.** The stored payload is the contract (FR-25). No `model_copy`, no template call, no threshold reload (ADR-0002).
- **Why `StoredNotice` is in `domain`.** Both `cases` (which builds it) and `telemetry` (which consumes it) may import `domain`, and neither may import the other. A domain dataclass is the only shared home that keeps `build_notice_trace` to one argument and the reader free of tuples.
- **Why telemetry owns the view and the renderer.** The view joins registry facts with trace lines, and `cases` may not import `telemetry`. Rendering next to the view keeps `runner/summary.py`'s rule and leaves `cli.py` as composition only (I2).
- **Raise match (R6).**
  - What is stored: `apply_proposal` stores only the proposal id, and the tool result is not traced.
  - Fields: the match parses each traced proposal back into the domain types and compares typed values: scope, category, and `Evidence` with `fragmento.strip()`, which is how `_cited` stores it. Stringly-typed dict comparison would hide `null` against a missing `mercado`.
  - Ordinal: the cross-check rests on `CauseLedger.raise_severity`, which assigns `active_cause_id_for(S, opened_count(S) + 1)`, and on causes never being deleted.
  - Refused applies: they open nothing, which is why only `is_error = false` applies count.
  - Ambiguity: any doubt shows "no matching proposal", never a guess (§6 spirit, ADR-0002).
- **Frozen dataclasses for the view (I8).** The inputs are already validated domain and trace types; a second pydantic pass would only add multi-line errors.
- **Calendar order from `seq`.** "At or before" compares `processed_snapshots.seq`; ids are never compared as strings (Q-01).
- **Duplicates only where used (R7).** A whole-directory check would name held-out snapshot ids in an error, and would block every trace over one unrelated bad line.
- **Escaping per line (I3).** One choke point; a field added later is covered too.
- **Exit 1 vs 2.** 1 means "not a notice"; 2 means "setup or stored data cannot be trusted". This mirrors the evaluator CLI.
- **Dependency rule additions** (docs, T10):
  - "`telemetry/trace_query.py` and `telemetry/trace_render.py` import only `domain` and `telemetry`";
  - "`cases/registry/notice_reader.py` imports only `domain` and `cases.registry`; it is the trace's only registry reader (ADR-0019)".

## Test strategy
- **Unit, telemetry files** (`tests/unit/telemetry/test_trace.py`, existing): E14.
- **Unit, reader** (`tests/unit/cases/test_notice_reader.py`): E11, on a file built through the real writers via `incident_run(path=…)` and the 008 raise. E12 goes into `tests/unit/test_import_boundaries.py`.
- **Unit, query** (`tests/unit/telemetry/test_trace_query.py`): E9, X1, X2, X3, X10, from hand-built `StoredNotice`s and `TraceLine`s.
- **Unit, renderer** (`tests/unit/telemetry/test_trace_render.py`): E10, X4, over views from `build_notice_trace`.
- **CLI integration** (`tests/integration/test_trace_cli.py`): E1–E8 and E13 through `main(argv, deps=cli_deps(...))`, with `isolate_settings_env` and `capsys`.
  - AGENT_DIR and TH_DIR are module-scoped; E13 works on copies.
  - E1–E3 compare stdout byte for byte. E1 also runs the R11 drift guard, building the view with `read_notice`, `read_trace_files` and `build_notice_trace`.
- Every test cites its spec id. Variants share one parametrized test (E4, E7, E8, E13, X2, X4, X10).

## Risks
- **A byte-exact block drifts from the IF.** The numbers in E1–E3 come from the IF plant data (see the note under E1); prices are pinned by PRICES. If a test shows a different metric, check the IF arithmetic first. Change the spec block only with the user.
- **Reading during a live run.** In rollback-journal mode the read transaction's shared lock makes a committing `run` wait. The reads take milliseconds, under sqlite3's default 5 s busy timeout. Not tested: a race test would be flaky for little value.
- **Missing fields on Demo Day.** The real held-out directory is checked by hand (T4). X3 keeps old lines readable.
- **Encoding on the demo console.** `write_safe` (I5). The rehearsal (T6) runs in the demo terminal.
- **Held-out leak.** R11 checks before reading traces and again over everything shown. The E1 drift guard fails if a shown id escapes the sets.
- **mypy order.** See tasks.md: the telemetry additions land before the query, and `write_safe` lands with the CLI.
