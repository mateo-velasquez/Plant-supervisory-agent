# 014 · Live dashboard with replay — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts.

- **mypy and pytest per commit.** A commit's tests use only symbols that exist at that commit. Write each task's new files only in that task; builder helpers land in the task whose tests first use them.
- **Type order:** T1 (removal) → T2 (shared helpers) → T3 (`run_reader`) → T4 (`heldout`) → T5 (`source`) → T6–T7 (`state`) → T8–T9 (`agents`) → T10 (`server`) → T11 (CLI, setting) → T12 (frontend).
- **Test conventions.** Every test cites its spec id (`Risk:` tests too). Helpers come `from dashboard_builders import ...`, `from trace_builders import ...`, `from notice_builders import ...`, never `from tests....`. Synthetic fixtures only.
- **New test basenames** (unique, check before writing): `test_run_reader.py`, `test_dashboard_heldout.py`, `test_dashboard_source.py`, `test_dashboard_state.py`, `test_dashboard_agents.py`, `test_dashboard_http.py`, `test_cli_dashboard.py`, `test_frontend_assets.py`.
- **Owner:** tests by `test-writer`, code by `domain-implementer`, unless stated.
- The folder was renamed from `specs/014-visual-reports/`. The static-HTML tasks of that design never merged and are not kept.

- [x] T0 · **Spec writer, before Ready:** spec, plan, tasks and Q-84–Q-100 written. The user runs `git mv specs/014-visual-reports specs/014-live-dashboard` (or removes the old folder). Status stays `Draft` until the user sets Ready — refs: I1–I8, Q-84–Q-100 · plan: Design notes
- [x] T1 · **Removal (domain-implementer) and agent scope (main session).** The tests are deleted with their feature, not to lower coverage of kept code.
  - delete `src/plant_monitor/notify/html.py`;
  - in `runner/cli.py`, delete `HtmlOptions`, `_HTML_COMMAND`, the `html` subparser and `_html`, and narrow `parse_args` (keep `_fail` through `write_safe`);
  - delete `Settings.html_dir`;
  - delete `tests/unit/notify/test_html_render.py`, `tests/integration/test_cli_html.py`, `tests/html_builders.py`, `tests/fixtures/html/` and `test_014_e10_html_dir_is_derived_from_output_dir_with_no_new_variable` in `tests/test_config.py`;
  - keep `domain/text.py`, `notify/atomic.py` and `case_snapshot_id` with their tests;
  - main session: update `.claude/agents/visual-designer.md` (scope: `src/frontend/` CSS, markup and presentation JS, spec `specs/014-live-dashboard/`, ADR-0021; no Python, no sinks of R15) and its row in the `CLAUDE.md` agent table, before T12;
  - pytest and mypy stay green.

  — refs: Acceptance (removed tests), R15 · plan: Modules
- [x] T2 · Shared helpers, no behavior change for 004/005/013 (their tests unchanged):
  - no new test for `is_deliverable` here: E23 (in T3) checks it against `read_deliverables`;
  - test E10's span part in the existing `tests/unit/domain/test_verbatim.py`.

  → `cases/registry/readonly.py` (`open_readonly`, `check_columns`, `READ_TIMEOUT_S`), used by `read_deliverables` and `notice_reader`; `notices.is_deliverable`; `telemetry/trace.py`: `CorruptTraces`, `TextBy`, `index_attempts`, `text_by` moved from `trace_query` (which imports them), and `read_trace_files(..., drop_partial_tail=False)`; `domain/verbatim.verbatim_spans` — refs: I3, I4, R10, R12, E10 · plan: `open_readonly`, `is_deliverable`, `telemetry/trace.py` additions, `verbatim_spans`
- [x] T3 · Tests for `read_run_rows` (`tests/integration/test_run_reader.py`, over TH_DIR and AGENT_DIR):
  - rows in seq order, counts match direct SQL;
  - E23;
  - E24 at reader level (`RegistryBusy`);
  - a missing path gives `None` and is not created;
  - the `not sqlite` file gives `ValueError` `dashboard: registry.sqlite3 is not a readable registry (DatabaseError)`;
  - bytes unchanged;
  - E22's `run_reader` / `readonly` part.

  → `cases/registry/run_reader.py` (`RunRows`, `RegistryBusy`) — refs: R2, E16 (500 message), E22, E23, E24, I3, I7 · plan: `read_run_rows`
- [x] T4 · Test E14 (`tests/unit/dashboard/test_dashboard_heldout.py`) → `dashboard/heldout.py`:
  - the patterns, `UnsafeId`, `validate_ids`, `shown_ids` and `select_shown` moved from the deleted `notify/html.py`, with prefix `dashboard:` (read them with `git show 7133458:src/plant_monitor/notify/html.py`, read-only);
  - plus `notice_ids_valid`, `case_shown`, `history_shown` and `line_shown`.

  — refs: R13, E14, I5 · plan: `dashboard/heldout.py`
