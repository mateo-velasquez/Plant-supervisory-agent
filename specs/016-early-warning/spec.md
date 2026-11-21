# 016 · Early warning: gap trend forecast and the Pronóstico window — Spec

- **Status:** Implemented
- **Requirements:** FR-41, FR-40, FR-38, NFR-04, NFR-06, NFR-07, NFR-10
- **Stories:** —
- **Decisions:** ADR-0023 "Early warning as a code-only gap forecast shown in the dashboard". Q-119–Q-136 decided by the user; design review applied (B2–B4, C1–C8). Reused unchanged: Q-06, Q-07, Q-16, Q-20, Q-23, Q-27 and 014 R3, R13, R14, R15, 015 I2.
- **Week:** Stretch · **Priority:** set by the user

## Goal
Warn before a combination's gap crosses its next severity level, with the snapshot and time it is expected. Code projects each combination's release rate against the known production plan, stores the result in the registry with its basis, and shows it in a fourth dashboard window, **Pronóstico**, plus a small marker in Planta. It is a forecast, not a notice: it never changes a severity, a case, the outbox, the shift report, the evaluator or what the agents see (ADR-0002). There is no model in this spec.

## Scope
- **In:**
  - `domain/forecast.py` (row types); `domain/calendar.py` gains `scheduled_time`, `future_snapshots`; `metrics/plan.py` gains `shift_plan` (moved from `engine`); `metrics/forecast.py` (pure forecast);
  - registry schema v5 (`gap_forecasts`), its store and reader; `runner/forecast_step.py` (`ForecastStep`), called from `ThresholdPipeline.finish`;
  - settings `early_warning_window_snapshots`, `early_warning_horizon_snapshots`;
  - `dashboard/forecast.py`, `dashboard/anticipation.py`, `/api/forecast`, `/pronostico`, `src/frontend/{pronostico.html, forecast.js}`, the nav tab in the three existing pages, one optional field in Planta's cell.
- **Out:** projecting the delay (it already is a projection, §1); any change to minimum or effective severity, the lifecycle, notices, the outbox, reports, the evaluator, the golden set or the agents' brief and prompts (Q-119). The 009 `tendencia` extension point is **not used**; ADR-0009's follow-up is superseded by ADR-0023. No backtest command, no new library, no build step, no `umbrales.yaml` key.

## Decisions (interface choices of the spec writer; see plan)
- **I1** The forecast is one pure function in `metrics/forecast.py`; its row types live in `domain/forecast.py`, so the registry and the dashboard read them without importing `metrics`.
- **I2** Python builds every rule-bearing value (levels, labels, formatted numbers, threshold lines as gap values); the JS only maps numbers to SVG (015 I2).
- **I3** Each row stores an explicit `status` (`warm_up`, `no_target`, `suppressed`, `no_crossing`, `warning`), so the dashboard never re-derives why there is no warning.
- **I4** Progress at N is `metrics[c].progress`; only progress at n − W is read, from `released_units` (`released_through(n − W)`), never from earlier forecast rows, so a registry migrated mid-run forecasts at once.
- **I5** `ForecastStep(config, source, sink, shifts)` is one collaborator passed to `ThresholdPipeline` as a keyword argument **with no default**; tests that do not forecast pass `forecast=None` explicitly. Its reads are a narrow `ForecastSource` protocol (`open_seq`, `released_through`, `snapshot_at`); `ReleaseLog` is unchanged.
- **I6** The step runs in `finish(final)` (after any `redecide`), so an agent raise at N is seen; the pure function receives `raised` and applies `effective_severity` itself (Q-134).
- **I7** `read_run_rows` reads the table in the same read-only transaction; `RunRows.forecasts` defaults to `None` (no table, or an unreadable payload).
- **I8** Own endpoint and page; `/api/state` changes only by the cell's `forecast` field; its and `/api/agents`' held-out blocks stay exactly as 014.
- **I9** Anticipación lives in `dashboard/anticipation.py`: computed in the viewer from stored rows only, with no plant metric and no golden set. ADR-0023 records why this differs from ADR-0022 (where the viewer only reads stored evaluations).
- **I10** `/api/forecast` ignores `snapshot`, like `/api/metrics` (one `_IGNORES_SNAPSHOT` set).
- **I11** Formatting: rate and plan per snapshot 2 decimals, thresholds 1 decimal, hours an integer when whole else 1 decimal, mean lead time 1 decimal (`Decimal`, half-even).

