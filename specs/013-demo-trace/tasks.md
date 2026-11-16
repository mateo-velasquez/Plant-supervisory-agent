# 013 · Alert trace for the demo — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts.

- **mypy per commit.** A commit's tests use only symbols from that commit or earlier, so each commit passes `mypy --strict` over `src tests evals` on its own.
  - The pre-commit mypy hook stashes unstaged tracked changes but leaves untracked files. So write each task's new files only in that task.
  - If test files for later tasks already exist untracked, the first Python commit must also carry everything they import.
- **Type order.** Types land before their users: the telemetry additions (T12) and the reader with `StoredNotice` (T7) come before the query (T1), the query before the renderer (T8), and the renderer before the CLI (T3, T2, T9). `write_safe` lands with the CLI (T3).
- **Before each commit:** `uv run pytest` and ruff.
- **Test conventions.** Every test cites its spec id (`Risk:` tests too). Helpers come `from builders import ...`, `from cli_builders import ...`, `from trace_builders import ...`, never `from tests....`.
- **New test basenames** (unique across `tests/`, checked): `test_notice_reader.py`, `test_trace_query.py`, `test_trace_render.py`, `test_trace_cli.py`.
- **Owner:** tests by `test-writer`, code by `domain-implementer`, unless stated.

Ids T1–T6 come from the Draft skeleton and keep their topic: T1 query, T2 threshold-only, T3 subcommand, T4 demo alert, T5 demo script, T6 rehearsal. T0 and T7–T12 are new.

- [x] T0 · **Main session, before Ready:** ADR-0019 "Read-only notice trace: registry read `mode=ro` plus JSON lines, no schema change". It closes ADR-0014's "revisit in spec 013". `docs/requirements.md` Q-72–Q-83 are already written by the spec writer — refs: D1–D5, Q-72–Q-83 · plan: Design notes
- [x] T12 · Test E14 (in `tests/unit/telemetry/test_trace.py`) → `telemetry/trace.py`: `TraceMode`, `TraceFile`, `read_trace_files`. Same commit, refactors with no test-expectation change:
  - `runner/summary.py`: `Mode = TraceMode`;
  - `runner/cli.py` `_report`: series lines from `read_trace_files`;
  - the 012 tests stay green unchanged.

  — refs: R7, E14, I9, I10 · plan: `TraceFile`, `read_trace_files`, `TraceMode`
- [x] T7 · Tests E11 (`tests/unit/cases/test_notice_reader.py`, new) and E12 (`tests/unit/test_import_boundaries.py`) → `domain/stored.py` (`StoredNotice`) and `cases/registry/notice_reader.py`:
  - `read_notice` → `StoredNotice | ShiftReport | None`;
  - `mode=ro`, one read transaction, per-table column check from `_NEEDS`, no version check;
  - the I6 refactor in `cases_repo.py` and `causes_repo.py`: tuples joined at the SQL sites, `cited_from_row` extracted from `SqliteCauseRepository.cited`, callers updated, no behavior change;
  - `tests/incident_runs.py`: `incident_run(..., path=":memory:")`.

  — refs: R2, R3, R14, E11, E12, I6, I7 · plan: `StoredNotice`, `read_notice`
- [x] T1 · Tests E9, X1, X2, X3, X10 (`tests/unit/telemetry/test_trace_query.py`, new; hand-built inputs in `tests/trace_builders.py`, new, without the CLI helpers) → `telemetry/trace_query.py`:
  - the frozen view dataclasses (`Opening` with its `__post_init__` check), `CorruptTraces` (message without prefix);
  - `build_notice_trace(stored, traces)`, `shown_snapshots`, `shown_shifts` (the R11 sets);
  - the R6 raise match (parse into `ValidatedProposal`, successful applies only, typed fields, ordinal cross-check, ambiguity → no match), R7 selection, R8 marking.

  — refs: R4, R5, R6, R7, R8, R9, R10, R11, E9, X1, X2, X3, X8, X9, X10, I8 · plan: `build_notice_trace`
