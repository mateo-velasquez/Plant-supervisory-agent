# 014 · Live dashboard with replay — Spec

- **Status:** Implemented (T14 pending: real-run review, with permission)
- **Requirements:** FR-22, FR-23, FR-25, FR-31, FR-37, FR-38, FR-40, FR-20, NFR-06, NFR-07, NFR-09
- **Stories:** US-05, US-06, US-09, US-10
- **Decisions:** ADR-0021 (rewritten in place: local read-only live dashboard with replay). Q-84–Q-100 decided by the user. Reused unchanged: Q-14, Q-37, Q-65, Q-76, Q-77, Q-79.
- **Week:** Stretch · **Priority:** Could

## Goal
A local web dashboard, served by `uv run plant-monitor dashboard`, that shows a run while it writes (live) and plays a run back snapshot by snapshot (replay). It has two windows: **Planta** (cases, alerts, reports, cost) and **Agentes** (what code, investigator and coordinator did per snapshot). It shows only what the run stored. It never computes a metric, calls the model or writes a file.

## Scope
- **In:**
  - new code: `src/plant_monitor/dashboard/` (read model, held-out filter, HTTP handler, server), `src/frontend/` (HTML, CSS, JS assets), `cases/registry/run_reader.py`, `domain/verbatim.verbatim_spans`, `Settings.dashboard_port`, `plant-monitor dashboard` in `runner/cli.py`;
  - shared registry helpers: `cases/registry/readonly.py` (`open_readonly`, `check_columns`) and `notices.is_deliverable`;
  - shared trace helpers: `telemetry/trace.index_attempts` / `text_by` (moved from `trace_query`) and `read_trace_files(drop_partial_tail=)`;
  - the removal of the static HTML design on this branch.
- **Out:** React or any framework or library, a build step, light mode, auth, network exposure, any write, the model, the prototype's fake-model demo, analytics and accuracy (spec 015), the held-out run itself.

## Decisions (interface choices of the spec writer; see plan)
- **I1** Replay is client-owned: the server is stateless, and each read endpoint takes an optional `at=<seq>`. Planta owns play/pause/speed and broadcasts its position to Agentes over `BroadcastChannel` (same origin, no network). A server-held position would need a write endpoint, so it is rejected.
- **I2** Python builds everything rule-bearing: the as-of filter, KPIs, cells, feed authors, conversation events in order, logbook segments with marks, and hook translations. The JS only lays out the JSON. So every rule is tested by pytest, and the JS is not.
- **I3** SQL lives in `cases/registry/run_reader.py` (`read_run_rows`), which reads every table in one transaction. `read_run_rows`, `read_deliverables` and `notice_reader` share `open_readonly` and `check_columns`. Deliverables are taken from `RunRows.notices` with `is_deliverable`, which agrees with `DELIVERABLE_FILTER`, so they come from the same snapshot of the file. The dashboard never opens SQLite itself.
- **I4** 013's `_pick` and `_text_by` move to `telemetry/trace.py`, together with `CorruptTraces` and `TextBy`. `_pick` becomes `index_attempts(files) -> (committed, aborted)`, which raises on the first duplicate committed line in file order. `trace_query` imports them; 013's expectations are unchanged.
- **I5** The held-out helpers move from `notify/html.py` to `dashboard/heldout.py`: the id patterns, `validate_ids`, `shown_ids`, `select_shown` and `UnsafeId`. Trace lines are filtered by an id-token scan (R13).
- **I6** JSON is written with `ensure_ascii=True`, so a body is always ASCII, even for a lone surrogate. USD values are strings with 8 decimals, as stored. Payloads are `TypedDict`s.
- **I7** Error bodies and messages name a file, a parameter or an exception class, never a stored value.
- **I8** `CliDeps.serve(app, port, on_ready)` is a seam, so the CLI is tested without blocking. `DashboardApp` is a plain constructor over its collaborators, with `from_settings` as the factory.

## Behavior

### R1 · Command and settings (Q-85; ADR-0018)
- `plant-monitor dashboard` takes no arguments. `--help` exits 0, and an extra argument is an argparse error (2).
- Startup, in order:
  1. settings;
  2. `turnos.csv` and `HeldOutPolicy` (as `run`);
  3. `load_plan` for the combinations;
  4. the `LogbookStore`;
  5. the frontend assets (R15).
- A failure in any step exits 2 with one stderr line through `_fail`, which writes through `write_safe`.
- The server then binds `127.0.0.1:<settings.dashboard_port>`. A bind `OSError` exits 2 with `dashboard: cannot listen on 127.0.0.1:<port> (<ErrorClass>)`, and no URL line is printed.
- Once bound, `on_ready(<bound port>)` writes `dashboard: http://127.0.0.1:<bound port>/ (Ctrl+C to stop)` to stdout, and then the server starts serving. Ctrl+C stops the server and exits 0.
- `DASHBOARD_PORT` (int, 1–65535, default 8765) is read through `Settings`.
- The command never builds the model, `SqliteRegistry` or the pipelines, never checks the API key, and logs no request lines.

