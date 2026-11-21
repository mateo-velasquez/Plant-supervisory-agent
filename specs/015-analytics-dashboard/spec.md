# 015 · Metrics window of the live dashboard — Spec

- **Status:** Implemented (T11 closing checks and T13 real-run review pending)
- **Requirements:** FR-37, FR-39, FR-40, FR-22, FR-38, NFR-06, NFR-07
- **Stories:** US-11, US-12
- **Decisions:** ADR-0022 (Accepted). Q-101–Q-118 decided by the user; design review applied (F1–F10). Reused unchanged: Q-33, Q-77, Q-97, Q-100 and 014 R2, R3, R12–R15 (ADR-0021).
- **Week:** Stretch · **Priority:** Could

## Goal
A third window of the 014 dashboard, **Métricas**, that shows what a run cost and how well it did: USD, tokens, cache and model latency per snapshot, alerts and reports per day, texts by author, live noise, the latest stored evaluation and the duration of each run. It reads the registry, the traces, the evaluator's summary files and the run reports. It never evaluates, prices, calls the model or writes anything.

## Scope
- **In:**
  - new code: `dashboard/metrics.py` (pure builder), `dashboard/panels.py` (eval and run-report reading), `/api/metrics`, `/metricas`, `src/frontend/{metricas.html, metrics.js}`, the "Métricas ↗" link in both 014 pages;
  - `evaluation/summary_file.py` (new leaf: stored model, reader, JSON writer); `EvalSummary.deliverables`; `run_eval` stores the resolved registry path;
  - `telemetry/run_report.py`: the run-report model moved from `runner/summary.py`, plus `read_report`; `STAMP_FORMAT`, `TRACE_NAME` and `ISO_Z_FORMAT` in `telemetry/trace.py`;
  - shared helpers: `source.lines_as_of`, `day_label`, `deliverables_as_of`, `author_of`, `day_lookup`; `heldout.json_shown`.
- **Out:** new accuracy metrics or ratios (Q-106), running the evaluator, comparing runs or several `OUTPUT_DIR`s (Q-112), hook blocks per day and `prefix_hash` changes (Q-109), a registry fingerprint (Q-117), any new setting, library or build step.

## Decisions (interface choices of the spec writer; see plan)
- **I1** Own endpoint and page; `/api/state` and `/api/agents` payloads do not change.
- **I2** Python builds every rule-bearing value; the JS only maps given numbers to SVG geometry.
- **I3** `source.lines_as_of` is extracted from `cost_as_of` and used by both; the cumulative sums the same `totals.usd` field as Planta (R3).
- **I4** File I/O for the fixed panels lives in `dashboard/panels.py`; `dashboard/metrics.py` is pure.
- **I5** The run-report model moves to `telemetry/run_report.py` (Q-108 option A); `runner/summary.py` re-exports only what its code and the 012 tests import; `runner/cli.py` imports the new home.
- **I6** `heldout.json_shown` scans every string of decoded JSON for refused id tokens; `line_shown`, eval files and run reports use it.
- **I7** A position with no trace line has `null` per-snapshot values, never 0; a line with no call has zeros.
- **I8** An unparseable eval or run-report file is skipped and counted (`unreadable`), never fails the endpoint, and no message carries a stored value.
- **I9** A `RunOutput` failure degrades only the noise panel (R9), never a 500.
- **I10** The eval writer and `write_report` write `.<random>.tmp` in the target directory (matching neither `eval-*.json` nor `run-*.json`), then `os.replace`, through a private helper in each owning layer (`evaluation`, `telemetry` may not import `notify`).
- **I11** `source.deliverables_as_of`, `author_of`, `day_lookup` are shared by `state.py` and `metrics.py`, so R7 and R8 match Planta by construction.
- **I12** `/api/metrics` ignores `snapshot`; the other routes keep 014's check. A route-to-builder table in `_api` is allowed, not required.
- **I13** `RunItem.status` and `mode` are `Literal`s; `AccuracyPanel` rejects `state="ok"` with no summary.

## Behavior

