# 012 · Full-series CLI — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `runner/cli.py` | New | Top-level composition root (ADR-0018): `RunOptions`, `parse_args`, `CliDeps`, `select_arrivals`, `main` and its private steps (I10). |
| `runner/summary.py` | New | `Tokens`, `Arrivals`, `RunScope`, `SeriesScope`, `RunReport`, `RunOutcome`, `build_report`, `render_report`, `report_path`. Pure apart from `write_report`. |
| `runner/post_commit.py` | Adds | `Pacer`. |
| `telemetry/trace.py` | Adds | `BUDGET_EXCEEDED_OUTCOME`, `BudgetStep`, `budget_exceeded_steps`. |
| `agents/loop.py` | Changes | `LoopOutcome.BUDGET_EXCEEDED = BUDGET_EXCEEDED_OUTCOME` (I13). |
| `config.py`, `.env.example` | Changes | Optional `anthropic_api_key` with blank → None; `runs_dir`; block comment. |
| `agents/anthropic_model.py` | Changes | `from_settings` raises on a missing key (I3). |
| `pyproject.toml` | Adds | `[project.scripts] plant-monitor = "plant_monitor.runner.cli:main"`. |
| `tests/cli_builders.py` | New | `write_cli_data`, `cli_settings`, `cli_deps`, `never_model`, `Sleeps`, `ARR13`. |
| `series.py`, pipelines, evals | Unchanged | — |

## Types and interfaces

### `Settings`
- `anthropic_api_key: SecretStr | None = None`, with a `mode="before"` `field_validator` that maps a blank string to None. Drop `min_length`.
- `runs_dir` property = `output_dir / "runs"` (I8), with no env var.
- `.env.example`: the block header becomes `# --- Anthropic (agent mode only; --thresholds-only needs no key) ---`. The empty line stays.

### `AnthropicModel.from_settings`
`from_settings(settings: Settings) -> AnthropicModel`: when `settings.anthropic_api_key is None`, it raises `ValueError("ANTHROPIC_API_KEY is not set")`. Otherwise it passes the narrowed `SecretStr`, as today. The evals already catch `ValueError`.

### `budget_exceeded_steps`
`telemetry/trace.py`:
- `BUDGET_EXCEEDED_OUTCOME: Final = "fallback:budget_exceeded"`, owned here (I13).
  - `agents/loop.py` (which already imports `telemetry.trace`) sets `BUDGET_EXCEEDED = BUDGET_EXCEEDED_OUTCOME` in `LoopOutcome`. A `Final[str]` name as an enum member value type-checks under mypy, and the member stays a `LoopOutcome`.
  - If the implementer finds that mypy rejects it, the literal duplicate stays, and E9's equality test guards it (report it in the PR).
- `class BudgetStep(BaseModel)`, frozen: `snapshot_id: str`, `agent: AgentName`.
- `budget_exceeded_steps(lines: Iterable[TraceLine]) -> tuple[BudgetStep, ...]` (R8 order: investigator first, then coordinator, per line).

