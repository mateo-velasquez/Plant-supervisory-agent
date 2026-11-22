# 016 · Early warning: gap trend forecast and the Pronóstico window — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts.

- **mypy and pytest per commit.** A commit's tests use only symbols that exist at that commit. Builder helpers land in the task whose tests first use them.
- **Type order:** T1 (domain, calendar, settings) → T2 (pure forecast) → T3 (schema, store) → T4 (step + pipeline + callers) → T5 (reader + source) → T6 (builders + cell) → T7 (server) → T8 (frontend).
- **Test conventions.** Every test cites its spec id (`Risk:` tests too). Helpers come `from forecast_builders import ...`, `from dashboard_builders import ...`, `from trace_builders import ...`, never `from tests....`. Synthetic fixtures only; never days 8–10.
- **New test basenames** (unique, check before writing): `test_forecast_settings.py`, `test_forecast_model.py`, `test_forecast_store.py`, `test_forecast_step.py`, `test_dashboard_forecast.py`, `test_dashboard_forecast_http.py`.
- **Owner:** tests by `test-writer`, code by `domain-implementer`, unless stated.
- 2026-11-21: design review (B2–B4, C1–C8) and the user's decisions on Q-130–Q-136 applied; no task had started.

- [x] T0 · **Main session, before Ready:** ADR-0023 "Early warning as a code-only gap forecast shown in the dashboard" (supersedes ADR-0009's `tendencia` follow-up); roadmap row 016; `design-reviewer` pass done (2026-11-21), findings applied in spec and plan. Closes when the user sets Ready — refs: I1–I11, Q-119–Q-136 · plan: Design notes, Alternatives
- [x] T1 · Tests E14 (`tests/unit/test_forecast_settings.py`) and the `scheduled_time` / `future_snapshots` cases used by E1, E9 (`tests/unit/domain/` existing calendar test file, new tests) → the two `Settings` fields and `.env.example`; `domain/forecast.py` (row types, validator); `domain/calendar.scheduled_time`, `future_snapshots` — refs: R4, R8, R10, E14, Q-121, Q-122, Q-130 · plan: `domain/forecast.py`, `domain/calendar.py`
- [x] T2 · Tests E1–E9 (`tests/unit/metrics/test_forecast_model.py`, through `forecast_snapshot`; `tests/forecast_builders.py` with `SYN`, `plan_rows`, `fc`) → `metrics/forecast.py` (`ForecastConfig`, `WindowBase`, `threshold_units`, `forecast_snapshot`); `shift_plan` moved to `metrics/plan.py`, `engine` imports it, 001 tests unchanged — refs: R2–R7, I1, I3, I4, I11, E1–E9, X2, X6, Q-120–Q-124, Q-130, Q-133–Q-135 · plan: `metrics/forecast.py`
- [x] T3 · Test E13 and the store cases (`tests/unit/cases/test_forecast_store.py`: `save` refusing a row whose seq is not the open one; `released_through`; `snapshot_at`). **Changed expectations** (spec Acceptance, schema list): `test_registry.py:126`; `test_cause_store.py:99, 111, 132`; `test_review_store.py:80, 86, 93, 111, 120`, and the "four" test names → `MIGRATION_V4_TO_V5_BODY`, `STEPS[4]`, `SCHEMA_VERSION = 5`; `cases/registry/forecasts.py` (`SqliteForecastStore`, `read_forecasts`); `SqliteRegistry.forecasts` — refs: R8, I4, E13 · plan: `cases/registry` (schema v5, store, reader)
- [x] T4 · Tests E10, E11, E12 (`tests/unit/runner/test_forecast_step.py`; E12 through the 012 runner on synthetic snapshots; `forecast_builders` gains `failing_sink`) → `runner/forecast_step.py` (`ForecastSource`, `ForecastSink`, `ForecastStep.build`, `run` with savepoint and WARNING); `ThresholdPipeline` / `from_registry` keyword `forecast` with no default, called in `finish`. **Callers:** `runner/cli._wire_thresholds`, `runner/agent_pipeline.build_agent_pipeline`, `evals/smoke_days_1_7.py` build the step; **changed expectations** `tests/incident_runs.py`, `tests/unit/runner/test_pipeline.py`, `test_pipeline_causes.py`, `test_judgment.py`, `tests/integration/test_notices_runner.py`, `test_judgment_runner.py`, `test_agent_runner.py` and any other site mypy lists pass `forecast=None` — refs: R1, R8, R9, I5, I6, E10–E12, X7, Q-27, Q-128, Q-136 · plan: `runner/forecast_step.py`, `runner/pipeline.py`
- [x] T5 · Tests E19 (reader part: `read_run_rows` gives `forecasts=None` for a v4 copy and for an invalid payload, other tables intact) and E20 (registry part, through `load_view`; `tests/unit/dashboard/test_dashboard_forecast.py`) → `RunRows.forecasts` (default `None`), `run_reader` calls `read_forecasts`; `RunView.forecasts`; `Omitted.forecast_rows: int = 0`; `_filter_rows` omits refused rows. `tests/dashboard_builders.py` unchanged — refs: R12, R15, I7, E19, E20, Q-129, Q-133 · plan: `cases/registry` (reader), Modules
- [x] T6 · Tests E15–E18, E20 (payload part) and E21 (same file; `forecast_builders` gains `fr`, `ft`) → `dashboard/anticipation.py` (`score_episodes`), `dashboard/forecast.py` (`build_forecast`, `active_warnings`), the forecast `TypedDict`s incl. `ForecastOmitted`, `Cell.forecast` in `state.py` from `active_warnings` — refs: R11, R13–R16, I2, I8, I9, I11, E15–E18, E20, E21, X3–X5, Q-125–Q-127, Q-131, Q-132 · plan: `dashboard/anticipation.py` and `dashboard/forecast.py`, API
- [x] T7 · Tests E19 (HTTP part), E22 and E24 (`tests/integration/test_dashboard_forecast_http.py`; E24 in `tests/unit/test_import_boundaries.py`, new test; `DASHBOARD_ALLOWED` unchanged). **Changed expectations** in `tests/integration/test_dashboard_http.py`: `ASSET_NAMES` adds `pronostico.html`, `forecast.js`; the invalid-`at` parametrization adds `/api/forecast` → the two `ASSETS` routes, `/api/forecast`, `_IGNORES_SNAPSHOT`; placeholder `pronostico.html` and `forecast.js` (valid, minimal, sink-free) that T8 replaces — refs: R1, R11, R12, R17, R19, I8, I10, E19, E22, E24 · plan: `DashboardApp` and the cell
- [x] T8 · **domain-implementer, frontend:** test E23 first (`tests/unit/dashboard/test_frontend_assets.py`, by test-writer). **Changed expectation:** the HTML-page check is parametrized over `pronostico.html`; the nav assertion covers all four pages. Then:
  - `pronostico.html` and `forecast.js`: header with the position, banners (busy, held-out counts, "Esta corrida no tiene pronósticos"), active warnings with the hover basis, the small charts (solid history, dashed projection, stepped thresholds; null is a gap), Anticipación (counts, mean lead time, episodes);
  - nav tab "Pronóstico ↗" in `index.html`, `agentes.html`, `metricas.html`;
  - Planta ⚠ marker in `app.js` from `cell.forecast`, `window.open("/pronostico", "pronostico")`;
  - following Planta and "Seguir en vivo" as 015; 503 keeps the last payload; text nodes only.
  - Check by hand against the JSON of a synthetic run (server on a copy).

  — refs: R16, R18, E23, Q-125, Q-126 · plan: API, Data flow
- [x] T9 · **visual-designer:** presentation pass on `pronostico.html`, `forecast.js` (presentation code only), the Planta marker and `app.css`: layout of the three blocks, chart legibility, warning emphasis, dark theme, Spanish labels. E23 re-run; no Python changes — refs: R18 · plan: Design notes
- [x] T10 · **Main session, check:** `/verify-criteria specs/016-early-warning`, `design-reviewer` on the diff, `/check` — refs: Acceptance
- [x] T11 · **Main session, docs:**
  - `docs/STRUCTURE.md` rows and dependency lines; the `domain/perspectives.py` row no longer promises `tendencia`;
  - README "Forecast window" section and the ADR-0023 decision line;
  - roadmap row 016 (status), ADR-0023 set to Accepted when the spec is Ready, its index row; ADR-0009's follow-up marked superseded;
  - `docs/agent-capabilities.md` untouched (no agent change).

  — refs: Acceptance · plan: Docs rows
- [ ] T12 · **User, manual, needs the user's permission:** open Pronóstico on a real run's `OUTPUT_DIR` (a days 1–7 run any time; the held-out run is reviewed only after it happens, with `CLAUDE_ALLOW_HELDOUT=1` for Claude Code). Check that:
  - no forecast exists before the twelfth snapshot, and every row from there has a basis;
  - warnings anticipate the known incidents of days 1–7 or the panel says why not (`suppressed`, `missed`, `no_forecast`);
  - the ⚠ marker in Planta matches the warnings list at the same position;
  - Pronóstico follows Planta's replay; with the guard closed no row names a day 8 snapshot;
  - the run log has no "forecast skipped" WARNING;
  - in a threshold-only run, `cases`, `case_history` and `notices` match a threshold-only run made before this spec.

  Log any problem before changing anything; window and horizon are tuned only on days 1–7 — refs: R1, R3, R4, R9, R13, R14, R16, FR-40

## Amendment 2026-11-21: empty table and `run --dashboard`

Same conventions as above. New test basename: `test_run_dashboard_cli.py` (check it is unique). T12 can run after T15 with `run --dashboard`.

- [x] T13 · Test E25 (`tests/unit/dashboard/test_dashboard_forecast.py` and `tests/integration/test_dashboard_forecast_http.py`, new tests) → `build_forecast`'s `available` rule; the hint text under the `unavailable` banner in `forecast.js` (text node only, E23 re-run) — refs: R12, E25, Q-139, X8 · plan: Amendment: empty table
- [x] T14 · Test E28 (`tests/integration/test_dashboard_forecast_http.py` or the 014 HTTP test file, new test, port 0) → `RunningDashboard`, `start_dashboard` in `dashboard/server.py`; `serve_dashboard` unchanged — refs: R20, I14, E28 · plan: Amendment: `start_dashboard`
- [x] T15 · Tests E26, E27 (`tests/integration/test_run_dashboard_cli.py`, synthetic fixtures, fake `start_dashboard` and `wait`, fixed `now`) → `--dashboard` in `parse_args`, `RunOptions.dashboard`, `CliDeps.start_dashboard` and `wait`, `_run_with_dashboard`, optional `started` in `_run`. Every existing 012 / 014 CLI test passes unchanged — refs: R20, I12–I14, E26, E27, Q-137, Q-138, X9 · plan: Amendment: `run --dashboard`
- [x] T17 · Test E29 (`tests/unit/dashboard/test_dashboard_forecast.py`) → `build_forecast(..., history_window)`, `DashboardApp` passes `early_warning_window_snapshots` — refs: R13, E29, Q-140
- [ ] T16 · **Main session:** docs (README "Running", `docs/demo.md` steps 2 and 4, STRUCTURE rows; Q-137–Q-139 are already in `docs/requirements.md`), `/verify-criteria specs/016-early-warning`, `reviewer` on the diff, `/check` — refs: Acceptance · plan: Docs rows
  - 2026-11-21: docs and `/check` done (2011 passed, coverage 98%); `/verify-criteria` and `reviewer` pending.
