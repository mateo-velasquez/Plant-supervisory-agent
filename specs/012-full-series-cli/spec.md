# 012 · Full-series CLI — Spec

- **Status:** Implemented
- **Requirements:** FR-33, FR-36, FR-37, FR-40, NFR-02, NFR-03, NFR-05, NFR-10
- **Stories:** US-11
- **Decisions:** ADR-0018 (CLI as composition root, resume by output directory, held-out via settings, run summary). Q-64–Q-71 decided (Q-71 amends Q-69). Q-10, Q-21–Q-23, Q-37, Q-43, Q-44 reused unchanged.
- **Week:** W6

## Goal
Run the whole series with one command, unattended, and report its cost and duration, so runs are reproducible and comparable, a failed run resumes where it stopped, and the Demo Day run is one line. The command prepares the single held-out run; it never runs it in this spec.

## Scope
- **In:** `runner/cli.py` (`plant-monitor run`, options, wiring of both modes); `runner/summary.py` (the run report); a `Pacer` post-commit step; `budget_exceeded_steps` in telemetry; an optional API key; `[project.scripts]`.
- **Out:** the trace viewer (013); any change to `series.py`, the pipelines, the trace schema or the eval scripts; reading real data. The full real run (= the held-out run, Q-64) is a manual task run by the user (T7), not a test.