### `RunReport`
`runner/summary.py`, every model frozen:
- `Mode = Literal["agent", "thresholds_only"]`, `Status = Literal["ok", "aborted", "interrupted"]`.
- `Tokens(BaseModel)`: `model_calls`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_5m_tokens`, `cache_write_1h_tokens: int = 0`; `usd: Decimal = Decimal(0)`, serialized as a float quantized to `USD_DECIMALS` (I7).
  - `Tokens.of(totals: RunTotals | AgentRunTotals) -> Tokens` (I15). Both types carry the same field names.
  - `Tokens` is the report's own JSON contract: `AgentRunTotals` is not reused, because its `runs` and Decimal serialization differ.
- `Arrivals(BaseModel)`: `processed: tuple[str, ...]`, `skipped: tuple[str, ...]`.
- `RunScope`: `arrivals: Arrivals | None`, `anomalies: int`, `tokens: Tokens`, `by_agent: dict[AgentName, Tokens]`, `budget_exceeded: tuple[BudgetStep, ...]`.
- `SeriesScope`: `tokens: Tokens`, `shift_reports: int`, `alerts: int`.
- `RunReport`: `mode`, `status`, `started_at: AwareDatetime`, `duration_seconds: float`, `aborted_at: str | None`, `cause: str | None`, `run: RunScope`, `series: SeriesScope`. The field order is the E10 key order.
- `@dataclass(frozen=True) class RunOutcome` (I10): `status: Status`, `summary: RunSummary | None`, `aborted: tuple[str, str] | None` (snapshot id, cause), `duration_seconds: float`.
- `build_report(*, mode: Mode, started_at: datetime, outcome: RunOutcome, run_lines: Sequence[TraceLine], series_lines: Sequence[TraceLine], deliverables: Sequence[Notice | ShiftReport]) -> RunReport`:
  - `status`, `aborted_at`, `cause` and `duration_seconds` come from `outcome`;
  - `anomalies = len(outcome.summary.anomalies)` (0 when None);
  - `run_totals` on each line set;
  - reports = `ShiftReport` instances, alerts = `Notice` instances.
- `render_report(report: RunReport) -> str`: the R9 lines joined by `\n`, with usd as `format(quantized, "f")`.
- `report_path(directory: Path, started: datetime) -> Path`: `directory / f"run-{started.astimezone(UTC):%Y%m%dT%H%M%SZ}.json"`, the same conversion as `trace_path` (I12).
- `write_report(report: RunReport, path: Path) -> None`: `mkdir(parents=True, exist_ok=True)`, then `write_text(model_dump_json(indent=2) + "\n", encoding="utf-8")`.

### `Pacer`
`runner/post_commit.py`:
- `class Pacer`: `__init__(self, seconds: float, sleep: Callable[[float], None])`, `after_commit(self) -> None`.
- State: `_started: bool = False`. The first call only sets it; every later call runs `sleep(seconds)` (I1).
- It implements `PostCommit`. It goes last in the chain, so the trace and outbox steps run before the pause.
- Its docstring says that it skips `run_series`' start-of-run flush (ADR-0010) and that each instance serves one run.

### `main`
`runner/cli.py`:
- `@dataclass(frozen=True) class RunOptions`: `mode: Mode` (from `summary`; I15), `until: str | None`, `speed: float`.
- `parse_args(argv: Sequence[str] | None) -> RunOptions`: a required `run` subcommand, with `--speed` typed by a private `_seconds` that rejects negative and non-finite values. `main` catches `SystemExit` only around this call and returns `int(exc.code or 0)` (I9).
- `@dataclass(frozen=True) class CliDeps`, every field defaulted:
  - `settings: Callable[[], Settings] = get_settings`;
  - `model_factory: Callable[[Settings], ModelPort] = AnthropicModel.from_settings`;
  - `sleep: Callable[[float], None] = time.sleep`;
  - `monotonic: Callable[[], float] = time.monotonic`;
  - `now: Callable[[], datetime]` (UTC now).
- `select_arrivals(arrivals: Sequence[Arrival], until: str | None, policy: HeldOutPolicy) -> list[Arrival]`: it raises `ValueError` with the R3 message.
- Private steps (I10), all module functions with no Strategy class:
  - `@dataclass(frozen=True) class Prepared`: `ctx: PlantContext`, `shifts: tuple[Shift, ...]`, `policy: HeldOutPolicy`, `arrivals: tuple[Arrival, ...]`;
  - `_prepare(opts: RunOptions, settings: Settings) -> Prepared`: plant context and policy (as `evals/agent_days_1_7.py`, with `settings.heldout_first_shift` and `heldout_open`), then the arrivals (R3). Raises only I4 errors;
  - `_wire_thresholds(registry, prepared, settings, deps, opts) -> tuple[SnapshotPipeline, PostCommit]`;
  - `_wire_agent(registry, prepared, settings, deps, opts, started) -> tuple[SnapshotPipeline, PostCommit]`: reads the criteria, calls the model factory and builds the trace writer, then delegates to `build_agent_pipeline`;
  - `_execute(arrivals, shifts, registry, pipeline, chain, deps) -> RunOutcome`: `t0 = deps.monotonic()`, then `run_series`. It catches **only** `RunAborted` (→ `aborted`, with `(exc.snapshot_id, f"{type(exc.cause).__name__}: {exc.cause}")` and `exc.summary`) and `KeyboardInterrupt` (→ `interrupted`), and always measures the duration;
  - `_report(settings: Settings, mode: Mode, started: datetime, outcome: RunOutcome) -> RunReport`: run after the registry closes. It reads this run's trace file if it exists, the series lines (`sorted(traces_dir.glob("trace-*.jsonl"))`) and `read_deliverables`, then calls `build_report`.
- `main(argv: Sequence[str] | None = None, *, deps: CliDeps | None = None) -> int`. In order:
  1. parse (I9);
  2. settings: `ValidationError` is caught **before** the generic handler and prints `settings: invalid or missing <FIELDS>` (it subclasses `ValueError`);
  3. key check in agent mode (R2);
  4. `logging.basicConfig(level=settings.log_level, stream=sys.stderr)`, without `force` (I14);
  5. `_prepare`;
  6. `started = deps.now()`; the collision check (I6);
  7. `output_dir.mkdir(parents=True, exist_ok=True)`;
  8. `with SqliteRegistry(registry_path)`: `_wire_*` by `opts.mode`, then `_execute`;
  9. `_report`, `write_report`, print `render_report` and `summary: <path>`. All of step 9 is inside `except (OSError, ValueError)` → stderr `summary unavailable: <error>` (I11);
  10. return `{"ok": 0, "aborted": 2, "interrupted": 130}[outcome.status]`.

  The one I4 handler wraps steps 3–8: `except (DataLoadError, ValueError, OSError, sqlite3.Error)` → stderr, 2. It covers the registry open, the criteria read, the model factory and `run_series`' upfront `DataLoadError`; `_execute` never swallows these. A `KeyboardInterrupt` before `run_series` is not handled.
- File names are module constants, as in the evals (`turnos.csv`, `plan_produccion.csv`, `tiempos_estandar.csv`, `embarques.csv`, `umbrales.yaml`, `llegadas.csv`).
- `if __name__ == "__main__": sys.exit(main())`.

### Test builders
`tests/cli_builders.py`: `CRIT` and `FIXTURE_PLANT` from `builders`; `STARTED` and `ALL` from `multi_agent_builders`; `write_incident_series`, `copy_incident_logbooks` and `INCIDENTS` from `incident_builders`. All of these names exist today.
- `ARR13: tuple[str, ...]`.
- `write_cli_data(root: Path, ids: Sequence[str]) -> Path`: builds the data dir of the spec's notation and returns it. Snapshots come from `write_incident_series`, logbooks from `copy_incident_logbooks`, and `llegadas.csv` lists `orden, snapshot_id, archivo, recibido` in `ids` order.
- `cli_settings(data: Path, out: Path, **overrides: object) -> Settings`: SET plus overrides. Callers isolate the env.
- `cli_deps(settings: Settings, model: ModelPort | None = None, *, sleep: Callable[[float], None] = no_sleep, now: datetime = STARTED, ticks: Sequence[float] = (0.0, 1.0)) -> CliDeps`. A None model gives `never_model`.
- `no_sleep(seconds: float) -> None`: fails the test, so every run without `--speed` proves that nothing slept (I16).
- `never_model(settings: Settings) -> ModelPort`: fails the test.
- `class Sleeps` (lands in T5 with E6 and E11): records its calls and raises `KeyboardInterrupt` at an optional call number.
- E2 alone uses `replace(CliDeps(), settings=…, model_factory=never_model)`, so the real `now`, `monotonic` and `sleep` defaults run.

## Design notes
- **Roots (ADR-0018).** `runner/cli.py` is the top-level composition root: it picks the mode and builds the registry, model, trace writer, outbox, notifier and pacer. `build_agent_pipeline` stays the agent sub-assembly (tool servers, both agents, prices), and `_wire_agent` calls it unchanged.
- **Why the CLI and not the evals.** The evals make a fresh timestamped directory per run, so they cannot resume, and the user's paid run depends on them. The CLI repeats their wiring in `settings.output_dir`. No shared helper is extracted, so the evals stay byte-identical.
- **Exception scopes (I10, I11).** Each handler catches only what its step can raise:
  - `_execute` turns the two run-time ends into a value;
  - the I4 handler covers setup;
  - the report handler cannot change the exit code.

  `RunOutcome` makes "ok but aborted" unrepresentable in `build_report`.
- **`--until` without touching `series.py`.** Truncating the selected list is enough. The first occurrence wins, because S034 arrives twice in the real file, and stopping at the second one would add a skip, not a snapshot.
- **Why `Pacer` ignores its first call (I1).** `run_series` calls `post_commit` once before any arrival (ADR-0010's start flush), and after each commit only. Ignoring the first call needs no new signal from the runner. A "last commit" rule would need the runner to know the end, so the final snapshot also gets its pause, which keeps its notices on screen before the summary.
  - Alternatives rejected: passing commit info to `PostCommit` (a port change); having the pacer query the store (coupling).
- **Two scopes (Q-66).** The run scope reads only `trace_path(traces_dir, started)`, so a resumed run shows its own cost. The series scope reads every file, so a run that aborted and resumed still reports the whole spend, aborted lines included (Q-44). Reports and alerts come from the registry, which is cumulative.
- **Collision guard (I6).** File names have one-second resolution. Without the guard, a second run in the same second would append to the first one's trace and double its run scope.
- **No price in the summary (ADR-0014).** It reads `usd` already costed into the trace lines and adds no price card. Threshold-only mode yields zero tokens because it has no trace file, not because of a special case.
- **No summary for the I4 errors.** Nothing was processed, and `output_dir` may not exist. stderr carries the message, as in the evals.
- **Optional key in `Settings`, check in the CLI.** One rule (agent mode needs a key) checked once, before data is read. `from_settings` also raises (I3) for the evals and for mypy narrowing.

## Test strategy
- **Unit:**
  - settings (E3, `tests/test_config.py`);
  - budget steps (E9, `tests/unit/telemetry/`);
  - report (E10, `tests/unit/runner/test_run_summary.py`, lines from `build_line` with a `PriceCard` from default Settings);
  - imports (E13, `tests/unit/test_import_boundaries.py`).
- **CLI integration** (`tests/integration/test_run_cli.py`, new; `isolate_settings_env`, `tmp_path`, `capsys`, `caplog`):
  - E1, E2, E4, E5, E6, E7, E8, E11, E12, E14;
  - `query` from `multi_agent_builders` for `processed_snapshots`;
  - `read_deliverables` for counts.
- Each test cites its spec id. Variants share one parametrized test (E3, E4, E5, E6c/d).

## Risks
- **A late failure in the held-out run.** Resume by directory (E7) restarts at the failed snapshot. The series scope keeps the cost of the aborted attempt.
- **Wrong cost after a resume.** The two scopes are pinned by E7 and E10.
- **Held-out leak.** Closed reads stop at the last allowed snapshot (E5d), `--until` cannot reach past it (E5b), and the logbook store shares the policy.
- **Mixed modes in one directory.** Visible as processed 0 (E12) and documented in the README. There is no guard (Q-69).
- **mypy churn from the optional key.** One `src` reader (`from_settings`) and one test (`test_reads_env_file`). Every other test passes `anthropic_api_key="k"` and is unaffected.
