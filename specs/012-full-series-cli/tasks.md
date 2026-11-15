# 012 · Full-series CLI — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts (the pre-commit mypy hook stashes unstaged tracked changes but leaves untracked files, 008 note).

- A commit's tests use only symbols from that commit or earlier, so **each commit passes `mypy --strict` over `src tests evals` on its own**. Every "Tests X → code" task below is one commit.
- Types land before their users: `Settings` (T10) and `budget_exceeded_steps` (T11) come before `RunReport` (T3), and that comes before the CLI (T2, T5, T1, T6, T4).
- `tests/cli_builders.py` lands with the first CLI task (T2). It imports only symbols that exist by then.
- Each task also runs `uv run pytest` and ruff before committing. Every test cites its spec id (`Risk:` tests too). Helpers come `from builders import ...` (or the other `*_builders`), never `from tests.builders`.
- Owner: tests by `test-writer`, code by `domain-implementer`, unless stated.

Ids T1–T8 come from the Draft skeleton and keep their topic. T0, T10 and T11 are new.

- [x] T0 · **Main session and spec writer, before Ready:** ADR-0018 written; `docs/requirements.md` gains Q-64–Q-70 — refs: D1–D6 · plan: Design notes
- [x] T10 · Tests E3 → `config.py`:
  - `anthropic_api_key: SecretStr | None = None` with the blank → None validator;
  - the `runs_dir` property.

  Also `agents/anthropic_model.py`: `from_settings` raises `ValueError("ANTHROPIC_API_KEY is not set")`. `.env.example`: the block header (agent mode only). Same commit:
  - `test_fails_without_api_key` re-expected as E3a and renamed `test_e3a_api_key_is_optional` (not deleted);
  - `test_reads_env_file` asserts the key is not None before `get_secret_value()`;
  - the evals still type-check unchanged.

  — refs: R2, E3, I2, I3, I8 · plan: `Settings`, `AnthropicModel.from_settings`
- [x] T11 · Tests E9 → `telemetry/trace.py`: `BUDGET_EXCEEDED_OUTCOME` (owned here), `BudgetStep`, `budget_exceeded_steps`; `agents/loop.py`: `LoopOutcome.BUDGET_EXCEEDED = BUDGET_EXCEEDED_OUTCOME` (if mypy rejects it, keep the literal and report it). E9 imports `LoopOutcome` in the test only; telemetry keeps importing only `domain` — refs: R8, E9, I13 · plan: `budget_exceeded_steps`
- [x] T3 · Tests E10 and the `summary.py` half of E13 → `runner/summary.py`: `Mode`, `Status`, `Tokens` (`Tokens.of`), `Arrivals`, `RunScope`, `SeriesScope`, `RunReport`, `RunOutcome`, `build_report`, `render_report`, `report_path` (UTC conversion as `trace_path`), `write_report` — refs: R7, R9, R11, E10, E13, I5, I7, I10, I12, I15 · plan: `RunReport`
- [x] T2 · Tests E2, E4b, E5, E14 and the `cli.py` half of E13 (`tests/integration/test_run_cli.py`, new; `tests/cli_builders.py`, new, without `Sleeps`) → `runner/cli.py`:
  - `RunOptions` (`mode: Mode`), `parse_args` (`SystemExit` caught only around it), `CliDeps`, `select_arrivals`;
  - `main` split into `_prepare`, `_wire_thresholds`, `_execute`, `_report`: the settings check (`ValidationError` first), key and data checks, logging without `force`, the collision guard, threshold-only wiring, the I4 handler, and the report step that never changes the exit code;
  - `pyproject.toml` `[project.scripts]`.

  The agent branch (`_wire_agent`) may raise `NotImplementedError` until T1. E5d uses `heldout_open=False` with first shift T06.

  — refs: R1, R2, R3, R4, R7, R9, R10, R11, E2, E4b, E5, E13, E14, I4, I6, I9, I10, I11, I14, I15, I16, X2 · plan: `main`, Test builders
- [x] T5 · Tests E6 (a, c, d), E11 → `Pacer` in `runner/post_commit.py` (ignores its first call; docstring per plan), wired last in the chain when `--speed` > 0; `Sleeps` lands in `tests/cli_builders.py`; `KeyboardInterrupt` → `interrupted` report, 130 — refs: R6, R10, E6, E11, I1, I5, X3 · plan: `Pacer`, `main`
- [x] T1 · Tests E1, E4a, E12 → the agent branch of `main` (`_wire_agent`): the model factory, `TraceWriter(trace_path(traces_dir, started))`, criteria `utf-8-sig`, `build_agent_pipeline`, chain [trace, outbox, pacer], and run and series trace lines in the report — refs: R2, R4, R5, R7, R9, E1, E4, E12, X4 · plan: `main`
- [x] T6 · Test E8 (US-11 scenario 3) → fixes in `src/` only if it fails. `caplog` filtered by `plant_monitor.agents.loop` — refs: R8, E8 · plan: `budget_exceeded_steps`
- [x] T4 · Test E7 (US-11 scenario 4) → fixes in `src/` only if it fails. Two `main` calls on one `output_dir` with `STARTED` and `SECOND_START` — refs: R5, R7, R10, E7, X1 · plan: Design notes
- [x] T12 · Test E15 and E14 re-expected (agent mode) → `runner/cli.py`: `--thresholds-only` returns 2 when `traces_dir` holds any `trace-*.jsonl` (Q-71), before processing, as an I4 error. Docs in the same change: Q-71 row (Q-69 amended), ADR-0018 line, README warning — refs: R5, E14, E15, Q-71 · plan: `main`
- [x] T8 · **Main session, docs:**
  - README "How to run":
    - `uv run plant-monitor run [--thresholds-only] [--until S0xx] [--speed s]`;
    - `OUTPUT_DIR` holds one run, and rerunning resumes; a fresh run needs a new directory;
    - mixed modes in one directory skip everything;
    - held-out data only through `HELDOUT_OPEN`;
    - the summary under `OUTPUT_DIR/runs/`;
    - exit codes 0, 2 and 130;
  - `docs/STRUCTURE.md`:
    - rows for `runner/cli.py` and `runner/summary.py`;
    - updated rows for `runner/post_commit.py` (`Pacer`), `telemetry/trace.py` (`budget_exceeded_steps`) and `config.py` (optional key, `runs_dir`);
    - the dependency rule gains the R11 lines;
  - roadmap:
    - row 012 moves above the *(process)* held-out run row: scope as built, Q-64–Q-70, ADR-0018, status Implemented with T7 pending;
    - the held-out row says it is the first `plant-monitor run` with `HELDOUT_OPEN=true` in a fresh `OUTPUT_DIR`, after 011 T7;
  - spec status Implemented;
  - `/check`.

  — refs: Acceptance, R12 · plan: Modules
- [ ] T7 · **User, manual, after merge and after the 011 T7 gate (not a test; Claude never runs it):**
  - the full real run is the held-out run (Q-64): `HELDOUT_OPEN=true`, a fresh `OUTPUT_DIR`, `uv run plant-monitor run` over the 61 arrivals, once, as-is;
  - failures are logged before any change; a failure resumes with the same `OUTPUT_DIR`;
  - the summary's series cost (tokens, cache, USD), the duration and the reports and alerts go in the README and the roadmap.

  — refs: R12, Q-64, FR-36, FR-37, FR-40