### R2 · Read-only sources (ADR-0002, ADR-0019; Q-84)
- The registry is read only through `read_run_rows(settings.registry_path)`: `mode=ro`, a busy timeout, one read transaction, a per-table column check. A missing file gives `registry: "missing"` and empty views, and the file is never created.
- A lock that outlasts the timeout gives 503 `{"error": "dashboard: registry busy"}`. The client keeps its last good payload and shows `Registro ocupado, reintentando`. A lock is never reported as corruption.
- Traces come from `settings.traces_dir` (R12), logbooks through the `LogbookStore` (R10), and plant files once at startup.
- Nothing is written anywhere: the registry bytes and the set of paths under `OUTPUT_DIR` are unchanged. Stored items are shown as stored, never copied with new values (no `model_copy`).

### R3 · Position: live and replay (Q-90; I1)
- **Positions** are the shown `processed_snapshots.seq` values in ascending order (contiguous from 1 unless R13 omits some). `latest` is the greatest of them, or 0 when there is none.
- `at` on `/api/state` and `/api/agents`:
  - absent → `latest`;
  - an ASCII integer with 1–6 digits → the greatest position ≤ it, or 0;
  - anything else (sign, letters, more than 6 digits) → 400 `{"error": "dashboard: invalid at"}`.
  - The response carries the effective `at` and `latest`.
- **As of N:** every view counts only rows with `seq ≤ N`. That covers the processed snapshots, `case_history` rows, notice rows (deliverables and per-case decisions), and the trace lines (committed or aborted) of snapshots whose seq ≤ N. `at=0` shows an empty plant: every cell is calm, and the feed and the snapshot list are empty.
- **Live** (client): poll without `at` every 1.5 s and follow `latest`. **Replay** (client): position N with ▶/⏸, step −1/+1, a slider over the positions, and speeds 1×, 2×, 4×, 8× (2 s, 1 s, 0.5 s, 0.25 s per snapshot). Each step fetches `?at=N`, and playback stops at `latest`. Agentes follows the broadcast position unless the user pins a snapshot; "Seguir en vivo" unpins it.

### R4 · Header and timeline (FR-22; Q-89)
- **Header:** `Snapshot <id> · <N> de <total>`, where `total` = 2 × the shown shifts of `turnos.csv`. Then the shift of that snapshot (`turno_id`, `turno`, `HH:MM–HH:MM`), its `fecha`, and the mode (`En vivo` / `Repetición`). `Serie completa` is shown when the shown position is the last snapshot (`at == total`, field `complete`). When `at=0` the header says `Sin snapshots procesados`.
- **Timeline:** shifts in calendar order, grouped by day (`fecha`, or the date of `inicio` when `fecha` is empty). Each day holds its shifts, and each shift holds two snapshot cells (mid, closing). A cell shows `processed` (`seq ≤ N`), the number of immediate alerts stored at that snapshot with `seq ≤ N`, and `report` (a shift report stored there with `seq ≤ N`). The cell of N is the current one. With 30 shifts this gives 10 day groups of 6 cells that wrap by day.

### R5 · Planta KPIs (FR-21, FR-22, FR-37)
As of N:
- **Casos activos**: combinations whose case is active (R6), "de <k> combinaciones".
- **Críticos**: active cases with effective severity `critica`, listed as `Modelo × Mercado`.
- **Alertas inmediatas**: `alerta_inmediata` rows.
- **Informes de turno**: report rows, "de <shown shifts> turnos".
- **Costo del modelo**: `run_totals` over the trace lines as of N, committed and aborted. At N = `latest` it also counts aborted lines of snapshots that never committed, so it equals the run summary (Q-97). It shows `usd`, `model_calls` and tokens = input + output. The dashboard never prices anything. If the traces are unreadable (R12), the cost is `null` and shows `—`.

### R6 · Model × market matrix (FR-12–FR-14, FR-16, FR-23)
- Rows are models and columns are markets, taken from `load_plan` and ordered as `all_combinations()`. There is one cell per combination.
- A combination's **case as of N** is its case (from `cases`) whose newest `case_history` row with `seq ≤ N` has the greatest seq. If two cases tie on that seq, the one with the later `opened_at` position wins, and at most one of them may be active (FR-12). The view raises if two tied cases are both active or also share that `opened_at` position (the pick would be arbitrary); the server answers 500 `dashboard: view failed (ValueError)`. That row gives `estado`, effective severity, `gap_unidades`, `gap_pct`, `retraso_dias` and `etapa_cuello`. `opened_at` comes from `cases`.
- **Status:**
  - `calm` when there is no such row ("Sin caso · Sin casos hasta este snapshot": a deviation below the thresholds opens no case, so the cell never claims the combination is on plan);
  - `resolved` when the row's state is `resuelto` (`resolved_at` = that row's snapshot);
  - `active` otherwise.