- [x] T8 · Tests E10 and X4 (`tests/unit/telemetry/test_trace_render.py`, new) → `telemetry/trace_render.py`: `escape_controls`, `render_notice_trace` with the exact R12 layout, `_number` (I4), `_usd`, `_json`, `_tokens` — refs: R12, E10, X4, X5, X6, I3, I4 · plan: `render_notice_trace`
- [x] T3 · Tests E1 (byte-exact; its R11 drift guard may be added in T2), E3, E4, E8 (`tests/integration/test_trace_cli.py`, new). `trace_builders` gains `S010_EMIT_HOOKED`, `PRICES`, the module-scoped `agent_dir` / `thresholds_dir` fixtures, `copied` and `traced`. Code:
  - `notify/console.py`: `write_safe` extracted, `ConsoleNotifier._write` calls it (existing notifier tests unchanged);
  - `runner/cli.py`: `TraceOptions`, subcommand-aware `parse_args`, the `main` dispatch;
  - `_trace` steps 1–3, 5–7 and 9 (the step 4 and 8 held-out checks may be no-ops until T2), with `CorruptTraces` → `ValueError(f"traces: {exc}")`;
  - `_read_traces`.

  — refs: R1, R2, R3, R6, R7, R8, R9, R10, R12, R13, E1, E3, E4, E8, I1, I5 · plan: `write_safe`, `main` (trace branch), Test builders
- [x] T2 · Tests E2, E7 and E1's R11 drift guard → the R11 held-out checks in `_trace` (before reading traces, and over `shown_snapshots` / `shown_shifts`); threshold-only rendering if E2 fails — refs: R9, R11, R13, E1, E2, E7, X5 · plan: `main` (trace branch)
- [x] T9 · Tests E5, E6, E13 → fixes in `src/` only if they fail: resumed run with aborted attempts, agent-mode "no agent was involved", unreadable and duplicate trace lines → exit 2 — refs: R7, R9, R13, E5, E6, E13 · plan: `main` (trace branch), Design notes
- [x] T5 · **Main session, draft:** `docs/demo.md` with:
  - the steps and their timings (series live with `--speed`, then one trace);
  - the commands `uv run plant-monitor run --speed <s>` and `uv run plant-monitor trace <notice_id>`;
  - both candidate alerts (the Europe audit EUR-0305, T07 → T10, which opens escalated under the T07 raise; the Pickup stop raised by the agent, T17 → T19);
  - the dry run on synthetic fixtures (`uv run pytest tests/integration/test_trace_cli.py --basetemp z_helps/dry-run`, then `plant-monitor trace` against the kept `OUTPUT_DIR`);
  - the fallback plan (a recorded copy of the held-out `OUTPUT_DIR`), marked "to finish after the held-out run".

  — refs: R15, Q-83
- [x] T10 · **Main session, docs:**
  - README "How to trace a notice": the command, the exit codes 0/1/2, the held-out note, and read-only;
  - `docs/STRUCTURE.md`:
    - rows for `domain/stored.py`, `cases/registry/notice_reader.py`, `telemetry/trace_query.py`, `telemetry/trace_render.py`;
    - updated rows for `telemetry/trace.py` (`TraceMode`, `TraceFile`, `read_trace_files`), `notify/console.py` (`write_safe`), `runner/cli.py`, `runner/summary.py` and `cases/registry/` (public row parsers);
    - the plan's dependency-rule lines;
  - roadmap row 013: scope as built, Q-72–Q-83, ADR-0019, status Implemented with T4, T11 and T6 pending;
  - spec status Implemented;
  - `/check`.

  — refs: Acceptance · plan: Modules, Design notes
- [ ] T4 · **User and main session, manual, after the held-out run, needs the user's permission (`CLAUDE_ALLOW_HELDOUT=1`):** choose the demo alert from the real run (one of the two candidates). Run `plant-monitor trace` on it and check every line by hand against `criterio.md` (metrics §1–§2, transition §3, raise §5, cause and citation §6). Log any mismatch before changing anything — refs: R15, Q-83, FR-38, FR-40
- [ ] T11 · **Main session, manual, after T4, needs permission:** finish `docs/demo.md` with the chosen alert, its real `notice_id` and timings. Record the fallback: a copy of the held-out `OUTPUT_DIR` outside the repo, plus its trace output — refs: R15, Q-83
- [ ] T6 · **User, manual, after T11:** full rehearsal end to end in the demo terminal, live run with `--speed` and the trace. Fix only what it reveals, through a normal spec/fix branch. Close 013's manual items — refs: R15, Q-83, Acceptance