## Behavior

### R1 · A forecast, never a decision (FR-41; Q-119; ADR-0002)
- The forecast changes no minimum or effective severity, case state, `case_history` row, notice, outbox row, shift report or trace field. A series run with `forecast=None` and with a `ForecastStep` gives byte-identical `cases`, `case_history` and `notices` tables.
- No agent tool, brief, perspective or prompt reads it; the evaluator never reads it. Traceability (FR-38) is the stored row: `snapshot_id`, `status` (the reason) and the basis numbers (the evidence).

### R2 · Inputs as of N (FR-41; Q-120)
At snapshot N (seq `n`) the forecast uses only: N's metrics (gap, gap severity, minimum severity, progress), progress at n − W from releases with seq ≤ n − W (first release wins, `count_progress`, Q-20), the combinations raised in the final decision, the static plan and calendar, and `umbrales.yaml`. The plan of future shifts is plant data, not future observation.

### R3 · Window and rate (Q-120, Q-121, Q-135)
- `W` = `early_warning_window_snapshots`. A forecast exists only when `n ≥ W`; else every row is `warm_up` (no points, no basis).
- **Rate** = (`metrics[c].progress` − progress(n − W)) / W, with progress(0) = 0. Basis: `rate`, `window` = the snapshot ids at seqs n − W + 1 and n, `points` = W, `horizon` = H. The window counts processed positions, not calendar slots.

### R4 · Future snapshots, times and the held-out boundary (Q-122, Q-130, Q-133, Q-135)
- `H` = `early_warning_horizon_snapshots`. The future snapshots are the first H snapshots after N in calendar order (mid, then closing of each shift) of the **forecast calendar**: every shift while the held-out guard is open; with it closed, the shifts before `heldout_first_shift` only. Fewer remain at its end: the horizon is truncated; none remain → no points.
- With the guard closed no refused snapshot id is ever written. Rows near the boundary depend on the guard state; the held-out run has it open.
- **Scheduled time:** mid = `inicio + (fin − inicio) / 2`, closing = `fin`. Hours = scheduled(F) − scheduled(N).