- **Cause as of N:** `causa` (`categoria`, `etapa`) of the newest notice row of that case (any `tipo`) with `seq ≤ N`, or, when there is none, `no_declarada` with the stage the data show: that history row's `etapa_cuello` (FR-18, criterio §6, as `default_cause` does in the run). It is never taken from the current `case_causes` row, which is overwritten over time.
- **Sparkline:** one point per position ≤ N, holding the combination's `gap_units` at that seq, or `null` when the combination had no history row there. A missing point is never drawn as 0.

### R7 · Activity feed (FR-22, FR-25, FR-38; Q-89)
- Deliverables (`is_deliverable` rows of `RunRows.notices`: alerts and shift reports) with `seq ≤ N`, newest first, in reversed `(seq, idx)` order.
- An **alert** item shows `texto` directly, `case_id`, `Modelo × Mercado`, `severidad`, `snapshot_id` and an **author** badge.
- A **report** item shows `turno_id`, the closing `snapshot_id`, and either each news item's `texto` with its own author badge or `Sin novedades en este turno` (Q-99), plus the count of active cases.
- **Author** comes from `text_by(notice_id, committed line of its snapshot, mode)`. The mode is `thresholds_only` when there is no trace file (013 Q-77). `agent` shows as "Texto del coordinador", `template` as "Texto de plantilla", and `unknown` as "Autor sin traza". In a mixed folder (a threshold-only start resumed in agent mode), the untraced snapshots show "Autor sin traza" (Q-100).
- **Details** (collapsed): `motivo`, `origen`, `causa` and `etapa`, `severidad_maxima`, `estado`, and the evidence (fragment plus `Bitácora <bitacora>`). A report's details also hold its `casos_activos` table as stored.
- **Link** "Ver agentes" opens `/agentes#<snapshot_id>` in the window named `agentes`, which pins that snapshot.