### R1 · Endpoint and position (Q-102; 014 R3)
- `GET /api/metrics?at=` parses `at` exactly as 014 R3 (absent → `latest`; 1–6 ASCII digits → greatest position ≤ it, or 0; else 400 `dashboard: invalid at`), before any file is read. `snapshot` is ignored (I12).
- The response carries `at`, `latest`, `positions`, `registry` and `trace_error`, as `/api/state` does.
- **Follows `at`:** cost, tokens, cache, latency (R3–R6), days (R7), authors (R8) and noise (R9) count only rows and trace lines of positions ≤ N (014 as-of rule).
- **Fixed:** the accuracy panel (R11) and the runs panel (R13) ignore `at`.

### R2 · Read-only sources (Q-103, Q-112; ADR-0021)
- Registry and traces come from one `load_view` per request (014 R2, R12, R13). Eval files come from `settings.evals_dir` and run reports from `settings.runs_dir`, read afresh per request.
- Nothing is written or created: not `evals_dir`, not `runs_dir`, not the registry. A missing directory is an empty panel. One `OUTPUT_DIR`, no new setting.

### R3 · Cost per snapshot and cumulative (FR-37; Q-107, Q-97)
- One point per shown position p ≤ N, in order, with `seq` and `snapshot_id`. A snapshot's **lines** are its committed line and its aborted lines (014 R12).
- `usd` of a point = `{"investigator", "coordinator"}` from `run_totals(lines).by_agent[agent].usd`, 8-decimal strings. **Display only** (the stacked split): it may differ from the point total by rounding. `null` with no line (I7).
- `cumulative_usd` = a running `Decimal` sum, over points ≤ p, of `run_totals(lines).usd` (the line `totals`, the field Planta's cost sums), formatted only when written. A `null` point adds 0.
- `unplaced_usd` = `run_totals(lines_as_of(view, N)).usd` − the sum over all points. It covers aborted lines of snapshots that never committed and committed lines whose snapshot has no shown position (missing or smaller registry). Below `latest` it is `"0.00000000"` by construction.
- `totals` = `run_totals(lines_as_of(view, N))`: `usd`, `model_calls`, the four token counts, `cache_pct` (R4) and `latency_ms` (R5). Last `cumulative_usd` + `unplaced_usd` = `totals.usd` = `/api/state` `kpis.cost.usd` at the same N, exactly.

### R4 · Tokens and cache share (FR-37, FR-35; Q-107)
- `tokens` of a point = sums over its lines' `totals`: `input`, `output`, `cache_read`, `cache_write_5m`, `cache_write_1h`; `null` with no line.
- `cache_pct` = 100 × cache_read / (input + cache_read + cache_write_5m + cache_write_1h), one decimal (`Decimal` quantize, half-even); `null` when the denominator is 0 (page: `—`). Same formula for `totals`.

### R5 · Model latency (FR-37; Q-108 a, Q-116)
- `latency_ms` of a point = the sum of `latency_ms` over every model call of its lines (coordinator and investigator), aborted attempts included; `null` with no line, 0 for a line with no call.
- `totals.latency_ms` sums the lines of `lines_as_of`, so aborted lines of snapshots that never committed count only in totals at `latest` (as cost, Q-97). Tool-call latency is not counted.

### R6 · Cost states (Q-107; 014 R12, Q-77)
- `cost.state` is `ok`; `thresholds_only` when the view's mode is `thresholds_only` (page: `Sin costo de modelo`); or `trace_error` when the traces are unreadable (014 R12; page: the 014 banner).
- In the last two, `points` is `[]` and `unplaced_usd` and `totals` are `null`. Days (R7) and noise (R9) are unaffected. In a mixed folder (Q-100) untraced snapshots are `null` points.

### R7 · Alerts and reports per day (FR-22, FR-24; Q-109; 014 R4)
- One bucket per day of `day_lookup(calendar)`, in calendar order, labelled with `day_label`. A day with nothing has zeros.
- Over `deliverables_as_of(view, N)`: `alerts` whose `snapshot_id` maps to the day; `reports` whose `turno_id` maps to the day, split into `reports_with_news` (non-empty `novedades`) and `reports_without_news`.
- A deliverable whose snapshot or shift is not in the shown calendar is not bucketed (014 X4).

### R8 · Texts by author (FR-38; Q-109; 014 R7)
`authors` = counts of `agent`, `template` and `unknown` over every alert and every news item of every report in `deliverables_as_of(view, N)`, each from `author_of(view, notice)` (Planta's feed uses the same helper). With `trace_error`, every author is `unknown`. Labels: "Texto del coordinador", "Texto de plantilla", "Autor sin traza".

### R9 · Live noise (FR-39; Q-105, Q-115, Q-33)
- `noise` = `count_noise(RunOutput(alerts, reports))` over `deliverables_as_of(view, N)` in `(seq, idx)` order: `{"state": "ok", "errors", "repeats": [{turno_id, case_id, previous_turno_id}], "duplicate_alerts": [{case_id, alerts}]}`. No golden data; `cases.novelty` is never used (ADR-0011).
- If `RunOutput` raises, `noise` = `{"state": "invalid", "error": "<ErrorClass>"}` with no stored value (I9).
- The page labels it "Ruido en vivo" (as of N, held-out filtered). It may differ from R11's "Ruido evaluado".

### R10 · Evaluation summary file (FR-39; Q-104, Q-114, Q-118; ADR-0011)
- `EvalSummary` gains `deliverables: int | None = None`. `evaluate` sets it to `len(run.alerts) + len(run.reports)`; `to_json` appends `"deliverables"` (null when unset). Other keys unchanged.
- `run_eval` stores `registry` as `str(registry.resolve())` (Q-114).
- `evaluation/summary_file.py` holds `EVAL_NAME`, `StoredSummary`, `read_summary` and `write_summary_json`, the JSON-writing half; `summary.write_summary` delegates to it. It imports nothing from the project but `domain`. Name, bytes (UTF-8, LF, one trailing newline) and the naive-time error stay as 005 E34. The write is atomic (I10).
- `read_summary(path)` parses the fields of R11 and ignores other keys. Older files parse: missing `deliverables` → `None`; missing `causes` (pre-008) → empty counts. A file that does not decode or validate raises `ValueError("<file name> is not a readable evaluation summary")`.

### R11 · Accuracy panel (FR-39; Q-103, Q-104, Q-106, Q-112, Q-115, Q-117)
- **Candidates:** files of `evals_dir` fully matching `EVAL_NAME` (`eval-[0-9]{8}T[0-9]{6}Z\.json`), newest name first, each read with `read_summary`; unreadable ones count in `unreadable` (I8).
- **Match:** `Path(stored.registry).resolve() == settings.registry_path.resolve()`; both sides are resolved so older relative paths still match (X3).
- **Chosen:** the newest match; `earlier` = the number of older matches.
- **Shown, as stored (Q-106):** `file`, `evaluated_at` (name stamp, `YYYY-MM-DDTHH:MM:SSZ`), `capabilities`, `covered_shifts`, per section (`alerts`, `news`, `causes`) `gated` and `not_gated`, `noise_errors` (labelled "Ruido evaluado": whole registry, at eval time), `gating_errors`, `exit_code`, `deliverables`. No ratio is derived.
- **Staleness:** `current_deliverables` = the deliverable count at `latest` **before** the held-out filter (shown + `omitted.notices`). `stale` = `deliverables ≠ current_deliverables` ("Evaluación desactualizada"), or `null` when `deliverables` is missing ("Vigencia: sin dato"). A registry rebuilt at the same path with the same count reads as current (Q-117).
- **States:** `ok`; `none` (no match: "Sin evaluación para este registro", hint `uv run python evals/run_eval.py --registry <registro> --golden evals/golden`); `omitted` (R12).

### R12 · Held-out omission (FR-40; Q-110; 014 R13)
With `HELDOUT_OPEN=false`:
- Registry and trace parts follow 014 R13 through `load_view`.
- **Eval file:** if `json_shown(decoded chosen file, policy)` is false, the state is `omitted` with no summary ("Evaluación omitida: incluye el bloque reservado"). Older matches are not tried (X5).
- **Run reports:** a report whose decoded JSON fails `json_shown` is omitted (its `arrivals`, `aborted_at`, `cause` and `budget_exceeded` may name ids).
- `heldout = {"open", "omitted": {"snapshots", "notices", "trace_lines", "evals", "run_reports"}}`; `evals` is 0 or 1. The banner lists every count > 0. With the guard open every count is 0.

### R13 · Run durations (FR-37; Q-108 b, Q-113)
- `runs.items`: one per `runs_dir` file fully matching `REPORT_NAME` (`run-[0-9]{8}T[0-9]{6}Z\.json`), read with `read_report`: `file`, `mode`, `status` (`ok`, `aborted`, `interrupted`), `started_at` (UTC, `YYYY-MM-DDTHH:MM:SSZ`), `duration_seconds`, as stored. Unreadable files count in `runs.unreadable` (I8).
- **In progress:** a `traces_dir` file fully matching `TRACE_NAME` **has a report** when a file named `run-<same stamp>.json` exists in `runs_dir`, readable or not, shown or omitted. A trace with no report adds `{file: null, mode: "agent", status: "running", started_at: <stamp>, duration_seconds: null}` ("En curso o sin informe", X1).
- Items are ordered by `started_at`.

### R14 · HTTP surface (NFR-06; 014 R14)
014 R14 applies unchanged (GET only, Host check, headers and CSP, ASCII JSON, 503 busy, the two 500 forms). New exact routes: `/metricas` → `metricas.html`, `/metrics.js`, `/api/metrics`; anything else stays 404.

### R15 · Frontend: the Métricas window (Q-101, Q-111; 014 R15)
- Both 014 pages show `<a href="/metricas" target="metricas" rel="noopener">Métricas ↗</a>`; `metricas.html` links back to Planta and Agentes.
- **Following:** fetches `?at=N` for the position Planta broadcasts (014 `BroadcastChannel`). "Seguir en vivo" polls without `at` every 1.5 s, ignoring broadcasts until "Seguir a Planta"; with no broadcast yet, it polls live.
- **Charts:** hand-written SVG through `dom.js` (`createElementNS`), no library: USD bars by agent with the cumulative line, tokens, cache share, latency, days, authors; then noise list, accuracy table, runs table. `null` is a gap, never a 0 bar.
- Every 014 R15 rule extends to both files; no new `.href =` or `window.open(` form.

### R16 · Layers (Q-105, Q-108, Q-118)
- `dashboard` imports what 014 R16 allows plus, from `evaluation`, exactly the **names** `output.RunOutput`, `noise.count_noise`, `noise.NoiseScore`, `summary_file.EVAL_NAME`, `summary_file.StoredSummary` and `summary_file.read_summary`. Importing `dashboard.server` loads no `evaluation.scoring`, `.golden`, `.causes` or `.summary`. It never imports `runner` (`runner/cli.py` imports `dashboard`).
- `evaluation/summary_file.py` imports nothing from the project but `domain`. `telemetry/run_report.py` stays under `telemetry`'s rule (only `domain`). `runner/summary.py` keeps `domain`, `runner`, `telemetry`.

## Worked examples

**Notation.** AGENT_DIR, TH_DIR, RESUMED, `copied`, APP, ST and HOST as in 014.
- **MT(s, q)** = the parsed JSON of `APP(s).handle("GET", "/api/metrics?" + q, HOST)`.
- **CAL** = `Calendar.load` over the incidents `turnos.csv`: T01–T03 on `3/2/2026` (S001–S006), T04–T06 on `3/3/2026` (S007–S012).
- **LN(sid, coord=[…], inv=[…], status, totals_usd)** = a hand-built `TraceLine` whose model calls are `C(usd, latency, in, out, cr, w5, w1)` (omitted counts 0), `totals` summed from them unless `totals_usd` overrides the USD. **MV(rows, lines)** = a `RunView` in agent mode over hand-built rows and lines.
- **EVAL(s, stamp, …)** = `write_summary(EvalSummary(registry=str(s.registry_path), golden="evals/golden", capabilities=frozenset(), covered_shifts=("T05",), alerts=(), news=(), noise=NO_NOISE, deliverables=8, …), s.evals_dir, stamp)`.
- AGENT_DIR calls (investigator / coordinator), 0.0004 USD each: S002 2/0, S004 2/2, S005 0/1, S006 3, S008 4, S010 2/3; S001, S003, S007, S009 have lines with no call; 3,000 input and 200 output tokens per call. AGENT_DIR and TH_DIR each have one run report, `run-20260302T230000Z.json` (1.0 s); AGENT_DIR's trace is `trace-20260302T230000Z.jsonl`.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **Position (R1).** TH_DIR: MT with `""`, `at=5`, `at=0`, `at=99`; then `at=abc`, `at=-1`, `at=1234567`, and `at=-1` while a write lock is held (014 E24 setup) | `at`/`latest`: 12/12, 5/12, 0/12, 12/12. At 0 every day bucket is zeros and `noise.errors` 0. The last four: 400 `{"error": "dashboard: invalid at"}`. |
| E2 | **Cost per snapshot (R3; FR-37).** AGENT_DIR, MT `at=5` and `at=10` | At 5, points (inv, coord, cumulative): S001 (0, 0, 0); S002 ("0.00080000", 0, "0.00080000"); S003 (0, 0, "0.00080000"); S004 ("0.00080000", "0.00080000", "0.00240000"); S005 (0, "0.00040000", "0.00280000"); zeros are `"0.00000000"`. `totals.usd` "0.00280000" = ST(`at=5`) `kpis.cost.usd`; `model_calls` 7. At 10: S010 ("0.00080000", "0.00120000"); last `cumulative_usd` = `totals.usd` = "0.00760000"; `unplaced_usd` "0.00000000". S006/S008 per-agent split not asserted. S004 `tokens`: input 12000, output 800, cache 0, `cache_pct` "0.0". S001 tokens all 0, `cache_pct` null. |
| E3 | **Tokens, cache share, missing line (R3, R4; I7).** MV: S001–S004 (seq 1–4); LN(S001) with no call; no S002 line; LN(S003, coord=[C(0.0001, 0, 1000, 100, 3000)]); LN(S004, inv=[C(0.0002, 0, 500, 50, 0, 1500)]). Built at 4 and 2 | At 4: S001 `usd` {0, 0}, tokens 0, `cache_pct` null. S002 `usd`, `tokens`, `cache_pct`, `latency_ms` null, `cumulative_usd` "0.00000000". S003 coord "0.00010000", `cache_pct` "75.0". S004 inv "0.00020000", `cache_write_5m` 1500, `cache_pct` "0.0". `totals`: input 1500, output 150, cache_read 3000, cache_write_5m 1500, cache_write_1h 0, `cache_pct` "50.0", usd "0.00030000". At 2: `totals.cache_pct` null. |
| E4 | **Aborted and unplaced lines (R3; Q-97).** A copy of AGENT_DIR plus `trace-20260303T000000Z.jsonl` with two aborted lines, one coordinator call of 0.0004 each: S004, and S011 (not processed). MT `at=10` and `at=9` | At 10: S004 ("0.00080000", "0.00120000"); no S011 point; last `cumulative_usd` "0.00800000"; `unplaced_usd` "0.00040000"; `totals.usd` = ST `kpis.cost.usd` = "0.00840000". At 9: `unplaced_usd` "0.00000000"; last `cumulative_usd` = `totals.usd` = ST(`at=9`) cost = "0.00600000". |
| E5 | **Latency (R5; Q-116).** MV: S001–S003; LN(S001, coord=[C(…, 1200), C(…, 800)], inv=[C(…, 500)]); LN(S001, coord=[C(…, 300)], status=aborted); LN(S002) with no call; no S003 line | `latency_ms`: 2800, 0, null. `totals.latency_ms` 2800. |
| E6 | **Cost states (R6).** (a) TH_DIR, MT; (b) 014 E13(b)'s copy (a broken `trace-20260301T000000Z.jsonl`) | (a) `cost` = `{"state": "thresholds_only", "points": [], "unplaced_usd": null, "totals": null}`. (b) `state` `trace_error`, `trace_error` `traces: trace-20260301T000000Z.jsonl is not a readable trace file`, `points` [], `totals` null; `days` equal the intact copy's; every author `unknown`. |
| E7 | **Days (R7).** (a) AGENT_DIR, MT `at=10` and `at=5`. (b) MV over CAL: report T01 at S002 (seq 2, no news), report T02 at S004 (seq 4, 1 news), alert at S005 (seq 5), report T04 at S008 (seq 8, 2 news); built at 8 and 4 | (a) At 10: `3/2/2026` alerts 1, reports 3; `3/3/2026` alerts 2, reports 2. At 5: `3/2/2026` alerts 1, reports 2; `3/3/2026` zeros. (b) At 8: `3/2/2026` alerts 1, reports 2, with news 1, without 1; `3/3/2026` alerts 0, reports 1, with news 1, without 0. At 4: `3/2/2026` alerts 0, reports 2, with 1, without 1. |
| E8 | **Authors (R8; Q-77, Q-100).** (a) AGENT_DIR at 10 gives counts A; (b) 014 E6(c)'s copy (S010 line removed) at 10; (c) TH_DIR at 12 | (b) `agent` = A.agent − 4, `unknown` = A.unknown + 4, `template` = A.template. (c) `agent` 0, `unknown` 0, `template` = ST `kpis.alerts` + the news items of the feed's reports. |
| E9 | **Live noise as of N (R9; Q-33).** MV, S001–S005: report T01 at S002 with `casos_activos` [S001-Pickup-Local, `en_seguimiento`, `media`]; `alert_notice(S003, S003-SUV-Europa)` (seq 3); report T02 at S004 with the news S001-Pickup-Local (`en_seguimiento`, `media`, max `media`); `alert_notice(S005, S003-SUV-Europa)` (seq 5) | At 3: `state` ok, `errors` 0, `repeats` [], `duplicate_alerts` []. At 5: `errors` 1, `repeats` [{T02, S001-Pickup-Local, T01}], `duplicate_alerts` [{S003-SUV-Europa, 2}]. |
| E10 | **Summary file (R10; Q-114, Q-118).** 005 E32's summary (1 alert, 2 reports); the same file with `deliverables` and `causes` removed; `eval-20261107T120000Z.json` holding `{`; an `EvalSummary` without `deliverables`; `run_eval` over 005 E37's fixture with a relative `--registry` and cwd `tmp_path` | `to_json()["deliverables"]` 3. `read_summary(write_summary(…))`: `deliverables` 3, `capabilities` [], `covered_shifts` [T01, T02], `news.gated["missing"]` 1, `gating_errors` 1, `exit_code` 1. Old file: `deliverables` None, `causes` empty. Broken: `ValueError` `eval-20261107T120000Z.json is not a readable evaluation summary`. No field: `deliverables` null. `run_eval`: stored `registry` = `str((tmp_path / <rel>).resolve())`. After every write the directory holds only `eval-*.json` names. |
| E11 | **Eval selection (R11).** A copy of AGENT_DIR (8 deliverables at `latest`). `evals_dir`: EVAL at 2026-03-03T10:00Z; EVAL at 12:00Z; EVAL at 13:00Z with `registry` = `<out>/evals/smoke-1/registry.sqlite3`; `eval-20260303T140000Z.json` holding `{broken`; `notes.json` holding `{}`. MT, and MT `at=3` | `accuracy.state` ok, `file` `eval-20260303T120000Z.json`, `evaluated_at` `2026-03-03T12:00:00Z`, `earlier` 1, `unreadable` 1, `deliverables` 8, `current_deliverables` 8, `stale` false, `covered_shifts` [T05]. Same panel at `at=3`. |
| E12 | **Staleness and none (R11).** Copies of AGENT_DIR with: (a) one EVAL `deliverables=7`; (b) one EVAL without the `deliverables` key; (c) no `evals_dir`; (d) one EVAL with `registry="out/registry.sqlite3"`, cwd = the copy's parent | (a) `stale` true. (b) `stale` null, `deliverables` null. (c) `state` none, `summary` null, `earlier` 0, `unreadable` 0. (d) `state` ok. |
| E13 | **Held-out eval and staleness (R11, R12; Q-110).** A TH_DIR copy, `heldout_open=False` (first shift T06): EVAL `covered_shifts=("T06",)`; then EVAL `("T05",)` with `deliverables` = D, the count of `read_deliverables` over the whole registry; then the first with the guard open | T06 closed: `state` omitted, `summary` null, `omitted.evals` 1, no body contains `T06`. T05: `omitted.notices` > 0, `current_deliverables` = D = shown + `omitted.notices`, `stale` false, `evals` 0. Guard open: `state` ok, every count 0. |
| E14 | **Runs (R13; Q-108).** (a) AGENT_DIR, MT and MT `at=3`; (b) RESUMED; (c) AGENT_DIR copy with `runs/` deleted; (d) TH_DIR copy with `runs/` deleted | (a) `items` [{`run-20260302T230000Z.json`, agent, ok, `2026-03-02T23:00:00Z`, 1.0}], equal at `at=3`. (b) `aborted` at `2026-03-02T23:00:00Z`, then `ok` at `2026-03-02T23:30:00Z`, each 1.0. (c) one item {null, agent, `running`, `2026-03-02T23:00:00Z`, null}. (d) `items` []. |
| E15 | **Run reports: held-out, unreadable (R12, R13; I8).** (a) TH_DIR copy, `heldout_open=False` (first shift T06); (b) AGENT_DIR copy plus `runs/run-20260301T000000Z.json` holding `{` | (a) `items` [] (`arrivals.processed` names S011, S012), `omitted.run_reports` 1. (b) `unreadable` 1; the real report is still listed. |
| E16 | **Run-report reader (R13; I5, I10).** 012's report fixture written with `write_report(report, p)` | `read_report(p) == report`; `runs/` holds only `p`. 012's tests pass unchanged. |
| E17 | **Held-out, registry part (R12, R7).** TH_DIR copy, `heldout_open=False` (first shift T06), MT | `latest` 10. `days` [`3/2/2026`, `3/3/2026`]; `3/3/2026` counts only T04, T05. `omitted.snapshots` 2, `omitted.notices` = ST's. No body contains `S011`, `S012` or `T06`. |
| E18 | **HTTP (R14; I12).** APP(TH_DIR).handle: GET `/metricas`, `/metrics.js?x=1`; `/metricas.html`, `/metrics.js/`, `/metricas/`; POST `/api/metrics`; GET `/api/metrics` with Host `evil.example:8765`; with a write lock held; on 014 E16's `not sqlite` copy; with `build_metrics` raising `ValueError("secret S011")`; GET `/api/metrics?snapshot=../x` | 200 `text/html; charset=utf-8` and `text/javascript; charset=utf-8`. 404 ×3, 405 `Allow: GET`, 403, 503 `dashboard: registry busy`, 500 `dashboard: registry.sqlite3 is not a readable registry (DatabaseError)`, 500 `dashboard: view failed (ValueError)`. `snapshot=../x`: 200, same body as with no query. Every response has 014 R14's three headers with the exact CSP. |
| E19 | **Risk: frontend assets (R15).** `ASSETS`; the asset scan; `metricas.html`; `index.html`, `agentes.html`; `from_settings` with no `metrics.js` | Both assets exist at `FRONTEND_DIR`, with no forbidden sink or remote URL. `metricas.html` loads only `/app.css`, `/dom.js`, `/metrics.js`; no inline script, `<style>`, `style=` or `on…=`. Both 014 pages contain `href="/metricas" target="metricas"`. Missing file: `ValueError` `dashboard: frontend asset not found: metrics.js`. |
| E20 | **Risk: imports (R16; Q-118).** Boundary scan; a subprocess import | `dashboard/*` imports from `evaluation` only the six R16 names, and never `runner`. Importing `plant_monitor.dashboard.server` (`loaded_by_import`) loads none of `plant_monitor.evaluation.{scoring,golden,causes,summary}`. `evaluation/summary_file.py` imports nothing from the project but `domain`. `telemetry/run_report.py`: the existing `test_e22_telemetry_imports_only_domain_and_is_sdk_free`, no new test. Only `runner/cli.py` imports `dashboard`. |
| E21 | **Cumulative = Planta by arithmetic (R3, R5; F1).** MV: S001–S002 (seq 1–2); LN(S001, coord=[C(0.00000003, 100), C(0.00000003, 200)], totals_usd=0.00000007); LN(S002, inv=[C(0.0001, 300)]); committed LN(S003, coord=[C(0.0002, 400)]) with no position. Built at 2 and 1 | At 2: S001 `usd.coordinator` "0.00000006", `cumulative_usd` "0.00000007"; S002 "0.00010007"; `unplaced_usd` "0.00020000"; `totals.usd` "0.00030007" = `cost_as_of(view, 2).usd`; `totals.latency_ms` 1000. At 1: `cumulative_usd` "0.00000007", `unplaced_usd` "0.00000000", `totals.usd` "0.00000007" = `cost_as_of(view, 1).usd`, `latency_ms` 300. |
| E22 | **Run-in-progress pairing (R13; F3).** (a) AGENT_DIR copy, `heldout_open=False` (first shift T05; the report's `arrivals.processed` names S009, S010); (b) AGENT_DIR copy whose `run-20260302T230000Z.json` holds `{` | (a) `items` [], `omitted.run_reports` 1. (b) `items` [], `unreadable` 1. No `running` item in either. |
| E23 | **Invalid run output (R9; I9).** MV, S001–S003: report T01 at S002 (seq 2) and a second report T01 at S003 (seq 3). Built at 3 and 2 | At 3: `noise` = `{"state": "invalid", "error": "ValidationError"}`; `days` and `authors` built as usual; no 500. At 2: `noise.state` ok, `errors` 0. |
| E24 | **Risk: no write (R2; 014 E17).** TH_DIR copy with `runs/` deleted and no `evals/`; APP.handle GET `/api/metrics` and `?at=3`; then APP over an `OUTPUT_DIR` that does not exist | 200 ×2. Registry bytes and the path set under `OUTPUT_DIR` unchanged (no `-journal`, `-wal`); `runs_dir` and `evals_dir` not created. Missing dir: 200, `registry` "missing", `latest` 0, not created. |

## Edge cases and assumptions
- **X1** · (Q-113) A run killed before writing its report keeps a trace with no report and shows "En curso o sin informe" forever. Not detected as running: a threshold-only run, an agent run before its first trace line, and a run whose snapshots were all skipped (none writes a trace file).
- **X2** · The panels re-read `evals_dir` and `runs_dir` on every poll (about 2 requests/s with three windows). A few small JSON files, so no cache (014 X5).
- **X3** · Files written before Q-114 store `--registry` as given; a relative one matches only when the dashboard runs from the same working directory (E12 d).
- **X4** · With the guard closed, noise compares consecutive *shown* reports. Held-out shifts are the last ones (T22 on), so no gap opens between two shown reports.
- **X5** · A held-out eval hides the panel even when an older allowed eval exists: an older file shown as "the" evaluation would mislead.
- **X6** · (Q-117) A registry rebuilt at the same path with the same deliverable count reads as current; no fingerprint.

## Acceptance
- [ ] E1–E24 pass on synthetic fixtures; CI never calls the model and opens no outside network (NFR-07). Every new test cites its spec id.
- [ ] **Changed expectations (not removed):**
  - `tests/unit/test_import_boundaries.py`: `DASHBOARD_ALLOWED` adds the six R16 names (name-level, not modules); the test is re-cited 014 E22 → 015 E20. New tests there: the import probe and the `summary_file` rule;
  - `tests/unit/dashboard/test_frontend_assets.py`: the HTML-page check is parametrized over `metricas.html` too;
  - `tests/integration/test_dashboard_http.py`: `ASSET_NAMES` adds `metricas.html` and `metrics.js`; E1's invalid-`at` parametrization adds `/api/metrics`.
- [ ] Specs 001–014 tests pass unchanged otherwise (helpers and `state.py` refactor, `json_shown`, run-report move, writer split, atomic writes).
- [ ] Docs (README, STRUCTURE, roadmap, ADR-0022 index), `visual-designer` pass, manual review with the user's permission (tasks T10, T12, T13).
- [ ] `ruff`, `mypy --strict` and `pytest --cov` pass.

## Size
About 25 KB, over the 20 KB aim: three data sources (traces, eval files, run reports) each need their own held-out, unreadable-file and atomic-write rule, plus four design-review examples. Splitting the fixed panels out would ship a window without the accuracy FR-39 asks for.