## Decisions
- **D1 · Full real run = held-out run (Q-64).** The first `plant-monitor run` with `HELDOUT_OPEN=true` in a fresh `OUTPUT_DIR`, after the 011 T7 gate. 012 merges before it and may be Implemented with T7 pending. Running is not tuning (ADR-0006).
- **D2 · Held-out via settings only (Q-65).** No CLI flag.
- **D3 · Two cost scopes (Q-66):** run (this invocation) and series (every trace file in the directory).
- **D4 · Budget report (Q-67):** steps derived from trace outcomes. No trace schema change and no exit code change.
- **D5 · Optional key (Q-68).** Threshold-only mode needs none.
- **D6 · Resume by `OUTPUT_DIR` (Q-69, amended by Q-71).** No `--resume` flag. One mode guard: a directory that holds agent-mode traces stays in agent mode.
- **D7 · Interface choices** (taken by the spec writer; see plan):
  - **I1** `Pacer` ignores its first call (run_series' start-of-run flush). It then sleeps on every call, the last commit included. With `--speed 0` it is left out of the chain.
  - **I2** An empty `ANTHROPIC_API_KEY` is read as unset (`.env.example` ships it empty).
  - **I3** `AnthropicModel.from_settings` raises `ValueError("ANTHROPIC_API_KEY is not set")` when the key is None.
  - **I4** (amended by review) Errors before the first arrival is handled print to stderr, exit 2 and write no summary. They are:
    - settings (pydantic `ValidationError` caught first, since it subclasses `ValueError`);
    - the key;
    - data loading;
    - `--until`;
    - the name collision;
    - opening `SqliteRegistry`;
    - reading the criteria;
    - the model factory;
    - `run_series`' upfront `DataLoadError`.

    A `KeyboardInterrupt` before `run_series` is not special-cased: default exit, no report.
  - **I5** An interrupted summary has `run.arrivals = null`: `run_series` returns no `RunSummary` on `KeyboardInterrupt`.
  - **I6** A summary or trace file already named after this UTC second is an error (exit 2), so two runs never share a trace file.
  - **I7** `usd` in the JSON is a number quantized to 8 decimals, as in the trace; the text shows 8 decimals.
  - **I8** `Settings.runs_dir` = `output_dir / "runs"`, derived like `traces_dir`, with no env var.
  - **I9** (amended by review) `SystemExit` is caught only around `parse_args`, and `main` returns `int(exc.code or 0)`: `--help` gives 0, a bad option gives 2.
  - **I10** `main` is split into `_prepare`, `_wire_thresholds` / `_wire_agent` (picked by a branch, with no Strategy class), `_execute` and `_report`. `_execute` catches only `RunAborted` and `KeyboardInterrupt` and turns them into a frozen `RunOutcome` (`status`, `summary`, `aborted`, `duration_seconds`). `build_report` takes that value, so "ok but aborted" cannot be expressed. The exit code is `{"ok": 0, "aborted": 2, "interrupted": 130}[status]`.
  - **I11** Building and writing the report is wrapped in `except (OSError, ValueError)`: stderr gets `summary unavailable: <error>`, and the run's exit code is kept.
  - **I12** `report_path` converts `started` with `astimezone(UTC)`, as `trace_path` does, so both names and the I6 guard agree.
  - **I13** `BUDGET_EXCEEDED_OUTCOME` is owned by `telemetry/trace.py`. `LoopOutcome.BUDGET_EXCEEDED = BUDGET_EXCEEDED_OUTCOME` (`agents` may import `telemetry`).
  - **I14** Logging uses `logging.basicConfig(level=…, stream=sys.stderr)` without `force`. Repeated `main` calls are no-ops, and pytest's `caplog` keeps working.
  - **I15** `RunOptions.mode: Mode` (no `thresholds_only` bool). `Tokens.of(RunTotals | AgentRunTotals)` is the report's own JSON contract.
  - **I16** The tests run the default `CliDeps` seams. In the builder, the default `sleep` fails the test when called.

## Behavior

### R1 · Command (FR-36, NFR-05, Q-70)
`plant-monitor run [--thresholds-only] [--until SNAPSHOT_ID] [--speed SECONDS]`, using stdlib `argparse`. `[project.scripts] plant-monitor = "plant_monitor.runner.cli:main"`. The default is agent mode. `--speed` is a finite float ≥ 0 (default 0). Anything else is an argparse error: `main` returns 2, and nothing is read or created. `--help` returns 0 (I9). `main(argv, *, deps)` takes injectable seams: settings, model factory, sleep, monotonic clock and UTC now. `cli.py` is the only product module that builds concrete adapters (ADR-0018).

### R2 · Settings, key and logging (Q-68, I2, I3)
- `anthropic_api_key: SecretStr | None = None`. An empty or blank value is None.
- An invalid `Settings` prints `settings: invalid or missing <FIELDS>` to stderr and returns 2.
- Agent mode with no key prints a message naming `ANTHROPIC_API_KEY` to stderr and returns 2 before any data file is read: the model factory is not called and `output_dir` is not created.
- Threshold-only mode never reads the key.
- Logging goes to stderr at `LOG_LEVEL` (I14).

### R3 · Arrival selection (FR-40, Q-65, Q-37, Q-21)
- `policy = HeldOutPolicy.from_calendar(shifts, heldout_first_shift, heldout_open)`. Closed → `load_arrivals_until(llegadas, policy)` (S001–S042 in the real calendar). Open → `load_arrivals(llegadas)`.
- The same policy goes to the logbook store (agent mode).
- `--until X` keeps the arrivals up to and including the **first** arrival whose id is X. Later arrivals, a repeat of X included, are dropped before `run_series`.
- An X not among the selected arrivals (unknown, or held out while closed) returns 2 before anything is processed. The message names X and, when X is held out and the guard is closed, says so. `output_dir` is not created.

### R4 · Composition per mode (FR-33, ADR-0002, ADR-0010, ADR-0014)
- Both modes use the registry at `settings.registry_path`, and the outbox with `FileNotifier(settings.notices_dir)` and `deps.now`.
- **Threshold-only:** `ThresholdPipeline.from_registry(registry, ctx)`. Post-commit chain [outbox, pacer]. No trace writer, no model, no criteria read.
- **Agent:** `model = deps.model_factory(settings)`, `TraceWriter(trace_path(settings.traces_dir, started))`, criteria from `settings.criteria_path` (`utf-8-sig`), `build_agent_pipeline(settings, registry, ctx, policy, model, trace, criteria)`. Post-commit chain [trace, outbox, pacer]. This is the wiring of `evals/agent_days_1_7.py`, in `settings.output_dir`.
- `started` is `deps.now()`, read once after the R2/R3 checks. It names the trace file and the summary file. If either already exists, `main` returns 2 before processing (I6).

### R5 · Resume by output directory (NFR-10, Q-69, Q-10, Q-23, ADR-0008)
A rerun with the same `OUTPUT_DIR` opens the same registry. `run_series` skips every arrival already committed with the same hash, and retries the one that failed. A fresh run needs a new `OUTPUT_DIR`. Pending notices are delivered by the start-of-run flush (Q-23).
- **Agent directory stays agent (Q-71, §3, §5).** `--thresholds-only` in a directory whose `traces_dir` holds any `trace-*.jsonl` (written only in agent mode, whatever its content) returns 2 before anything is processed (an I4 error: stderr says the directory holds agent-mode traces and to resume in agent mode or use a new `OUTPUT_DIR`; no report). Reason: the threshold pipeline has no cause ledger, so an agent raise in force would be dropped (§3 resolution, §5 new cases), and nobody would read the logbook that lifts it.
- The other order is allowed (Q-69): an agent run in a directory where threshold-only already processed every arrival shows processed 0 and skipped N.

### R6 · Pacing (ADR-0018, I1)
With `--speed s` > 0, the chain ends with `Pacer(s, deps.sleep)`. `run_series` calls the chain once at the start of the run and once after each committed arrival, never after a skipped one. `Pacer` ignores the first call and calls `sleep(s)` on every later one. So there is one sleep per committed snapshot, after its trace line and notices, and none for skipped arrivals. With `s = 0` no `Pacer` is built and `sleep` is never called.

### R7 · Run report (FR-37, NFR-03, Q-66, ADR-0014)
`RunReport` (frozen pydantic) only sums values telemetry and the runner already computed. It never sees prices.
- `mode` (`agent` | `thresholds_only`) and `status` (`ok` | `aborted` | `interrupted`).
- `started_at` (UTC) and `duration_seconds`: wall clock around `run_series` with `deps.monotonic`.
- `aborted_at` and `cause` (`<ErrorClass>: <message>`) only when aborted, else null.
- **`run`:**
  - `arrivals {processed, skipped}`: ids in order, from the `RunSummary` (or from `RunAborted.summary`); null when interrupted (I5);
  - `anomalies` (count);
  - `tokens`: `model_calls`, input, output, cache read, cache write 5m and 1h, `usd`, from `run_totals` over this run's trace file only (empty when absent, always empty in threshold-only mode);
  - `by_agent`: the same fields for `investigator` and `coordinator`, both always listed;
  - `budget_exceeded` (R8).
- **`series`:** `tokens`, `run_totals` over every `trace-*.jsonl` under `traces_dir` (aborted lines of earlier runs included), plus `shift_reports` and `alerts` counted from `read_deliverables(registry_path)` after the registry closes (`ShiftReport` rows vs `Notice` rows).

### R8 · Prompt-budget report (NFR-02, Q-67, Q-43)
- `budget_exceeded_steps(lines)` lists, in line order, one step per hit of the prompt-budget guard:
  - `(snapshot_id, "investigator")` when `line.investigator.outcome` is `fallback:budget_exceeded`;
  - then `(snapshot_id, "coordinator")` when `line.outcome` is.
- The request was not sent, the texts fell back, the run continued, and the exit code does not change.
- Turn and token count stay in the loop's existing WARNING.
- The constant `BUDGET_EXCEEDED_OUTCOME` is owned by telemetry, and the loop's enum member takes its value from it (I13).

### R9 · Output (FR-37, I7)
- The report is written as JSON (`model_dump_json(indent=2)`) to `settings.runs_dir / "run-<started %Y%m%dT%H%M%SZ>.json"`.
- `render_report` prints it to stdout as fixed lines, followed by `summary: <path>`. Lines:
  - `run: <mode> <status>, <duration .1f> s, started <iso Z>`;
  - `aborted at <id>: <cause>` (when aborted);
  - `arrivals: <p> processed, <s> skipped, <a> anomalies` (or `arrivals: unknown (interrupted), <a> anomalies`);
  - `run tokens: <c> calls, input <i>, output <o>, cache read <r>, cache write <w5> (5m) <w1> (1h), usd <usd 8 dp>`;
  - `series tokens: …`, in the same format;
  - `series deliverables: shift reports <n>, alerts <m>`;
  - `budget exceeded: <id> <agent>, …` or `budget exceeded: none`.
- A report is written for `ok`, `aborted` and `interrupted`, never in the I4 cases.
- A report that cannot be built or written (`OSError`, `ValueError`, e.g. an unreadable trace file) prints `summary unavailable: …` to stderr and keeps the run's exit code (I11).

### R10 · Exit codes (Q-22, Q-23, NFR-10)
- 0: the run finished.
- 2: a settings or data error (I4), or `RunAborted`. On `RunAborted`, stderr gets `run aborted at <id>: <cause>`, and the partial report is printed and written with status `aborted`.
- 130: `KeyboardInterrupt`. The report is written with status `interrupted`. The snapshot in progress records nothing (Q-23).
- Delivery failures never change the code (ADR-0010).

### R11 · Imports and unchanged invariants
- `runner/summary.py` imports only `domain`, `runner` and `telemetry`.
- `runner/cli.py` imports only `agents`, `cases`, `config`, `domain`, `ingestion`, `metrics`, `notify`, `runner` and `telemetry`. It may import `AnthropicModel`, never `anthropic` or `mcp`.
- Unchanged: `series.py`, the single writer, the floor, logbooks as data, `evals/agent_days_1_7.py` and `evals/smoke_days_1_7.py`.

### R12 · Full real run (Q-64, FR-40, FR-36, FR-37)
After merge and after the 011 T7 gate, the user runs `plant-monitor run` once with `HELDOUT_OPEN=true` in a fresh `OUTPUT_DIR` over the 61 arrivals. Failures are logged before any change. Cost and duration go in the README and the roadmap. Claude never runs it.

## Worked examples

**Notation.** IF, `ALL` (S001–S012), `HEAD`, `S002`, `S004`, `S005`, `S006`, `S010_JUDGE`, `S010_EMIT`, `TAIL`, `turn`, `logbook`, `USAGE` (3,000 in / 200 out), `STARTED` (2026-03-02T23:00Z) and `SECOND_START` (23:30Z), all from `multi_agent_builders`.
- **D** = `write_cli_data(tmp, ids)`: IF `planta` plus the plant fixture's standards, shipments and `umbrales.yaml`, `reglas/criterio.md` = `CRIT`, the IF logbooks, and the snapshots plus `llegadas.csv` in the order of `ids`. A repeated id points to the same file (identical bytes).
- **ARR13** = `(S001, S002, S003, S004, S004, S005, …, S012)`: the repeat sits at `orden` 5.
- **SET** = `Settings(anthropic_api_key="k", data_dir=D, output_dir=O, heldout_open=True, heldout_first_shift="T06")`.
- **NEVER** = a model factory that fails the test if called.
- Prices: Settings defaults (input 0.10, cache write 5m 0.125, 1h 0.20, cache read 0.01, output 0.50 USD/MTok).
- US-11 mapping: "61 arrivals" ↦ ARR13 (13 arrivals, 12 snapshots); "30 shift reports" ↦ 6 (T01–T06); "failed at S030" ↦ S004. The skeleton's "third snapshot" becomes S004, the third IF snapshot that calls a model, because S003 makes no model call (`no_text_needed`).

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **Full series, agent mode (R1, R4, R7, R9; US-11 scenarios 1 and 2; FR-36).** SET, D over ARR13, `main(["run"])`, model `FakeModel([*HEAD, *S010_JUDGE, *S010_EMIT, *TAIL])`, now STARTED, monotonic `[10.0, 52.5]` | 0. 22 requests. Processed S001…S012 in order; skipped `[S004]`. `traces/trace-20260302T230000Z.jsonl` has 12 lines. `read_deliverables`: 6 reports T01…T06 in order, 4 alerts. `runs/run-20260302T230000Z.json`: `mode` agent, `status` ok, `duration_seconds` 42.5. Run tokens: `model_calls` 22, input 66000, output 4400, cache 0/0/0, `usd` 0.0088. `by_agent`: investigator 12 calls, `usd` 0.0048; coordinator 10 calls, `usd` 0.004. `budget_exceeded` []. Series tokens = run tokens; `shift_reports` 6, `alerts` 4. The last stdout line is `summary: <that path>`. |
| E2 | **Threshold-only (R2, R4, I16).** SET with `anthropic_api_key=None`, ARR13, `["run", "--thresholds-only"]`, deps `replace(CliDeps(), settings=<that SET>, model_factory=never_model)`, so the real `now`, `monotonic` and `sleep` run | 0. NEVER is not called; file names are not asserted. Processed 12; skipped `[S004]`. No `traces` directory. Run tokens: every field 0, `model_calls` 0; `by_agent` lists both agents at 0. Series tokens 0; `shift_reports` 6. |
| E3 | **Optional key (R2, Q-68, I2, I3).** Isolated env: (a) `Settings()`; (b) `ANTHROPIC_API_KEY=""`; (c) `ANTHROPIC_API_KEY=sk-x`; (d) `AnthropicModel.from_settings(Settings())` | (a) `anthropic_api_key is None`: this is the changed expectation of `test_fails_without_api_key`. (b) None. (c) `get_secret_value() == "sk-x"`. (d) `ValueError` whose message holds `ANTHROPIC_API_KEY`. |
| E4 | **Risk: setup errors (R2, I4).** `["run"]`, NEVER: (a) SET with `anthropic_api_key=None`; (b) a settings callable that raises `ValidationError` | (a) 2; stderr holds `ANTHROPIC_API_KEY`. (b) 2; stderr starts `settings: invalid or missing`. In both, NEVER is not called and O does not exist. |
| E5 | **Selection (R3, I6).** Threshold-only, NEVER: (a) ARR13, `--until S004`; (b) ARR13, `heldout_open=False` (first shift T06), `--until S011`; (c) ARR13, `--until S099`; (d) as (b) with no `--until`; (e) as (a), with `O/runs/run-20260302T230000Z.json` already present | (a) 0; processed S001–S004; skipped `[]`: the repeat at `orden` 5 is not read. (b) 2; stderr names S011 and says it is held out; O does not exist. (c) 2; stderr names S099; O does not exist. (d) 0; processed S001–S010; skipped `[S004]`; no held-out row is read (Q-37). (e) 2; nothing processed (no `registry.sqlite3`); the existing file is unchanged. |
| E6 | **Pacing (R1, R6, I1, I9).** Threshold-only, ARR13: (a) `--until S005 --speed 2.5` with recording `Sleeps`; (b) dropped: the builder's default `sleep` fails any test without `--speed` (I16); (c) `--speed -1`, `--speed nan`; (d) `--help` | (a) 0; processed S001–S005, skipped `[S004]`; sleep calls `[2.5] × 5`: none at run start, none for the repeat. (c) Each returns 2; O does not exist. (d) 0. |
| E7 | **Resume after a failure (R5, R7, R10; US-11 scenario 4; NFR-10).** SET, D over S001–S006. Run 1: now STARTED, script `[*S002, S004[0], ModelCallFailed("create", 529)]`. Run 2, same O: now SECOND_START, script `[*S004, *S005, *S006]` | Run 1: 2; stderr `run aborted at S004: …`. `run-20260302T230000Z.json`: `status` aborted, `aborted_at` S004, `cause` `ModelCallFailed: model call 'create' failed (status 529)`, processed `[S001, S002, S003]`, skipped `[]`. Run tokens: `model_calls` 3, input 9000, output 600, `usd` 0.0012 (the aborted line's call counts). Series is the same. Run 2: 0; 8 requests, none for S001–S003; processed `[S004, S005, S006]`, skipped `[S001, S002, S003]`. Run tokens: 8 calls, input 24000, output 1600, `usd` 0.0032 (its own trace file only). Series: 11 calls, input 33000, output 2200, `usd` 0.0044; `shift_reports` 3, `alerts` 1. |
| E8 | **Prompt budget (R8; US-11 scenario 3; NFR-02).** SET, D over S001–S002, `FakeModel([], count=96_000)` (limit 95000), `["run"]` | 0, `status` ok. `requests == []`, 1 counted request. Processed `[S001, S002]`. `budget_exceeded` = `[{"snapshot_id": "S002", "agent": "investigator"}]`. Run tokens 0. `shift_reports` 1. stdout has `budget exceeded: S002 investigator`. The loop's WARNING `snapshot S002 turn 1: prompt of 96000 tokens is over the limit of 95000; request not sent` is logged. |
| E9 | **Budget steps (R8).** `build_line` lines: S003 outcome `done`; S004 with investigator outcome `fallback:budget_exceeded` and outcome `fallback:budget_exceeded`; S005 outcome `aborted:ModelCallFailed` | `budget_exceeded_steps` → `(S004, investigator), (S004, coordinator)`. `()` for no lines. `BUDGET_EXCEEDED_OUTCOME == LoopOutcome.BUDGET_EXCEEDED.value`. |
| E10 | **Report shape (R7, R9, I10).** `build_report(mode="agent", started_at=SECOND_START, outcome=RunOutcome("ok", <summary below>, None, 12.5), …)`. Run lines (default card): S003 coordinator call `Usage(1000, 200, cache_write_5m=2000)` (usd 0.00045); S004 investigator call `Usage(500, 100, cache_read=2000)` (usd 0.00012), with outcome `fallback:budget_exceeded` and no coordinator call. Series lines: those two plus an earlier file's aborted S003 with coordinator `Usage(300, 50)` (usd 0.000055). `RunSummary(("S003", "S004"), ("S001", "S002"))`. Deliverables: reports T01, T02 and one alert | `model_dump(mode="json")` == `{"mode": "agent", "status": "ok", "started_at": "2026-03-02T23:30:00Z", "duration_seconds": 12.5, "aborted_at": null, "cause": null, "run": {"arrivals": {"processed": ["S003", "S004"], "skipped": ["S001", "S002"]}, "anomalies": 0, "tokens": {"model_calls": 2, "input_tokens": 1500, "output_tokens": 300, "cache_read_tokens": 2000, "cache_write_5m_tokens": 2000, "cache_write_1h_tokens": 0, "usd": 0.00057}, "by_agent": {"investigator": {"model_calls": 1, "input_tokens": 500, "output_tokens": 100, "cache_read_tokens": 2000, "cache_write_5m_tokens": 0, "cache_write_1h_tokens": 0, "usd": 0.00012}, "coordinator": {"model_calls": 1, "input_tokens": 1000, "output_tokens": 200, "cache_read_tokens": 0, "cache_write_5m_tokens": 2000, "cache_write_1h_tokens": 0, "usd": 0.00045}}, "budget_exceeded": [{"snapshot_id": "S004", "agent": "coordinator"}]}, "series": {"tokens": {"model_calls": 3, "input_tokens": 1800, "output_tokens": 350, "cache_read_tokens": 2000, "cache_write_5m_tokens": 2000, "cache_write_1h_tokens": 0, "usd": 0.000625}, "shift_reports": 2, "alerts": 1}}`. `render_report` lines: `run: agent ok, 12.5 s, started 2026-03-02T23:30:00Z`; `arrivals: 2 processed, 2 skipped, 0 anomalies`; `run tokens: 2 calls, input 1500, output 300, cache read 2000, cache write 2000 (5m) 0 (1h), usd 0.00057000`; `series tokens: 3 calls, input 1800, output 350, cache read 2000, cache write 2000 (5m) 0 (1h), usd 0.00062500`; `series deliverables: shift reports 2, alerts 1`; `budget exceeded: S004 coordinator`. |
| E11 | **Risk: Ctrl-C (R10, I5).** Threshold-only, ARR13, `--speed 1`, a `sleep` that raises `KeyboardInterrupt` on its 2nd call | 130. The report has `status` interrupted, `run.arrivals` null, and is written under `runs/`. `processed_snapshots` holds S001 and S002 only. |
| E12 | **Risk: mixed modes in one directory (R5).** E2's run, then `["run"]` on the same O with `FakeModel([])`, now SECOND_START | 0. 0 requests. Processed `[]`; skipped all 13 arrivals' ids. Run tokens 0. `trace-20260302T233000Z.jsonl` is not created. |
| E13 | **Risk: imports (R11).** `runner/summary.py`, `runner/cli.py` | Each imports only its R11 layers; neither imports `anthropic` or `mcp`. |
| E14 | **Risk: the summary never loses the run (R9, I11).** O with `traces/trace-20260301T000000Z.jsonl` holding the line `{broken`, then agent mode `["run"]` over D (S001–S002) with `FakeModel([*S002])` (agent mode since Q-71: threshold-only would be refused by the trace file) | 0. Processed `[S001, S002]`. stderr has `summary unavailable: …`. No traceback reaches the caller. |
| E15 | **Risk: an agent directory stays agent (R5, Q-71).** SET, D over S001–S004. Run 1: agent, `["run", "--until", "S002"]`, `FakeModel([*S002])`, now STARTED. Run 2, same O: `["run", "--thresholds-only"]`, NEVER, now SECOND_START | Run 1: 0. Run 2: 2; stderr says the directory holds agent-mode traces and names agent mode; `processed_snapshots` still `[S001, S002]`; no `runs/run-20260302T233000Z.json`. |

## Edge cases and assumptions
- **X1** · A `KeyboardInterrupt` inside a snapshot leaves no aborted trace line (`AgentPipeline` catches `Exception` only). So the run and series tokens miss at most that snapshot's calls. Fixing this would change the pipeline, which is out of scope.
- **X2** · Closed mode inherits Q-37's limitation: a repeat of an allowed snapshot that arrives after S042 completes is not read. This does not happen in days 1–7.
- **X3** · Pending notices from an earlier run are delivered by the start-of-run flush, before any pacing sleep (I1).
- **X4** · A run whose arrivals are all skipped writes no trace file. Its run scope is empty, and its series scope still sums the earlier files (E12).
- **X5** · The eval scripts keep their own wiring and directories. Q-68 only removes their "missing key" settings error.

## Acceptance
- [x] E1–E15 pass with `FakeModel` on synthetic fixtures; CI makes no network call (NFR-07). Every new test cites its spec id (`Risk:` tests too).
- [x] Specs 001–011 tests pass. Only these change, and no test is deleted:
  - `tests/test_config.py::test_fails_without_api_key`: re-expected as E3a (`anthropic_api_key is None`) and renamed `test_e3a_api_key_is_optional`;
  - setup only: `test_reads_env_file` asserts the key is not None before `get_secret_value()` (mypy narrowing);
  - `test_e19_agent_defaults_and_traces_dir` (spec 007) also asserts `runs_dir` (I8).
- [x] `.env.example`: the key's block comment says it is needed in agent mode only.
- [x] Docs in this PR (T8): README "How to run", `docs/STRUCTURE.md`, roadmap rows 012 and held-out run reordered (Q-64). `docs/requirements.md` Q-64–Q-70 are done with this spec.
- [ ] Manual, after merge and the 011 T7 gate: the full real run = the held-out run, run by the user (T7, R12).
- [x] `ruff`, `mypy --strict`, `pytest --cov` pass.

## Size
About 23 KB, over budget. E10 spells out the full JSON shape, because the user asked for exact numbers. Splitting the summary from the CLI would leave the command untestable end to end.