### R8 · Agentes: snapshot list and KPIs (FR-28, FR-31, FR-37; Q-89, Q-94)
- **List:** every shown processed snapshot with `seq ≤ N`, newest first. Each entry has `snapshot_id`, `turno_id`, `agents` (`TraceLine.ran` of the committed line), `hook_blocks` (`len(hooks)`), `model_calls`, `usd` (that line's `totals.usd`), `previous_attempts` (aborted lines of that snapshot, R12) and `traced` (a committed line exists). If `agents` is empty the entry says `Solo código`, and if `traced` is false it says `Sin traza`.
- **KPIs:** snapshots whose committed line ran the investigator; the same for the coordinator; the sum of `hook_blocks`; and the cost as in R5.
- **Selected:** the `snapshot` parameter (`S[0-9]{3}`, else 400 `dashboard: invalid snapshot`). If it is absent, the newest entry is selected. A valid id that is not listed (unknown, held out, or later than N) gives `selected: null`, the same response in every case.

### R9 · Agentes: conversation (FR-17, FR-20, FR-28, FR-31; Q-93)
For the committed line of the selected snapshot, `events` come in this order, each with a `lane` (`code`, `investigator`, `coordinator`):
1. `decision` (code): `decision`, `decision_reason`, number of `required`, agents run.
2. If the investigator ran: `thinking` (only when it has a non-empty text); then turn by turn: its `pre_tool` hook blocks, its tool calls (`get_logbook` → `logbook_read`, R10; any other → `tool_call`), its `on_stop` hook blocks; then one `control_error` per entry (code lane); then one `proposal` per stored proposal, or `no_proposals`; then `agent_cost` (calls, usd from `run_totals([line]).by_agent`).
3. `validation` (code), when `proposals_applied` or `proposals_declined` is non-empty.
4. If the coordinator ran: `thinking` (non-empty only); turns as in step 2, where `apply_proposal`, `emit_alert` and `emit_shift_report` carry their arguments' proposal id, `case_id` and `texto` values as stored; then `agent_cost`.
5. `registration` (code), when `notices_agent`, `notices_template` or `report_id` is non-empty: both counts and `report_id`.

A hook block is a `hook_block` event in the code lane, carrying the blocked agent. A tool call with `is_error` whose agent, turn and name match a hook block is shown only as that block. The header shows `previous_attempts` as "N intentos previos" when N > 0.

### R10 · Logbook text with highlights (FR-17, FR-20, FR-40; Q-93)
- A `logbook_read` loads its text with `LogbookStore.get(turno_id, line.snapshot_id)`, so the held-out guard and the shift-close availability rule apply. On a `RejectedRequest`, or a `turno_id` that is not a string matching `T[0-9]{2}`, the event has `logbook: null` and the note `no disponible`.
- `segments` cover the whole text in order: `[{"text", "mark"}]`. Marked spans are the `verbatim_spans` (whitespace-tolerant, case-sensitive, Q-36) of each `fragmento` of that line's investigator proposals citing that `turno_id`. Overlapping or touching spans are merged.
- Logbook text is data. It reaches the DOM only as text nodes (R15).

### R11 · Hook reasons in plain Spanish (FR-31; Q-93)
`explain_hook(hook) -> str | None` maps a stored reason that fully matches a known pattern (plan table: allowlist, novelty, cause, text floor) to a Spanish sentence, and returns `None` otherwise. The event carries both `reason` (raw, always shown) and `reason_es`.

### R12 · Trace files and attempts (Q-94; 013 R7)
- `trace-*.jsonl` files are read with `read_trace_files(dir, drop_partial_tail=True)`, in name order. A trailing segment without a final `\n` (a line being written) is ignored. Any other line that does not validate as `TraceLine`, or a duplicate committed line for one snapshot (`index_attempts`, the first duplicate in file order), sets `trace_error`. The message is one line with no stored values: `traces: <file> is not a readable trace file` or `traces: two committed lines for <snapshot_id> (<file>, <file>)`.
- With `trace_error`, Planta keeps its registry views (cells, feed, timeline, counts) and shows the error banner. The cost is `null`, authors are `unknown`, and Agentes lists snapshots with `traced: false` and `selected.events = []`.
- The committed line is shown, and aborted lines are counted (`previous_attempts`). Aborted lines of a snapshot that never committed have no position and are not shown; they count only in the cost at `latest` (R5, Q-97).

### R13 · Held-out omission (FR-40; Q-91)
With `HELDOUT_OPEN=false` and the policy from `turnos.csv`:
- **Processed snapshots**: omitted when refused, or when they fail `S[0-9]{3}`.
- **Deliverables**: `select_shown` (014 rule). An item is omitted whole when any snapshot or shift id it shows is refused (`snapshot_id`, every `case_id` prefix, `turno_id`, every evidence `bitacora`), or when `validate_ids` fails.
- **`cases` rows**: omitted when `case_snapshot_id(case_id)` or `opened_at` is refused, or fails `S[0-9]{3}`.
- **Per-case decision notices and `case_history` rows**: omitted when their `snapshot_id` or `case_id` prefix is refused or fails its pattern (the evidence `bitacora`s too, for notices).
- **Trace lines**: omitted when `snapshot_id` fails `S[0-9]{3}`, `turno_id` fails `T[0-9]{2}`, or the line's JSON holds a token `\bS[0-9]{3}\b` or `\bT[0-9]{2}\b` that is refused.
- **Calendar**: refused shifts are dropped from the timeline and from `total`.
- `heldout = {"open": false, "omitted": {"snapshots": a, "notices": b, "trace_lines": c}}` counts the omitted processed snapshots, deliverables and trace lines. The page shows `Bloque reservado cerrado: se omitieron a snapshots, b avisos y c líneas de traza` when any count is > 0.
- With the guard open nothing is omitted and every count is 0.

### R14 · HTTP surface (NFR-06; Q-88)
- **GET only.** POST, PUT, DELETE, PATCH and HEAD → 405 with `Allow: GET`.
- **Routes** (exact path, query ignored for static files):
  - `/` → `index.html`, `/agentes` → `agentes.html`;
  - `/app.css`, `/dom.js`, `/app.js`, `/agents.js`;
  - `/api/state`, `/api/agents`.
  - Anything else → 404, including `/index.html`, `/app.js/`, `/../registry.sqlite3`, `/%2e%2e/x` and `/frontend/app.js`.
- **Host check (Q-98):** the host name of the `Host` header, with any port stripped, must be `127.0.0.1` or `localhost`, else 403, before any read. A missing header also gets 403.
- **Parameters before I/O:** `at` and `snapshot` are validated before any file is read, so a bad parameter is 400 even when the registry is locked.
- **Last resort:** any other error while building a view is 500 `dashboard: view failed (<ErrorClass>)` with the headers below; nothing is printed to stderr and no stored value or path reaches the body.
- **Every response:**
  - `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` (Q-88, tightened);
  - `X-Content-Type-Options: nosniff`;
  - `Cache-Control: no-store`.
- **Content types:** `text/html; charset=utf-8`, `text/css; charset=utf-8`, `text/javascript; charset=utf-8`, `application/json` (ASCII body, I6).
- A registry read `ValueError` → 500 `{"error": "dashboard: <registry file name> is not a readable registry (<ErrorClass>)"}`.

### R15 · Frontend (Q-86, Q-87, Q-96)
- The assets are `src/frontend/{index.html, agentes.html, app.css, dom.js, app.js, agents.js}`: hand-written, no framework, no library, no build step, dark theme only, UI text in Spanish.
- The server finds them at `Path(__file__).resolve().parents[2] / "frontend"`.
- Stored values reach the DOM only through `textContent`, `createTextNode`, `setAttribute` on non-URL, non-event attributes, and SVG geometry attributes.
- None of these appears in any asset: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval(`, `new Function`, `setTimeout("`, `setAttribute("on`, `srcdoc` or `http:` / `https:` (the one exception is the SVG namespace string `"http://www.w3.org/2000/svg"` passed to `createElementNS`, which loads nothing). Every `.href =` and `window.open(` takes a string literal or a template whose only interpolation is a snapshot id checked against `^S[0-9]{3}$` (the scan accepts only the two allowed forms listed in the plan).
- HTML files hold no inline `<script>` body, no `<style>`, no `style=` and no `on…=` attribute, so the CSP holds.

### R16 · Layers (STRUCTURE dependency rule)
- `dashboard` imports only `domain`, `cases.registry` (`run_reader`, `notices.is_deliverable`), `telemetry`, `ingestion`, `logbooks` and `config`. It never imports `agents`, `mcp_server`, `hooks`, `runner`, `evaluation`, `anthropic` or `mcp`.
- No module outside `runner/cli.py` imports `dashboard`.
- `cases/registry/run_reader.py` and `cases/registry/readonly.py` import only `domain` and `cases.registry`.

## Worked examples

**Notation.**
- **AGENT_DIR**, **TH_DIR**, `copied` come from `trace_builders` (013): ten agent-mode snapshots with a hook block at S010, and twelve threshold-only snapshots with no trace file.
- **RESUMED** = 013 E5's two runs over `ALL[:5]`: S005 aborts in `trace-20260302T230000Z.jsonl` and commits in `trace-20260302T233000Z.jsonl`.
- **APP(s)** = `DashboardApp.from_settings(s)`.
- **ST(s, q)** / **AG(s, q)** = the parsed JSON of `APP(s).handle("GET", "/api/state?" + q, HOST)` / `"/api/agents?" + q`, with `HOST = "127.0.0.1:8765"`. Before T10, the same payloads come from `build_state` / `build_agents` over `load_view`.
- Calendar of the fixture: T01–T06 close at S002, S004, …, S012. USAGE costs 0.0004 USD per call with PRICES; FakeModel reports no cache tokens.
- AGENT_DIR model calls per snapshot (013 scripts): S002 2, S004 4, S005 1, S006 3, S008 4, S010 5.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **Position (R3).** TH_DIR: ST with `""`, `at=5`, `at=0`, `at=99`, `at=abc`, `at=-1`, `at=1234567` | `at`/`latest`: 12/12, 5/12, 0/12, 12/12. `positions` = 1…12. At 0: `current` null, every cell `calm`, `feed` []. The last three: 400, body `{"error": "dashboard: invalid at"}`. |
| E2 | **Replay as of N (R3, R6, R7; FR-13).** TH_DIR, cell Pickup × Local and feed at `at=9`, `11`, `12` | 9: `calm`, `case` null. 11: `active`, `case_id` S010-Pickup-Local, `estado` en_seguimiento, `opened_at` S010; no feed item has `notice_id` S012-alerta_inmediata-S010-Pickup-Local. 12: `active`, `escalado`, `critica`, `gap_unidades` −11.0, `gap_pct` −36.7 (stored value, rounded by the test to 1 decimal), `etapa_cuello` null, cause `no_declarada`; `series` has 12 points, null for seq 1–9, −11.0 at seq 12; the feed's ids equal `read_deliverables` reversed and include that alert. |
| E3 | **Timeline (R4).** TH_DIR at 11 | 6 shifts T01…T06 in calendar order, grouped by `fecha`; S001–S011 `processed`, S012 not; `report` true exactly at S002, S004, S006, S008, S010; `current.snapshot_id` S011, `current.turno_id` T06; `total` 12; no `Serie completa` (11 < 12). At 12, `complete` is true. |
| E4 | **KPIs and cost (R5; FR-37).** AGENT_DIR at 5 and at 10 | 5: `alerts` 1, `reports` 2, cost `model_calls` 7, `usd` "0.00280000", tokens 22400 (7 × 3,200). 10: `alerts` 3 (S005 SUV × Europa, S010 Pickup × Local, S010 Pickup × Brasil), `reports` 5, cost 19 calls, "0.00760000", 60800 tokens; `critical` includes `Pickup × Local` and `Pickup × Brasil`. |
| E5 | **Cell states and cause as of N (R6; FR-18).** Unit, hand-built rows: case S005-SUV-Europa with history at seq 5 (`escalado`, raised, gap −4.0, `calidad`), 6, 7 (gap 0.0), 8 (`resuelto`, gap 0.0); an alert at seq 5 with `causa` (`retencion_de_calidad`, `calidad`); case S006-Sedán-Local with one history row at seq 6 and no notice row; boundary: case S009-SUV-Europa with a history row at seq 8 in state `abierto` (the same seq as S005-SUV-Europa's `resuelto` row) | SUV × Europa: at 4 `calm`; at 5 `active`, `critica`, cause `retencion_de_calidad`/`calidad`; at 8 without the boundary case `resolved`, `resolved_at` S008, `series` [null, null, null, null, −4.0, …, 0.0]; at 8 with it, `active` S009-SUV-Europa (later `opened_at`). Sedán × Local at 6: `active`, cause `no_declarada` with `etapa` = its history row's `etapa_cuello` (criterio §6). At 5 SUV × Europa also shows the stored `retraso_dias` and `etapa_cuello` `calidad`. |
| E6 | **Feed item and author (R7; Q-77).** (a) AGENT_DIR at 10, the item of S010-alerta_inmediata-S010-Pickup-Local; (b) TH_DIR at 12, the item of S012-alerta_inmediata-S010-Pickup-Local; (c) a copy of AGENT_DIR whose trace file has its S010 line removed | (a) `texto` `Agente: S010-alerta_inmediata-S010-Pickup-Local`, `author` agent, `motivo` [bitacora], `origen` agente, `causa` parada_de_linea/montaje, `evidencia` [(T05, F5)], `snapshot_id` S010. (b) `author` template (no trace file). (c) the same item has `author` unknown. |
| E7 | **Agentes list and KPIs (R8).** AGENT_DIR, AG at 10 | KPIs: investigator 5 (S002, S004, S006, S008, S010), coordinator 5 (S004, S005, S006, S008, S010), `hook_blocks` 1, cost as E4. The list is newest first, S010 to S001. S010: `agents` [investigator, coordinator], `hook_blocks` 1, `model_calls` 5, `usd` "0.00200000". S001, S003, S007, S009: `agents` []. Every entry has `previous_attempts` 0 and `traced` true. |
| E8 | **Conversation order (R9).** AGENT_DIR, AG `snapshot=S010` | `[lane/kind]`: code/decision (`call`, `text_needed`); investigator/logbook_read T05 (turn 1); investigator/proposal S010-p1 (`raise`, `parada_de_linea`, `montaje`, Pickup, `mercado` null, T05); investigator/agent_cost (2, "0.00080000"); code/validation (applied includes S010-p1); coordinator/tool_call apply_proposal S010-p1 (turn 1); code/hook_block (coordinator, `allowlist`, `get_logbook`, turn 2), with no separate tool_call for that `get_logbook`; coordinator/tool_call emit_alert S010-Pickup-Local; emit_alert S010-Pickup-Brasil; emit_shift_report with 2 items (turn 3); coordinator/agent_cost (3, "0.00120000"); code/registration (`agent` 4, `report_id` T05-informe). No `thinking` event. |
| E9 | **Thinking (R9).** Unit: a committed line built with `model_validate`: coordinator `thinking` ["", "Reviso las propuestas."], investigator `thinking` ["Busco la causa en T05."], both agents run | One investigator/thinking event with ["Busco la causa en T05."] before the investigator's first turn. One coordinator/thinking event with ["Reviso las propuestas."] (the empty text dropped) before the coordinator's first turn. A line with only empty texts has no thinking event. |
| E10 | **Segments (R10; Q-36).** Unit: `segments("Turno T05.\nse paró la línea\nde montaje.\nFin.", ["se paró la línea de montaje", "montaje.", "no está"])`; and AGENT_DIR S010's logbook_read | `[("Turno T05.\n", false), ("se paró la línea\nde montaje.", true), ("\nFin.", false)]` (overlapping spans merged, the absent fragment ignored). The joined texts equal the input. AGENT_DIR: the T05 text is the fixture file's text, and exactly one marked segment, whose whitespace-normalized text equals F5. |
| E11 | **Hook reasons (R11).** `explain_hook` of: `tool get_logbook is not allowed for the coordinator`; `S010-Pickup-Local: no news since last report`; `something else` | `El coordinador no tiene permiso para usar get_logbook: cada agente solo usa sus herramientas.`; `S010-Pickup-Local no tiene novedades desde el último informe: el aviso no se repite.`; None. |
| E12 | **Resumed run (R8, R12; Q-94).** RESUMED, AG `snapshot=S005` | The S005 entry has `previous_attempts` 1, and `selected.previous_attempts` 1. Its events come from the committed line (second file). S004 has `previous_attempts` 0. The cost includes the aborted line (013 E5: usd 0 for it). |
| E13 | **Corrupt traces (R12).** Copies of AGENT_DIR: (a) the trace file duplicated as `trace-20260302T235900Z.jsonl`; (b) a file `trace-20260301T000000Z.jsonl` holding `{broken\n`; (c) the trace file with `{"snapshot_id": "S0` appended (no newline) | (a) `trace_error` `traces: two committed lines for S001 (trace-20260302T230000Z.jsonl, trace-20260302T235900Z.jsonl)`; cells and feed as in the intact copy; cost null; every author unknown; AG `selected.events` []. (b) `traces: trace-20260301T000000Z.jsonl is not a readable trace file`. (c) `trace_error` null, same as the intact copy. |
| E14 | **Held-out filter, unit (R13; Q-91).** Moved from the static design: policy `from_calendar(plant_shifts(), "T03", False)` (refuses T03, S005, S006) and items (1) `alert_notice("S004", "S003-Pickup-Local")`; (2) a T02 report at S004 citing (T03, x); (3) `shift_report("T02", "S004", active=("S005-Pickup-Brasil",))`; (4) `alert_notice("S005", "S005-SUV-Local")`; (5) `shift_report("T03", "S006")`; (6) `shift_report("../T03", "S004")`. Then trace lines: (7) S004 with investigator `logbooks` [T03]; (8) `snapshot_id` `../S004`; (9) S004 clean | `select_shown` → `((1,), 5)`. `line_shown`: (7) false, (8) false, (9) true. With `is_open=True`: all kept, 0 omitted, and (7), (8) shown. |
| E15 | **Held-out end to end (R13, R4).** TH_DIR copy with `heldout_open=False` (first shift T06: S011, S012): ST and AG with no `at`, and AG `snapshot=S012` | `latest` 10, `positions` 1…10, `total` 10, no T06 in `days`. `omitted.snapshots` 2, `omitted.notices` = deliverables of S011/S012 in `read_deliverables` (≥ 2). No body contains `S011`, `S012` or `T06`. `load_view(...).rows.cases` holds no case with prefix S011 or S012. AG `snapshot=S012` gives `selected` null, the same body as `snapshot=S099`. |
| E16 | **HTTP surface (R14).** APP(TH_DIR).handle: GET `/`, `/app.js?x=1`; GET `/index.html`, `/app.js/`, `/../registry.sqlite3`, `/%2e%2e/x`, `/frontend/app.js`; POST `/api/state`; GET `/api/state` with Host `evil.example:8765`, `localhost:9999`, `127.0.0.1` and none; a copy whose `registry.sqlite3` holds the bytes `not sqlite` | 200 with `text/html; charset=utf-8` and `text/javascript; charset=utf-8`. Then 404 ×5, 405 with `Allow: GET`, then 403, 200, 200, 403 (the port is not compared). 500 with body `{"error": "dashboard: registry.sqlite3 is not a readable registry (DatabaseError)"}`. Every response has the three headers of R14 with the exact CSP. |
| E17 | **Real socket, read-only (R1, R2, R14).** A TH_DIR copy; `serve_dashboard(APP, 0, on_ready)` in a thread (port 0, ephemeral); the test waits for `on_ready(p)`, then urllib GETs `http://127.0.0.1:<p>/`, `/agentes`, `/api/state`, `/api/agents?snapshot=S012`; then `shutdown` | `p` > 0. 200 ×4. The JSON bodies equal `handle`'s for the same paths. The registry bytes and the path set under `OUTPUT_DIR` are unchanged (no `-journal`, no `-wal`). With an `OUTPUT_DIR` that does not exist: `/api/state` 200 with `registry` "missing", `latest` 0, and the directory is not created. |
| E18 | **Command (R1).** `main(["dashboard"], deps)` with a `serve(app, port, on_ready)` seam: (a) records `port`, calls `on_ready(8765)` and returns; (b) calls `on_ready(8765)`, then raises `KeyboardInterrupt`; (c) raises `OSError` without calling `on_ready`; (d) `heldout_first_shift="T99"`; (e) `["dashboard", "x"]`; (f) `["dashboard", "--help"]`. Settings with `anthropic_api_key=None` and `never_model` | (a) 0, port 8765, stdout `dashboard: http://127.0.0.1:8765/ (Ctrl+C to stop)\n`. (b) 0. (c) 2, stdout empty, stderr `dashboard: cannot listen on 127.0.0.1:8765 (OSError)`. (d) 2, stderr `first held-out shift T99 is not in turnos.csv`. (e) 2. (f) 0. The model factory is never called. |
| E19 | **Risk: an error cannot crash stderr (R1).** Moved from the static design. `heldout_first_shift="T99−"` (U+2212), `sys.stderr` = `TextIOWrapper(BytesIO(), encoding="cp1252")` | 2, no exception; stderr bytes `first held-out shift T99− is not in turnos.csv\n`. |
| E20 | **Setting (R1).** `Settings()` with `DASHBOARD_PORT` unset, `"9001"`, `"0"`, `"70000"` | 8765; 9001; validation error; validation error. `.env.example` lists `DASHBOARD_PORT=8765`. |
| E21 | **Risk: frontend assets (R15, R1).** The six files of R15; and `DashboardApp.from_settings` with the frontend directory pointed at a temp folder missing `agents.js` | All exist at `FRONTEND_DIR`, and `FRONTEND_DIR` equals the server's lookup. The temp-folder case raises `ValueError` `dashboard: frontend asset not found: agents.js`. No forbidden token of R15 appears in any file, and every `.href =` / `window.open(` matches an allowed form. Every `<script` in the HTML has `src` in {`/dom.js`, `/app.js`, `/agents.js`} and an empty body; there is no `<style`, `style=` or ` on[a-z]+=`. |
| E22 | **Risk: imports (R16).** Boundary scan | `dashboard/*` and `cases/registry/run_reader.py` import only what R16 allows. No module but `runner/cli.py` imports `plant_monitor.dashboard`. |
| E23 | **Deliverables agree (I3; R7).** TH_DIR and AGENT_DIR: `[n.item for n in read_run_rows(p).notices if is_deliverable(n.item)]` versus `read_deliverables(p)` | Equal, in the same order. |
| E24 | **Locked registry (R2).** A TH_DIR copy; the test holds a write lock (`BEGIN EXCLUSIVE` on its own connection); ST with the reader timeout patched to 0.05 s | 503, body `{"error": "dashboard: registry busy"}`. After the lock is released, 200. |

## Edge cases and assumptions
- **X1** · Registry and traces are read separately, so during a live run the newest snapshot can be committed before its trace line is appended (013 R14 order). It shows `traced: false` and author `unknown` for at most one poll. No test.
- **X2** · Before an agent run's first trace file exists, the mode looks like `thresholds_only`, so the first notices may briefly show "Texto de plantilla". Same window as X1, accepted.
- **X3** · Free text (logbooks, `texto`) can hold bidi controls (U+202E) that reorder how text looks. They cannot run code: text nodes plus CSP. Accepted, no test.
- **X4** · A processed snapshot missing from `turnos.csv` cannot be placed on the timeline. It still counts as a position, and the header shows its id without a shift. The run cannot produce one. No test.
- **X5** · The read model reloads the whole registry on every poll (two windows → about 1.3 requests/s). The registry of 60 snapshots is small; no cache is added.

## Acceptance
- [ ] E1–E24 pass on synthetic fixtures; CI never calls the model and opens no outside network (NFR-07). Every new test cites its spec id.
- [ ] **Changed expectation (not removed):** 012 E13 in `tests/unit/test_import_boundaries.py` adds `dashboard` to the layers `runner/cli.py` may import (R16, E22). In the same file, the leaf-module check that lists `domain/text.py` is re-cited to the 014 plan (shared `domain/text.py`); its assertion is unchanged. In `test_dashboard_state.py`, E5's Sedán × Local cause at 6 changes from `("no_declarada", None)` to `("no_declarada", "montaje")` after the criterio §6 correction of R6.
- [ ] Specs 001–013 tests pass unchanged otherwise. That covers the `index_attempts` / `text_by` move to `telemetry/trace.py`, the `drop_partial_tail` flag (off by default), and `open_readonly` / `check_columns` under `read_deliverables` and `notice_reader`.
- [ ] **Removed with the feature, not lowering coverage of kept code:** `tests/unit/notify/test_html_render.py`, `tests/integration/test_cli_html.py`, `tests/html_builders.py`, `tests/fixtures/html/`, and the `html_dir` test (old E10) in `tests/test_config.py`. Their two still-relevant rules move here: the held-out filter (E14) and `_fail` through `write_safe` (E19).
- [ ] Docs: README section "Live dashboard" replaces "How to render the HTML reports". Also `docs/STRUCTURE.md` rows and dependency line (plan), roadmap row 014, ADR-0021 rewritten, ADR index row.
- [ ] Manual, with the user's permission: the dashboard reviewed on a real run (tasks T14).
- [ ] `ruff`, `mypy --strict`, `pytest --cov` pass.

## Size
About 28 KB, over budget, after the design review added shared helpers and two risk examples. The feature has two windows and a replay contract, and every rule-bearing step sits in Python so pytest can test it (I2). Splitting Agentes into its own spec would leave Planta's links pointing to nothing.
