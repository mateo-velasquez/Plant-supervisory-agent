# 015 · Metrics window of the live dashboard — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts.

- **mypy and pytest per commit.** A commit's tests use only symbols that exist at that commit. Builder helpers land in the task whose tests first use them.
- **Type order:** T1 (summary_file) → T2–T3 (shared helpers) → T4–T5 (`metrics`) → T6 (run report) → T7 (`panels`) → T8 (`server`) → T9 (frontend).
- **Test conventions.** Every test cites its spec id (`Risk:` tests too). Helpers come `from metrics_builders import ...`, `from dashboard_builders import ...`, `from trace_builders import ...`, never `from tests....`. Synthetic fixtures only.
- **New test basenames** (unique, check before writing): `test_summary_file.py`, `test_dashboard_metrics.py`, `test_dashboard_panels.py`, `test_run_report.py`, `test_dashboard_metrics_http.py`.
- **Owner:** tests by `test-writer`, code by `domain-implementer`, unless stated.
- Task numbers changed on 2026-11-20 (design review); no task had started.

- [x] T0 · **Spec writer, before Ready:** spec, plan, tasks, Q-101–Q-118 and ADR-0022 (Proposed). `design-reviewer` pass done (2026-11-20): F1–F10 applied, run report settled as option A (Q-108). Closes when the user sets Ready — refs: I1–I13, Q-101–Q-118 · plan: Design notes, Alternatives
- [x] T1 · Tests E10 (new `tests/unit/evaluation/test_summary_file.py` for `read_summary` and the atomic write; the `deliverables` and `run_eval` cases as new tests in the existing `test_summary.py` / CLI test file) and E20's `summary_file` part (`tests/unit/test_import_boundaries.py`, one new test) → `evaluation/summary_file.py` (`EVAL_NAME`, stored models, `read_summary`, `write_summary_json`, `_write_atomic`); `EvalSummary.deliverables` (set by `evaluate`, written by `to_json`); `write_summary` delegates; `run_eval` stores `str(registry.resolve())`. 005 tests unchanged (E34a bytes and name) — refs: R10, R16, I10, E10, E20, Q-104, Q-114, Q-118 · plan: `evaluation/summary_file.py`, `EvalSummary.deliverables`
- [x] T2 · Shared helpers, no behavior change, 014 tests unchanged and no new test:
  - `source.lines_as_of`, used by `cost_as_of`;
  - `day_label` moved from `state._day_label` to `source.py`;
  - `heldout.json_shown`, used by `line_shown`.

  — refs: I3, I6, R3, R7, R12 · plan: `json_shown`, `dashboard/source.py` helpers