### R5 · Projected gap and thresholds in units (§1; Q-06, Q-07, Q-16, Q-120)
- For the h-th future snapshot F: **projected gap** = progress at N + rate × h − `cumulative_plan` at F.
- **Thresholds of a snapshot X**, in units behind, for L in `media`, `alta`, `critica`: max(`minimo_unidades`, `umbrales.gap.L` / 100 × `shift_plan` of X's shift × 3); all null when that plan is 0. Display and evidence only; the crossing uses R7.
- `plan_per_snapshot` = (`cumulative_plan` at the last future snapshot − at N) / future snapshots; null with none.

### R6 · Target level and status (Q-123, Q-134)
- **Target** = the level above N's gap severity: `media` if `ninguna`, `alta` if `media`, `critica` if `alta`; none if `critica`.
- **Effective severity** at N = `effective_severity(metrics[c].minimum_severity, c in raised)`, where `raised` = the combinations whose case in the final decision's `delta.cases` has `raised`. It includes the delay severity.
- **Status**, first match: `warm_up`; `no_target` (gap severity `critica`); `suppressed` (effective ≥ target); `warning` (R7 finds a crossing); else `no_crossing`. Points and basis are stored for every status but `warm_up`.

### R7 · Crossing and warning (§2; Q-07, Q-16, Q-123, Q-124)
- F is a **crossing** when `gap_severity(projected gap, gap_pct(projected gap, shift_plan of F), thresholds)` ≥ target: the official function (inclusive, `minimo_unidades`, `gap_pct` None when F's plan is 0 → never a crossing at F).
- The **warning** is the first crossing within the horizon: `target_level`, `crossing_snapshot_id`, scheduled time, `hours`, label `"<id> · <HH:MM> (en <hours> h)"`, e.g. `S010 · 22:00 (en 8 h)`. No interpolated hour.

### R8 · Storage (Q-128; ADR-0003, ADR-0023)
- Schema **v5**: one step v4 → v5 in `STEPS` creates `gap_forecasts`; `SCHEMA_VERSION` = 5. v2–v4 files migrate through the chain when the writer opens them.
- Inside the snapshot's unit of work: **one row per combination for all 9 combinations** (seq, `snapshot_id`, combination, scheduled time, `gap_units`, gap and effective severity, `status`, `target_level`, thresholds at N, points with their thresholds, basis, warning). `ForecastRow` is a persisted contract: a field added later needs a default.
- Rows commit with the snapshot (Q-23). A repeated snapshot is skipped before the unit of work, so nothing new is written (§4).

### R9 · Wiring and failure containment (Q-27, Q-136; NFR-10)
- `finish(final)` saves notices, marks reported cases, then, when `forecast` is set, runs the step on `final` (`final.delta is None` → `ValueError` before any forecast work).
- The step computes and saves inside `session.savepoint()`. Any exception rolls the savepoint back, logs one WARNING `forecast skipped for <snapshot_id> (<ErrorClass>)` and writes no row for that snapshot; the snapshot still commits with its notices.
- Wiring sites pass a `ForecastStep` built from settings and the held-out policy: `runner/cli._wire_thresholds`, `runner/agent_pipeline.build_agent_pipeline`, `evals/smoke_days_1_7.py`.

### R10 · Settings (Q-121, Q-122, Q-129)
`early_warning_window_snapshots: int = 12` (≥ 2) and `early_warning_horizon_snapshots: int = 3` (≥ 1), each in `Settings`, `.env.example` and a settings test. Never `umbrales.yaml` keys.

### R11 · Endpoint and position (014 R3; Q-125)
`GET /api/forecast?at=` parses `at` exactly as 014 R3 before any read (else 400 `dashboard: invalid at`); `snapshot` is ignored. The response carries `at`, `latest`, `positions`, `registry`, `state`, `heldout` and uses only rows with seq ≤ N.

### R12 · Read-only source, older or unreadable tables (Q-128, Q-129; 014 R2)
- Rows come from the one `load_view` per request (`mode=ro`); nothing is written or created.
- `state` = `ok` with rows; `unavailable` when the table does not exist (v4 cannot be migrated read-only), the registry is missing, or a stored payload fails `ForecastRow` validation (`forecasts=None`, other tables read as usual). Page: "Esta corrida no tiene pronósticos"; lists empty; never a 500 on any endpoint.

### R13 · Active warnings and combination charts (Q-125)
- **Warnings** = shown rows at position N with status `warning`, ordered by `hours`, then canonical combination order; each with `modelo`, `mercado`, `target_level`, `label` and a hover **basis**: rate, plan per snapshot, window `"S005–S008"`, threshold (the target's units at the crossing snapshot).
- **Combinations**: those of `calendar.combinations` (as Planta), each with `status`, gap and effective severity, `target_level`, **history** (every shown row ≤ N: seq, `snapshot_id`, gap, threshold lines as gap values ≤ 0), the **projection** of row N (points as gap values with their stepped lines) and the warning or null.

### R14 · Anticipación (Q-127, Q-131, Q-132)
Over shown rows with seq ≤ N, per combination:
- **Episode** = a maximal run of rows at consecutive positions with status `warning` and the same `target_level`. **Deadline** = the scheduled time of the last point of its last row.
- **Crossing** at row M = gap severity at M > gap severity at position M − 1 (no row at M − 1 → no crossing). A crossing **fulfils** an episode of level L when its gap severity ≥ L and its scheduled time is after the episode's first row and ≤ the deadline.
- Outcomes: **fulfilled** (lead time = hours from the first row to the first fulfilling crossing); **not fulfilled** (none, and a shown row at or past the deadline exists); **pending** (neither, as of N).
- A crossing that fulfils no episode is **missed** ("Cruce sin aviso previo") when row M − 1 had status `no_crossing` or `warning`, else **no_forecast** ("Cruce sin pronóstico posible").
- `accuracy` = counts `{fulfilled, not_fulfilled, pending, missed, no_forecast}`, `mean_lead_hours` (null with no fulfilled) and the episode list (combination, level, first and last id, outcome, crossing id, lead hours).

### R15 · Held-out omission (FR-40; Q-129, Q-133; 014 R13)
With the guard closed, a row is omitted whole when its `snapshot_id`, any point's `snapshot_id` or its warning's `crossing_snapshot_id` is refused or fails `S[0-9]{3}` (014 R13: a row written with the guard open may name day 8 ids near the boundary). Pronóstico's `heldout` is its own block `{open, omitted: {snapshots, notices, trace_lines, forecast_rows}}`; the 014 blocks are unchanged. Rows written with the guard closed never name a refused id (R4).

### R16 · Planta marker (Q-126)
Each 014 cell gains `forecast`: null, or `{target_level, label}` when the combination has an active warning at N (R13). Planta draws a small ⚠ that opens Pronóstico with `window.open("/pronostico", "pronostico")`. With `state` `unavailable` every `forecast` is null.

### R17 · HTTP surface (NFR-06; 014 R14)
014 R14 applies unchanged. New exact routes: `/pronostico`, `/forecast.js`, `/api/forecast`; anything else stays 404.

### R18 · Frontend: the Pronóstico window (Q-125; 014 R15, 015 R15)
- Nav in all four pages: Planta | Agentes | Métricas | Pronóstico; the last is `<a href="/pronostico" target="pronostico" rel="noopener">Pronóstico ↗</a>` (Métricas style). `pronostico.html` links back to the other three.
- Follows Planta's broadcast position and "Seguir en vivo" as 015 R15. Three blocks: active warnings with the hover basis, the small charts (solid history, dashed projection, stepped thresholds; null is a gap), Anticipación. SVG through `dom.js`; every 014 R15 rule extends to both new files.

### R19 · Layers (STRUCTURE)
- `domain/forecast.py` imports only `domain`. `metrics/forecast.py` imports only `domain` and `metrics`. `cases/registry/forecasts.py` imports only `domain` and `cases.registry`. `runner/forecast_step.py` imports only `domain`, `metrics` and `runner` (its `ForecastSource` and `ForecastSink` protocols are its own; `SqliteRegistry` satisfies them structurally).
- `dashboard` keeps `DASHBOARD_ALLOWED` unchanged (`cases.registry.run_reader`, `cases.registry.notices`, `domain`, …): it gets `ForecastRow` from `domain.forecast`, never imports `cases.registry.forecasts` or `metrics`.
- No module of `agents`, `mcp_server`, `hooks`, `evaluation`, `cases/notice_builder.py` or `runner/perspectives.py` imports a forecast module.

## Worked examples

**Notation.**
- **SYN** = synthetic `turnos.csv`: T01–T12, three 8-h shifts a day from 3/2/2026 06:00. S(2k−1) is Tk's mid, S(2k) its closing. Times: S001 10:00, S002 14:00, S003 18:00, S004 22:00, S005 02:00, S006 06:00, S007 10:00, S008 14:00, S009 18:00, S010 22:00, S011 02:00, S012 06:00 (repeats).
- **P** = Pickup × Local; **SB** = Sedán × Brasil. Thresholds from the versioned `umbrales.yaml` (3 units; 10/20/35 %). Unless stated: **W = 4, H = 3**, guard open, other combinations with plan 0 and no releases, `raised` empty.
- **prog(k)** = cumulative first-release progress after seq k (prog(n) = `metrics.progress`). **FC(…)** = `forecast_snapshot`. **FR(…)** = a hand-built stored row; **FT(rows, at)** = `build_forecast` over them.
- Plan "24" = 24 units per shift (12 per snapshot, daily 72; thresholds 7.2 / 14.4 / 25.2).

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **Constant-plan crossing (R3–R7).** P plan 24; prog(4) = 52, prog(8) = 92. FC at N = S008 | Gap −4.0 (−5.6 %), `ninguna`, target `media`. Rate 10.00, window S005–S008, points 4, horizon 3. Points S009 18:00 −6.0; S010 22:00 −8.0; S011 02:00 −10.0. Crossing S010 (−11.1 %, 8 ≥ 3): `warning`, label `S010 · 22:00 (en 8 h)`, hours 8, `plan_per_snapshot` 12.00. Thresholds at N 7.2 / 14.4 / 25.2. Nine rows; the other eight `no_crossing`, thresholds null. |
| E2 | **Plan change a straight line gets wrong (R5).** E1's progress; plan T01–T04 24, T05 12, T06 24 | Cumulative plan S009 102, S010 108, S011 120. Points 0.0, +4.0, +2.0; `no_crossing`; `plan_per_snapshot` 8.00. (The gap's own line, +4 at S004 to −4 at S008, would give −10 at S011: a false `media`.) |
| E3 | **Shift with plan 0 (R5, R7; Q-16).** Plan T01–T04 24, T05 0, T06 24; prog(5) = 78, prog(9) = 86. FC at N = S009 | Gap −10.0, `gap_pct` None, `ninguna`, thresholds at N null, target `media`, rate 2.00. S010 −8.0 (plan 0: no crossing, thresholds null); S011 −18.0 (−25 %, `alta` ≥ `media`: crossing); S012 −28.0. Label `S011 · 02:00 (en 8 h)`, target `media`. |
| E4 | **`minimo_unidades` blocks (R5, R7; §2).** SB plan 4 (daily 12); prog(4) = 9, prog(8) = 15. FC at S008 | Gap −1.0, rate 1.50; points −1.5, −2.0, −2.5 (−20.8 % but 2.5 < 3): `no_crossing`. Thresholds at N 3.0 / 3.0 / 4.2. |
| E5 | **Recovering trend (R7).** P plan 24; prog(4) = 39, prog(8) = 91 | Gap −5.0, rate 13.00; points −4.0, −3.0, −2.0; `no_crossing`. |
| E6 | **Full window required (R3; Q-121).** Default settings (W = 12, H = 3). P plan 24, 12 per snapshot. FC at seq 11 and seq 12 | Seq 11: nine rows `warm_up`, points [], basis null. Seq 12: `no_crossing`, rate 12.00, window S001–S012, points 12. |
| E7 | **Suppression (R6; Q-123, Q-134).** (a) P plan 24; prog(4) = 50, prog(8) = 86. (b) Same, `raised` = {P}. (c) E1 with delay severity `alta` | (a) Gap −10.0 (−13.9 %), `media`, target `alta`, rate 9.00; points −13.0, −16.0, −19.0; crossing S010 (−22.2 %): `warning` `alta`. (b) Effective `critica`, `suppressed`, same points. (c) Effective `alta` ≥ `media`: `suppressed`. |
| E8 | **Gap already `critica` (R6).** P plan 24; prog(4) = 41, prog(8) = 69 | Gap −27.0 (−37.5 %), `no_target`, target null; points stored (rate 7.00). |
| E9 | **Held-out boundary at write time (R4; Q-133).** E1 with guard closed and `heldout_first_shift` T06 (S011 on refused); then FC at S010 | At S008: points S009, S010 only, horizon truncated; crossing S010 still found. At S010: points [], `no_crossing`. No row holds `S011` or later. Guard open: E1's three points. |
| E10 | **Wiring and final decision (R1, R8, R9; I5, I6).** `ThresholdPipeline(…, forecast=ForecastStep(…))` over E7(a)'s snapshots; at S008 `finish` gets a final decision whose `delta` holds P's case with `raised=True`. Then the same series with `forecast=None` | 72 rows; S008's P row `suppressed`, effective `critica`. With `None`: no row; `cases`, `case_history`, `notices` byte-identical. `finish` with `delta=None` and a step → `ValueError`. |
| E11 | **Failure containment (R9; Q-136).** E1's series; at S008 `forecast_snapshot` raises `ValueError`; separately, `save` raises after inserting 4 of 9 rows | One WARNING `forecast skipped for S008 (ValueError)`; no S008 forecast row (none of the 4); S008 committed with its notices; S009's rows written. |
| E12 | **Idempotency and abort (R8; Q-10, Q-23).** E1's series through the runner; S008 again (same bytes, then different); a pipeline raising after the forecast save at S008, then resume | Repeat: still 72 rows, S008's byte-equal; different content writes nothing. Abort: no S008 row; after resume, 9 rows equal to the uninterrupted run's. |
| E13 | **Schema v5 and migration (R8; I4).** (a) Fresh file; (b) v4 file with 6 processed snapshots of E1, opened by `SqliteRegistry`, then S007–S008 processed | (a) `user_version` 5, `gap_forecasts` exists. (b) Version 5, earlier rows intact, no rows for S001–S006; S007, S008 not `warm_up`; S008's P row equals E1's. |
| E14 | **Settings (R10).** Defaults; `EARLY_WARNING_WINDOW_SNAPSHOTS=1`; `EARLY_WARNING_HORIZON_SNAPSHOTS=0`; `.env.example` | 12 and 3; `ValidationError` for both; both names in `.env.example`. |
| E15 | **Warnings payload and order (R11, R13; I11).** FT at 8 over E1's rows plus an SB `warning` with hours 4 (`S009 · 18:00 (en 4 h)`) | `warnings`: SB, then P. P's basis: rate "10.00", plan "12.00", window "S005–S008", threshold "7.2". P's history: 8 points; projection gaps −6.0, −8.0, −10.0 with lines −7.2, −14.4, −25.2. |
| E16 | **Episode fulfilled, pending at N (R14).** P rows: seq 9 `warning` `media` (points S010–S012), seq 10 `warning` `media` (S011–S013), seq 11 `no_crossing` with gap `media` (9–10 `ninguna`). FT at 11 and 10 | At 11: episode S009–S010 `fulfilled`, crossing S011, lead 8 h, `mean_lead_hours` "8.0"; no active warning. At 10: `pending` 1, active warning `S011 · 02:00 (en 4 h)`. |
| E17 | **Not fulfilled (R14).** P rows: seq 13 `warning` `media` (S014–S016); 14–16 `no_crossing`, `ninguna` | At 15: `pending` 1. At 16 (deadline S016 22:00 reached): `not_fulfilled` 1. |
| E18 | **Missed and no-forecast (R14; Q-131).** P rows: (a) seq 17 `no_crossing`, 18 `media`; (b) seq 3 `warm_up`, 4 `media`; (c) seq 20 `suppressed`, 21 `media` | (a) `missed` 1. (b), (c) `no_forecast` 1 each. |
| E19 | **v4 and unreadable tables (R12, R16; C4).** (a) TH_DIR copy with `gap_forecasts` dropped and `user_version` 4; (b) a v5 copy with one `payload` set to `{}`. GET `/api/forecast`, `/api/state`, `/api/metrics` | Both: `state` `unavailable`, lists empty, every cell `forecast` null; all three 200; `/api/state` otherwise equal to the intact copy's; bytes unchanged, nothing created. |
| E20 | **Held-out rows (R15).** FT with guard closed (first T06): FR rows at S009, S010, S011, S012; `/api/state` on the same view | Rows S011, S012 omitted, `forecast_rows` 2; no body names `S011`, `S012`, `T06`. `/api/state` `heldout.omitted` keys exactly 014's three. (b) Rows written with the guard open: P at S009 naming S011 in points and crossing, SB at S010 in points only, a third combination at S010 in its crossing only, P at S008 naming S009–S010, P at S010 naming nothing; viewed closed → the first three omitted, `forecast_rows` 3, neither `/api/forecast` nor the Planta cells' `forecast` names `S011` or `S012`. |
| E21 | **Planta marker and replay (R16, R11).** `/api/state` over E16's rows at `at=10` and `at=11` | At 10: P `forecast` = `{"target_level": "media", "label": "S011 · 02:00 (en 4 h)"}`, others null. At 11: all null. |
| E22 | **HTTP (R17; I10).** GET `/pronostico`, `/forecast.js`; `/pronostico/`, `/forecast.js/`; POST `/api/forecast`; bad Host; write lock held; `at=abc`; `snapshot=../x` | 200 HTML, JS; 404 ×2; 405; 403; 503 `dashboard: registry busy`; 400 `dashboard: invalid at`; `snapshot=../x` → 200, same body as none. 014 R14 headers on all. |
| E23 | **Risk: frontend assets (R18).** Asset scan; `pronostico.html`; other pages; `app.js` | `pronostico.html` loads only `/app.css`, `/dom.js`, `/forecast.js`; no inline script, `<style>`, `style=`, `on…=`. All four pages contain `href="/pronostico" target="pronostico"`. `app.js`'s new `window.open` takes the literal `"/pronostico"`. |
| E24 | **Risk: imports (R1, R19).** Boundary scan | `domain/forecast.py`, `metrics/forecast.py`, `cases/registry/forecasts.py`, `runner/forecast_step.py` follow R19. Importers of the non-domain forecast modules (`metrics.forecast`, `cases.registry.forecasts`, `runner.forecast_step`, `dashboard.forecast`, `dashboard.anticipation`) are exactly: `cases/registry/{run_reader,sqlite}.py`, `runner/{pipeline,forecast_step,cli,agent_pipeline}.py`, `dashboard/{forecast,server,state}.py` (`forecast.py` imports `dashboard.anticipation`; `server.py` and `state.py` import `dashboard.forecast`), `evals/smoke_days_1_7.py` (`ForecastConfig`, `ForecastStep`); the excluded layers import none of them nor `domain.forecast`. `DASHBOARD_ALLOWED` unchanged. |

## Edge cases and assumptions
- **X1** · (Q-135) A missing snapshot stretches the window; FR-42 is not implemented and days 1–7 have none.
- **X2** · (Q-134) A combination at `alta` by delay gets no gap warning to `media` or `alta`: intended, the warning anticipates a severity it does not yet have.
- **X3** · A jump `ninguna` → `alta` fulfils a `media` episode and is not also `missed`.
- **X4** · A crossing at an episode's first row is impossible: the target is above that row's gap severity.
- **X5** · An episode whose deadline never arrives (series end; with the guard closed, the end of day 7) stays `pending`.
- **X6** · Float boundaries: the crossing uses `gap_severity`, so a projected gap exactly at a threshold behaves as the official severity (Q-07).
- **X7** · (Q-136) A snapshot whose forecast failed has no rows: Planta shows no marker, history has a hole, and R14 sees no crossing at the next row.

## Acceptance
- [ ] E1–E24 pass on synthetic fixtures; CI never calls the model (NFR-07). Every new test cites its spec id.
- [ ] **Changed expectations (not removed):**
  - schema: `SCHEMA_VERSION == 4` → 5 (`tests/unit/cases/test_registry.py:126`); final `user_version` 4 → `SCHEMA_VERSION` (`test_cause_store.py:99, 111`, `test_review_store.py:80, 93`); `assert "4" in message` → `str(SCHEMA_VERSION)` (`test_cause_store.py:132`, `test_review_store.py:111`) and test names saying "four" → "current"; `test_review_store.py:86` parametrize `[2, 3]` → `[2, 3, 4]`; `:120` fresh vs migrated covers a v4 file;
  - pipeline: every `ThresholdPipeline(...)` / `from_registry(...)` call passes `forecast=` (`None` in tests that do not forecast);
  - dashboard: `ASSET_NAMES` and the invalid-`at` parametrization (`tests/integration/test_dashboard_http.py`); the HTML-page and nav checks (`tests/unit/dashboard/test_frontend_assets.py`).
- [ ] Specs 001–015 tests pass unchanged otherwise.
- [ ] Docs, `visual-designer` pass, real-run review with the user's permission (T9, T11, T12).
- [ ] `ruff`, `mypy --strict` and `pytest --cov` pass.

## Size
About 25 KB, near 015's: the forecast, its storage, its failure containment and its window share one row contract; splitting the window out would ship stored forecasts nobody can see.