- [x] T5 · Tests E12 (attempt counts), E13 and E15's `rows.cases` assertion, all through `load_view` (`tests/unit/dashboard/test_dashboard_source.py`) → `dashboard/source.py` (`Calendar`, `Omitted`, `RunView`, `load_view`, `positions`, `resolve_at`); `dashboard/payloads.py` stubs needed by the signatures; `tests/dashboard_builders.py` with `run_rows` and `RESUMED` only — refs: R2, R3, R12, R13, E12, E13, E15 · plan: `dashboard/source.py`, `dashboard/payloads.py`
- [x] T6 · Tests E1 (through `resolve_at` + `build_state`; the 400 cases wait for T10), E2, E3, E5 (`tests/unit/dashboard/test_dashboard_state.py`) → `dashboard/state.py`: header, days, cells with the R6 tie-break, sparkline, cause as of N; the state `TypedDict`s — refs: R3, R4, R6, E1, E2, E3, E5 · plan: `dashboard/state.py`, `dashboard/payloads.py`, API
- [x] T7 · Tests E4, E6, E15 (state part) (same file) → KPIs, cost through `run_totals` (aborted lines included; at `latest` also those of snapshots that never committed), the feed with `text_by` authors, held-out counts — refs: R5, R7, R13, E4, E6, E15 · plan: `dashboard/state.py`, API
- [x] T8 · Tests E7, E10 (`segments` unit part), E11, E12 (selected) (`tests/unit/dashboard/test_dashboard_agents.py`) → `dashboard/agents.py`: `build_agents` (list, KPIs, selection rules), `segments`, `explain_hook`; the agents `TypedDict`s — refs: R8, R10, R11, R12, E7, E10, E11, E12 · plan: `dashboard/agents.py`
- [x] T9 · Tests E8, E9, E10 (AGENT_DIR `logbook_read` part), E15 (agents part) (same file) → `conversation`: event order, hook/tool pairing, thinking, registration, `logbook_read` through `LogbookStore` — refs: R9, R10, R13, E8, E9, E10, E15 · plan: `dashboard/agents.py`, API
- [x] T10 · Tests E1 (400 cases), E16, E17, E21's asset-missing case, E24 (HTTP 503) (`tests/integration/test_dashboard_http.py`); `dashboard_builders` gains `HOST`, `app_of`, `get_json` → `dashboard/server.py`: `ASSETS`, `CSP`, `ALLOWED_HOSTS`, `Response`, `DashboardApp` (constructor, `from_settings(frontend_dir=)`, `handle`), `make_server`, `serve_dashboard(app, port, on_ready)`. T10 creates placeholder `src/frontend/*` files (valid, minimal, sink-free) that T12 replaces — refs: R1, R2, R14, E1, E16, E17, E21, E24, Q-98 · plan: `dashboard/server.py`
- [x] T11 · Tests E18, E19 (`tests/integration/test_cli_dashboard.py`; `dashboard_builders` gains `FakeServe`), E20 (`tests/test_config.py`), E22 (`tests/unit/test_import_boundaries.py`: one new test for `dashboard`) → `Settings.dashboard_port`, `.env.example`, `DashboardOptions`, the `dashboard` subparser, `_dashboard` with `on_ready`, `CliDeps.serve` — refs: R1, R16, E18, E19, E20, E22 · plan: `main` (dashboard branch), `Settings.dashboard_port`
- [x] T12 · **visual-designer with domain-implementer, frontend:** test E21 (`tests/unit/dashboard/test_frontend_assets.py`, by test-writer first) → `src/frontend/` from the approved prototype (`z_helps/live-dashboard-prototype/`, reference only):
  - Planta: header, timeline by day, KPIs, matrix with sparklines, feed with author badges, details, the Agentes link;
  - Agentes: KPIs, snapshot list, three lanes, pin and "Seguir en vivo";
  - replay controls, BroadcastChannel, 503 "Registro ocupado" keeping the last payload;
  - dark theme; text nodes only; only the two link forms of the plan.
  - Check by hand against the JSON of AGENT_DIR and TH_DIR (server on a copy).

  — refs: R2, R3, R4, R7, R8, R9, R15, E21 · plan: API, Frontend link forms, Design notes
- [x] T13 · **Main session, check and docs:**
  - `/verify-criteria specs/014-live-dashboard` and `design-reviewer` on the diff;
  - README "Live dashboard" (command, port, live vs replay, read-only, held-out banner, runs from the repo only) replacing "How to render the HTML reports";
  - `docs/STRUCTURE.md` rows and dependency line;
  - roadmap row 014;
  - ADR-0021 rewritten from the plan and its index row;
  - `/check`.

  — refs: Acceptance · plan: ADR-0021 text, Docs rows
- [ ] T14 · **User, manual, needs the user's permission:** open the dashboard on a real run's `OUTPUT_DIR` (a days 1–7 run any time; the held-out run only after it happens, with `CLAUDE_ALLOW_HELDOUT=1` for Claude Code). Check that:
  - live follows a running `plant-monitor run --speed`;
  - replay steps and the slider reproduce each snapshot;
  - the timeline is readable for 30 shifts;
  - the cost at `latest` equals the run summary's (aborted attempts included, Q-97);
  - the logbook highlights hit the cited fragments;
  - every shift report is listed;
  - with `HELDOUT_OPEN=false`, no held-out id appears.

  Log any problem before changing anything — refs: R3–R13, Acceptance, FR-40