- [x] T3 · Source helpers for Planta and Métricas, no behavior change, 014 tests unchanged and no new test: `deliverables_as_of`, `author_of`, `DayLookup`/`day_lookup` in `source.py`; `state.py` refactored to use them (`_current`, `_days`, `_kpis`, `_feed`, `_notice_item`) — refs: I11, R7, R8 · plan: `dashboard/source.py` helpers
- [x] T4 · Tests E2, E3, E4, E5, E6, E21 (`tests/unit/dashboard/test_dashboard_metrics.py`, through `build_metrics` over `load_view` or MV, with empty panels); `tests/metrics_builders.py` with `call`, `metric_line` (incl. `totals_usd`), `metric_view` → `dashboard/metrics.py` (`build_metrics`, `_cost` with `Decimal` running sums and `unplaced_usd` as the remainder); the metrics `TypedDict`s; `AccuracyPanel` (with `__post_init__`), `RunItem` (`Literal` fields) and `RunsPanel` as dataclasses in `dashboard/panels.py` (loaders come in T7) — refs: R1, R3, R4, R5, R6, I3, I7, I13, E2–E6, E21, Q-116 · plan: `build_metrics`, `dashboard/panels.py`, API
- [x] T5 · Tests E1 (no-400 cases), E7, E8, E9, E17, E23 (same file; `metrics_builders` gains `CAL`) and E20's `dashboard` part in `tests/unit/test_import_boundaries.py`: **changed expectation**, `DASHBOARD_ALLOWED` adds the six R16 names (name-level), re-cited 014 E22 → 015 E20; **new test**, the `loaded_by_import` probe of `plant_monitor.dashboard.server` (no `evaluation.{scoring,golden,causes,summary}`) → `_days`, `_authors`, `_noise` (incl. the `invalid` state), `_heldout` (registry and trace counts) — refs: R1, R7, R8, R9, R12, R16, I9, I11, E1, E7, E8, E9, E17, E20, E23, Q-105, Q-115 · plan: `build_metrics`
- [x] T6 · Test E16 (`tests/unit/telemetry/test_run_report.py`) → `telemetry/trace.py` gains `STAMP_FORMAT`, `ISO_Z_FORMAT`, `TRACE_NAME` (`trace_path` uses `STAMP_FORMAT`); `telemetry/run_report.py` (moved models, `report_path`, atomic `write_report`, `REPORT_NAME`, `read_report`); `runner/summary.py` imports what it uses and re-exports `report_path` only; `runner/cli.py` imports the new home. 012 tests unchanged. E20's telemetry part is the existing `test_e22_telemetry_imports_only_domain_and_is_sdk_free` (no new test) — refs: R13, R16, I5, I10, E16, E20, Q-108 · plan: `telemetry/trace.py` constants, `telemetry/run_report.py`
- [x] T7 · Tests E11, E12, E13, E14, E15, E22 (`tests/unit/dashboard/test_dashboard_panels.py`, through `load_accuracy` / `load_runs` and then `build_metrics`; `metrics_builders` gains `eval_file`) → `load_accuracy` (candidates, match, `earlier`, `unreadable`, held-out), `load_runs` (reports, pairing by name, running items, `unreadable`, held-out), and `_accuracy` / `_runs` / the `evals` and `run_reports` counts in `build_metrics` — refs: R2, R11, R12, R13, I4, I8, E11–E15, E22, Q-103, Q-104, Q-110, Q-113, Q-117 · plan: `dashboard/panels.py`, `build_metrics`
- [x] T8 · Tests E1 (400 cases), E18 and E24 (`tests/integration/test_dashboard_metrics_http.py`; `metrics_builders` gains `MT`). **Changed expectations** in `tests/integration/test_dashboard_http.py`: `ASSET_NAMES` adds `metricas.html` and `metrics.js`; E1's invalid-`at` parametrization adds `/api/metrics`. → `DashboardApp(evals_dir=, runs_dir=)`, `from_settings`, the two `ASSETS` routes, `/api/metrics` (ignores `snapshot`). T8 creates placeholder `src/frontend/metricas.html` and `metrics.js` (valid, minimal, sink-free) that T9 replaces — refs: R1, R2, R14, I12, E1, E18, E24 · plan: `DashboardApp`
- [x] T9 · **domain-implementer, frontend:** test E19 first (`tests/unit/dashboard/test_frontend_assets.py`, by test-writer). **Changed expectation:** the HTML-page check is parametrized over `metricas.html` too; add the nav-link assertion. Then:
  - `metricas.html` and `metrics.js`: header with the position, banners (trace error, busy, held-out counts), KPI row, the R15 charts, "Ruido en vivo" list (and its invalid state), accuracy table with its states and "Ruido evaluado", runs table;
  - the "Métricas ↗" link in `index.html` and `agentes.html`;
  - following Planta over `BroadcastChannel`, plus "Seguir en vivo" / "Seguir a Planta";
  - 503 keeps the last payload; text nodes only; `null` drawn as a gap.
  - Check by hand against the JSON of AGENT_DIR and TH_DIR (server on a copy).

  — refs: R9, R11, R12, R15, E19, Q-101, Q-111, Q-115 · plan: API, Data flow
- [x] T10 · **visual-designer:** a presentation pass on `metricas.html`, `metrics.js` (presentation code only) and `app.css`: layout, chart legibility, dark theme, Spanish labels. Then E19 is re-run; no Python changes — refs: R15, Q-111 · plan: Design notes
- [ ] T11 · **Main session, check:** `/verify-criteria specs/015-analytics-dashboard`, `design-reviewer` on the diff, `/check` — refs: Acceptance
- [x] T12 · **Main session, docs:**
  - README "Metrics window";
  - `docs/STRUCTURE.md` rows and dependency lines;
  - roadmap row 015 (priority Could, status);
  - ADR-0022 set to Accepted when the spec is Ready, and its index row.

  — refs: Acceptance · plan: Docs rows
- [ ] T13 · **User, manual, needs the user's permission:** open Métricas on a real run's `OUTPUT_DIR` (a days 1–7 run any time; days 8–10 stay omitted while the guard is closed, and the held-out run is reviewed only after it happens, with `CLAUDE_ALLOW_HELDOUT=1` for Claude Code). Check that:
  - the last cumulative USD plus `unplaced_usd` equals Planta's cost and the run summary's series USD;
  - the cache share is above 0 from the second call of each agent's session (Q-63);
  - the accuracy panel picks the evaluation of this registry and flags it stale after more snapshots run;
  - the run durations match the run reports;
  - Métricas follows Planta's replay.

  Log any problem before changing anything — refs: R3, R4, R11, R13, R15, FR-40
