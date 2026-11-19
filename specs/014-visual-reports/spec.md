# 014 · Visual shift reports — Spec

- **Status:** Implemented (T9 pending: real-run review after the held-out run)
- **Requirements:** FR-26, FR-22, FR-23, FR-25, FR-20, FR-40, NFR-04, NFR-06
- **Stories:** US-05
- **Decisions:** ADR-0021 (post-run read-only HTML render, standard-library templates, one escape point, CSP, held-out omission). Q-84–Q-95 decided. Q-14, Q-17, Q-37, Q-79, Q-81 reused unchanged.
- **Week:** Stretch · **Priority:** Could

## Goal
Render the shift reports and immediate alerts already validated and stored in the registry as static HTML pages, so the plant manager reads the signal at a glance. Rendering only: no new system behavior, no model call, no change to what a report contains (004), no analytics (015), no change to `plant-monitor run`.

## Scope
- **In:** `notify/html.py` (pure renderer and the held-out filter `select_shown`), `notify/atomic.py` (`write_atomic`, extracted from `FileNotifier`), `domain/text.py` (`escape_controls`, moved from `telemetry/trace_render.py`), `Settings.html_dir`, the `plant-monitor html` subcommand in `runner/cli.py`, `cli._fail` through `write_safe`, two golden files under `tests/fixtures/html/`, tests, docs.
- **Out:** a notifier adapter in the run path (Q-84); Jinja2 or any new dependency (Q-86); HTML trace pages (Q-89); deleting stale pages; reading real data. Rendering the held-out run is a manual task after that run (T9).

## Decisions
- **D1 · When and where (Q-84, Q-85).** A post-run subcommand over `read_deliverables`; renderer in `notify`, composition in `runner/cli.py`.
- **D2 · Templates and escaping (Q-86, Q-87, Q-90).** As R9–R11.
- **D3 · Pages, trace link, labels, numbers, silence (Q-88, Q-89, Q-92–Q-94).** As R3–R8.
- **D4 · Held-out omission (Q-91).** As R12.
- **D5 · Tests (Q-95).** Two golden files, the rest structural.
- **D6 · Interface choices** (taken by the spec writer; see plan):
  - **I1** `parse_args` returns `RunOptions | TraceOptions | HtmlOptions`; `HtmlOptions` has no fields. No 012/013 test changes.
  - **I2** `escape_controls` moves to `domain/text.py`, so `notify` can use it; `telemetry/trace_render.py` imports it from there. Same function, same 013 tests.
  - **I3** `write_atomic(target, data)` is extracted to `notify/atomic.py`; `FileNotifier` writes through it (whether `_write` stays as a wrapper is the implementer's choice). 004 E30/E31 stay green unchanged.
  - **I4** Escape by default: a `Markup` `str` subclass marks template output; the one fill function escapes every value that is not `Markup`. A forgotten escape cannot happen by omission.
  - **I5** File names are `<report_id>.html` and `<notice_id>.html`, with the validated id as is (`Sedán` stays Unicode on disk). An `href` is `urllib.parse.quote(name, safe="")`.
  - **I6** Id patterns use `[0-9]`, never `\d` (which matches non-ASCII digits). Evidence `bitacora` ids are checked with the shift pattern too.
  - **I7** The held-out filter is `select_shown(items, policy)` in `notify/html.py` (it imports `domain.calendar.HeldOutPolicy`, allowed by the `notify` rule), next to the private `_shown_ids`, so the module that renders an item also says what it shows. `runner/cli.py` only calls it.
  - **I8** Output lines: stdout `html: shift reports <r>, alerts <a>, in <html_dir>`; stderr `html: <k> held-out or unverifiable items omitted (HELDOUT_OPEN=false)`; id errors `html: invalid <field>: <value>`.
  - **I9** `retraso_dias` uses the same formatting as `gap_unidades` (Q-93, amended).
  - **I10** Every page is rendered, every id validated and every page encoded to UTF-8 (`Page.data: bytes`) before the first write; item pages are written in registry order and `index.html` last. So no error after the read writes anything.
  - **I11** The severity badge text is the contract value; a peak adds the CSS class `peak` and the label `pico`. CSS class names are English.
  - **I12** `cli._fail` writes through `write_safe(message + "\n", sys.stderr)`, so an unencodable character in an error message never crashes the command (`run` and `trace` too). For ASCII messages the output is unchanged.
  - **I13** `format_pct` repeats `trace_render._number`'s expression with `DECIMALS`; it is not extracted into `domain/numbers.py`, to keep 013's module limited to the import move.
  - **I14** `render_site` refuses a duplicate page name with `ValueError` (`html: duplicate page <name>`), checked after every id is validated.

## Behavior

### R1 · Command (Q-85, I1)
`plant-monitor html`, a third subcommand of the 012 parser, with no arguments or options. `html --help` returns 0; an extra argument is an argparse error (2). `run` and `trace` keep their options, behavior and tests.

### R2 · Read-only source, no model (Q-84, ADR-0002, ADR-0019)
- Data comes only from `read_deliverables(settings.registry_path)` (`mode=ro`, deliverable rows in `(seq, idx)` order) and `turnos.csv` (for the held-out policy, R12).
- The command never builds `SqliteRegistry`, the model, the pipelines or the ledger; `deps.model_factory` is never called; the API key is not checked; logging is not configured.
- A stored item is rendered as stored; it is never rebuilt, re-validated with new values or copied with `model_copy`.
- It writes only under `settings.html_dir`. The registry file and every other path under `OUTPUT_DIR` are unchanged (no `-journal`, no `-wal`).

### R3 · Pages and writing (Q-85, Q-88, I5, I10)
- One page per `ShiftReport` (`<report_id_for(turno_id)>.html`, e.g. `T05-informe.html`), one per alert (`<notice_id>.html`), and `index.html`, all directly in `settings.html_dir` (created if missing).
- Each file is written with `write_atomic`: UTF-8 bytes without BOM, a temp file in the same directory, then `os.replace`. An existing file is overwritten; no file is ever deleted.
- All pages are rendered and encoded first (I10); a text that cannot be encoded as UTF-8 (a lone surrogate) raises `ValueError` (`html: <page name> is not encodable as UTF-8`) before any write. Then item pages are written in registry order, and `index.html` last, so the index never links a page not yet written.

### R4 · Report page (FR-22, FR-23, FR-25, Q-92, Q-94; US-05)
In this order: the back link to the index; the title `Informe de turno <turno_id>`; `Snapshot de cierre: <snapshot_id>`; the heading `Novedades` and one notice block (R5) per news item in stored order, or `Sin novedades en este turno`; the heading `Casos activos` and the table, one row per `casos_activos` item in stored order, or `Sin casos activos`.
Table columns: `Caso`, `Modelo`, `Mercado`, `Gap (u)`, `Gap (%)`, `Retraso (días)`, `Severidad`, `Máxima`, `Estado`, `Etapa cuello`. The renderer never reorders, filters or adds items.

### R5 · Notice block (FR-25, Q-89, Q-93, I11)
For an alert and for each news item: `case_id` as heading; severity badge, maximum badge (a peak is marked only when `severidad_maxima > severidad`), `estado`; `motivo` (values joined by `, `, or `—` when empty) and `origen`; `texto`; `causa.categoria` and `etapa` (or `—`); evidence (`Evidencia: —`, or one `<blockquote>` per item with the fragment and `Bitácora <bitacora>`); and the copyable `plant-monitor trace <notice_id>` in a `<code>` element.

### R6 · Alert page (Q-88)
The back link; the title `Alerta inmediata · <case_id>`; `Snapshot: <snapshot_id>`; the notice block (R5).

### R7 · Index (Q-88)
The title `Informes y alertas`; then an ordered list in registry `(seq, idx)` order, alerts and reports interleaved, or `Sin informes ni alertas`.
- Alert entry: link `<snapshot_id> · Alerta inmediata · <case_id>` plus its severity badge.
- Report entry: link `<snapshot_id> · Informe de turno <turno_id>`, then `· Novedades: <n> · Casos activos: <m>`.

### R8 · Number and empty-value formatting (Q-93, I9)
- `format_plain(v)`: `None` → `—`; an integral float → its integer form (`-4.0` → `-4`, `-0.0` → `0`); otherwise Python's shortest `repr`, which is the JSON form (`-2.5`). Used for `gap_unidades` and `retraso_dias`. No `+` sign, ASCII `-`.
- `format_pct(v)`: `None` → `—`; otherwise `f"{round_display(v) + 0.0:.{DECIMALS}f}%"` (`DECIMALS` = 1; `23.61111` → `23.6%`, `-0.04` → `0.0%`), the same expression as `trace_render._number` (I13).
- A null `etapa` or `etapa_cuello` → `—`. Contract values (`no_declarada`, `en_seguimiento`, `critica`) are shown verbatim.

### R9 · Escaping, one choke point (Q-87, Q-81, FR-20, I4)
- Every interpolated value, enum values and numbers included, becomes `html.escape(escape_controls(value), quote=True)`. `escape_controls` maps each character in U+0000–U+001F, U+007F, U+0080–U+009F to `\xHH` (two lowercase hex digits).
- Only template output (`Markup`) is inserted unescaped. Template constants contain no value.
- So a page holds no character of those ranges except the template's `\n` separators, and no value can open a tag, close `<style>` or break out of an attribute.

### R10 · Ids, file names and links (Q-87, I5, I6)
- Patterns (full match): `snapshot_id` `S[0-9]{3}`; `turno_id` and evidence `bitacora` `T[0-9]{2}`; `case_id` `S[0-9]{3}-<Model>-<Market>` (enum values); `notice_id` `S[0-9]{3}-(alerta_inmediata|informe_de_turno)-<case_id pattern>`.
- `validate_ids(item)` checks in this order, first failure wins:
  - a top-level notice: `tipo` first (only `alerta_inmediata` is a page; anything else is `html: invalid tipo: <value>`), then `snapshot_id`, `case_id`, `notice_id`, then each evidence `bitacora`;
  - a report: `turno_id`, `snapshot_id`, then each news item's `snapshot_id`, `case_id`, `notice_id` and `bitacora`s (no `tipo` check: the `ShiftReport` validator already requires `informe_de_turno`), then each row's `case_id`.
- A failure raises `UnsafeId` (`ValueError`) with message `html: invalid <field>: <escape_controls(value)>`. With the guard open this exits 2 and nothing is written; with it closed the item is omitted instead (R12).
- `render_report`, `render_alert` and `render_index` call `validate_ids` on their item(s); `render_site` validates every item before rendering any page, then refuses a duplicate page name (I14).
- `href` = `quote(file_name, safe="")`, then escaped like any value.

### R11 · Page shell, determinism (Q-90, Q-92, Q-95)
- Every page: `<!DOCTYPE html>`, `<html lang="es">`, `<meta charset="utf-8">`, the CSP `<meta>` exactly as Q-90, the embedded CSS of the plan and no other resource.
- No `<script`, no `src=`, no `http:` / `https:`, no `url(`, no `@import` anywhere in a page.
- Labels are the plan's Spanish strings. Lines are joined with `\n`, the page ends with `</html>\n`, and nothing varies between renders (no time, no path): the same items give the same bytes.

### R12 · Held-out omission (Q-91, FR-40, Q-37, I7)
- `policy = HeldOutPolicy.from_calendar(load_shifts(plant_dir / "turnos.csv"), heldout_first_shift, heldout_open)`, as `run` and `trace`.
- `select_shown(items, policy) -> (kept, k)` in `notify/html.py`, using the private `_shown_ids(item)`, the ids an item would show:
  - alert: snapshots {`snapshot_id`, the prefix before the first `-` of `case_id`}; shifts {each evidence `bitacora`};
  - report: snapshots {`snapshot_id`} ∪ the news items' snapshots ∪ the prefix of every news and row `case_id`; shifts {`turno_id`} ∪ every news evidence `bitacora`.
- An item is **omitted whole** (no page, no index entry) when its snapshots meet `policy.refused_snapshots` or its shifts meet `policy.refused_shifts`. Free text (`texto`, `fragmento`) is not parsed for ids.
- **Unverifiable ids (guard closed).** When `policy.is_open` is false, an item for which `validate_ids` raises `UnsafeId` is omitted too and counted in `k`: a corrupt id such as `../T06` cannot be proven not held out. When the guard is open, `select_shown` keeps every item and R10's exit 2 applies.
- The filter runs before `render_site`, so an error message never names an omitted item.
- With `k > 0`, stderr gets `html: <k> held-out or unverifiable items omitted (HELDOUT_OPEN=false)`. With the guard open nothing is omitted.

### R13 · Exit codes and output (Q-85, I8)
- 0: done, including an empty set (only `index.html`). stdout `html: shift reports <r>, alerts <a>, in <html_dir>` (counts of rendered items), through `write_safe`.
- 2: invalid settings (same message as `run`), `DataLoadError` (`turnos.csv`), `ValueError` (unknown `heldout_first_shift`, registry missing or unreadable from `read_deliverables`, `UnsafeId`, a duplicate page name, a page not encodable as UTF-8), `OSError` on a write, `sqlite3.Error`. One line on stderr, written through `write_safe` (I12).

### R14 · Layers and setting (Q-84, Q-85, I2, I3)
- `notify/html.py` (including its use of `domain.calendar`) and `notify/atomic.py` import only `domain` (the existing `notify` scan covers them). `domain/text.py` imports nothing from the project; it joins the leaf-module list of the existing 006 E18 boundary test.
- `runner/cli.py` keeps its 012 R11 layers; no new module imports `anthropic` or `mcp`.
- `Settings.html_dir` = `output_dir / "html"`, a derived property: no environment variable, no `.env.example` change.

## Worked examples

**Notation.**
- **N_SE** = news `S010-informe_de_turno-S005-SUV-Europa`: SUV, Europa, `critica`/`critica`, `escalado`, `agente`, motivo `(bitacora,)`, cause `retencion_de_calidad`/`calidad`, evidence (`T05`, `la auditoría de homologación retuvo en calidad las SUV para Europa`), texto `SUV × Europa escaló a crítica por bitácora: auditoría en calidad.`
- **N_PB** = news `S010-informe_de_turno-S009-Pickup-Brasil`: Pickup, Brasil, `media`/`alta` (peak), `en_seguimiento`, `umbral`, motivo `(gap,)`, cause `no_declarada`/null, no evidence, texto `Pickup × Brasil: caso nuevo; pico de alta. Estado en seguimiento, severidad media, máxima alta. Causa no declarada, sin etapa cuello identificada.`
- **ROW_SE** = `S005-SUV-Europa`, SUV, Europa, −4.0, −13.33333, 0.0, `critica`, `critica`, `escalado`, `calidad`. **ROW_PB** = `S009-Pickup-Brasil`, Pickup, Brasil, −2.5, None, None, `media`, `alta`, `en_seguimiento`, None.
- **REPORT_T05** = `ShiftReport("T05", "S010", (N_SE, N_PB), (ROW_SE, ROW_PB))` (stored `case_order`).
- **A1** = `alert_notice("S009", "S001-Sedán-Local")`; **EMPTY_T06** = `shift_report("T06", "S012")` (`notice_builders`).
- **TH_DIR**, `copied`, `cli_deps`, `never_model`: from `trace_builders` / `cli_builders` (013). TH_DIR holds T01–T06 (S001–S012), threshold-only. **H()** = `main(["html"], deps=cli_deps(<settings>, None))`, on a `copied` TH_DIR unless stated.
- **‹CSS›** = the plan's `CSS` constant, verbatim.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **Formatting (R8; Q-93).** `format_plain` of −4.0, −2.5, −0.0, 12.0, None; `format_pct` of 23.61111, −13.33333, −0.04, None | `-4`, `-2.5`, `0`, `12`, `—`; `23.6%`, `-13.3%`, `0.0%`, `—`. |
| E2 | **Report page, golden (R4, R5, R8, R9, R11; US-05, Q-95).** `render_report(REPORT_T05)` (a `str`) | Equals the text of `tests/fixtures/html/report_T05.html` (read as UTF-8 with LF kept): block **E2** below with ‹CSS› substituted. |
| E3 | **Visible silence (R4; Q-94).** (a) `ShiftReport("T04", "S008", (), (ROW_SE,))`; (b) EMPTY_T06 | (a) The page has `<p class="empty">Sin novedades en este turno</p>` before `<h2>Casos activos</h2>`, then a table with exactly one `<tr><td>S005-SUV-Europa</td>` row. (b) It has `Sin novedades en este turno` and `<p class="empty">Sin casos activos</p>`, and no `<table>`. |
| E4 | **Alert page (R5, R6; Q-89).** `render_alert(A1)` | Contains `<title>Alerta inmediata · S001-Sedán-Local</title>`, `<nav><a href="index.html">Índice</a></nav>`, `<p>Snapshot: S009</p>`, `<span class="sev sev-critica">critica</span>` twice (no `peak` class and no `pico` label in the body), `<p>Evidencia: —</p>`, `<p>Causa: no_declarada · Etapa: montaje</p>` and `<code>plant-monitor trace S009-alerta_inmediata-S001-Sedán-Local</code>`. |
| E5 | **Index and site, golden (R3, R7, R10; Q-88).** `render_site((A1, REPORT_T05, EMPTY_T06))` | Page names in order: `S009-alerta_inmediata-S001-Sedán-Local.html`, `T05-informe.html`, `T06-informe.html`, `index.html`. Each `Page.data` is UTF-8 bytes; the T05 page's `data` equals E2's golden file bytes, and `index.html`'s equals `tests/fixtures/html/index.html`: block **E5** below. |
| E6 | **Risk: a logbook cannot inject markup (R9; Q-87, FR-20).** An alert at S010 for `S010-Pickup-Local`, `agente`, motivo `(bitacora,)`, evidence (`T05`, `<script>alert(1)</script></style>` + ESC + `[31mrojo`), texto `it's x" onmouseover="y` | Contains `<blockquote>&lt;script&gt;alert(1)&lt;/script&gt;&lt;/style&gt;\x1b[31mrojo</blockquote>` (literal backslash) and `<p class="text">it&#x27;s x&quot; onmouseover=&quot;y</p>`. `<script` is absent, `</style>` occurs once, and no character is in U+0000–U+001F (except `\n`), U+007F or U+0080–U+009F. |
| E7 | **Risk: no script, no network (R11; Q-90).** Every page of E5 | Each has `<meta charset="utf-8">` and `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">` once each, and none contains `<script`, `src=`, `http:`, `https:`, `url(` or `@import`. |
| E8 | **Unsafe ids and duplicates (R10; Q-87, I14).** `render_site` of: (a) `shift_report("../T05", "S010")`; (b) `shift_report("T5", "S010")`; (c) an alert at S009 with `case_id` `S001-Sedán-Local/x` (and the matching `notice_id`); (d) A1's fields with evidence (`T05` + LF, `x`); (e) `(A1, A1)`; (f) `(news_notice("S010", "S010-Pickup-Local"),)` | (a)–(d), (f): `UnsafeId`, message: (a) `html: invalid turno_id: ../T05`; (b) `html: invalid turno_id: T5`; (c) `html: invalid case_id: S001-Sedán-Local/x`; (d) `html: invalid bitacora: T05\x0a`; (f) `html: invalid tipo: informe_de_turno`. (e) `ValueError`, `html: duplicate page S009-alerta_inmediata-S001-Sedán-Local.html`. |
| E9 | **Held-out filter (R12; Q-91).** `policy` = `HeldOutPolicy.from_calendar(plant_shifts(), "T03", False)` (refuses T03, S005, S006). Items, in order: (1) `alert_notice("S004", "S003-Pickup-Local")`; (2) a T02 report at S004 whose one news item cites (`T03`, `x`); (3) `shift_report("T02", "S004", active=("S005-Pickup-Brasil",))`; (4) `alert_notice("S005", "S005-SUV-Local")`; (5) `shift_report("T03", "S006")`; (6) `shift_report("../T03", "S004")`. (a) `select_shown(items, policy)`. (b) The same with `is_open=True`, then `render_site` of the kept items | (a) `((item 1,), 5)`: (2) omitted for its cited T03 alone, (3) for its row's opening snapshot S005, (4) for its snapshot, (5) for its shift and snapshot, (6) because its id cannot be verified while the guard is closed. (b) All six kept, 0 omitted; `render_site` raises `UnsafeId` `html: invalid turno_id: ../T03` (ids are checked before duplicate names). |
| E10 | **Setting (R14).** `Settings(output_dir=Path("out")).html_dir` | `Path("out") / "html"`. No new environment variable. |
| E11 | **Full render (R1–R3, R7, R11, R13).** H() with the guard open. Record the registry bytes and every path under `OUTPUT_DIR` first; then H() again | 0. stderr empty. stdout `html: shift reports 6, alerts <a>, in <html_dir>` with `<a>` = alerts in `read_deliverables`. The files under `html_dir` are exactly `T01-informe.html` … `T06-informe.html`, one `<notice_id>.html` per alert and `index.html`; the index has one `href` per page, equal to `quote(name, safe="")`, in `read_deliverables` order. The registry bytes and the paths outside `html_dir` are unchanged; `never_model` was not called. The second H() returns 0 and every file is byte-identical. |
| E12 | **Held-out omission end to end (R12, R13).** H() with `heldout_open=False` (first held-out shift T06: S011, S012) | 0. No `T06-informe.html`, and no page for any deliverable of S011 or S012 (e.g. `S012-alerta_inmediata-S010-Pickup-Local.html`). No page under `html_dir` contains `S011`, `S012` or `T06`. stderr is exactly `html: <k> held-out or unverifiable items omitted (HELDOUT_OPEN=false)` with `<k>` = deliverables whose `snapshot_id` is S011 or S012 (at least 2). stdout counts `shift reports 5`. |
| E13 | **Errors and the empty set (R13).** (a) H() with an `output_dir` that does not exist. (b) `heldout_first_shift="T99"`. (c) cli's `read_deliverables` monkeypatched to return `(shift_report("../T05", "S010"),)`. (d) A fresh `output_dir` whose registry the test creates with `SqliteRegistry` (no rows) | (a) 2; stderr contains `registry not found`; the directory is not created. (b) 2; stderr `first held-out shift T99 is not in turnos.csv`. (c) 2; stderr `html: invalid turno_id: ../T05`; `html_dir` does not exist. (d) 0; `html_dir` holds only `index.html`, which contains `<p class="empty">Sin informes ni alertas</p>`; stdout `html: shift reports 0, alerts 0, in <html_dir>`. |
| E14 | **Risk: an error message cannot crash stderr (R13; I12).** Guard open; cli's `read_deliverables` monkeypatched to return `(shift_report("T05−", "S010"),)` (U+2212); `sys.stderr` replaced by `io.TextIOWrapper(io.BytesIO(), encoding="cp1252")` | 2, no exception. The stderr bytes are `html: invalid turno_id: T05−` (backslash escape from `backslashreplace`) followed by `\n`. 012/013 stderr expectations (ASCII) are unchanged. |
| E15 | **Encoding before writing (R3; I10).** (a) `render_site` of an alert like A1 whose `texto` holds a lone surrogate U+D800. (b) H() with cli's `read_deliverables` monkeypatched to return that alert, guard open | (a) `ValueError`, `html: S009-alerta_inmediata-S001-Sedán-Local.html is not encodable as UTF-8`. (b) 2; stderr is that message; `html_dir` does not exist. |

**E2** (`tests/fixtures/html/report_T05.html`, LF, ending with one `\n`):
```
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informe de turno T05</title>
<style>
‹CSS›
</style>
</head>
<body>
<nav><a href="index.html">Índice</a></nav>
<h1>Informe de turno T05</h1>
<p>Snapshot de cierre: S010</p>
<h2>Novedades</h2>
<article class="notice">
<h3>S005-SUV-Europa</h3>
<p>Severidad <span class="sev sev-critica">critica</span> · Máxima <span class="sev sev-critica">critica</span> · Estado escalado</p>
<p>Motivo: bitacora · Origen: agente</p>
<p class="text">SUV × Europa escaló a crítica por bitácora: auditoría en calidad.</p>
<p>Causa: retencion_de_calidad · Etapa: calidad</p>
<p>Evidencia:</p>
<figure><blockquote>la auditoría de homologación retuvo en calidad las SUV para Europa</blockquote><figcaption>Bitácora T05</figcaption></figure>
<p>Traza: <code>plant-monitor trace S010-informe_de_turno-S005-SUV-Europa</code></p>
</article>
<article class="notice">
<h3>S009-Pickup-Brasil</h3>
<p>Severidad <span class="sev sev-media">media</span> · Máxima <span class="sev sev-alta peak">alta</span> <strong>pico</strong> · Estado en_seguimiento</p>
<p>Motivo: gap · Origen: umbral</p>
<p class="text">Pickup × Brasil: caso nuevo; pico de alta. Estado en seguimiento, severidad media, máxima alta. Causa no declarada, sin etapa cuello identificada.</p>
<p>Causa: no_declarada · Etapa: —</p>
<p>Evidencia: —</p>
<p>Traza: <code>plant-monitor trace S010-informe_de_turno-S009-Pickup-Brasil</code></p>
</article>
<h2>Casos activos</h2>
<table>
<thead><tr><th>Caso</th><th>Modelo</th><th>Mercado</th><th>Gap (u)</th><th>Gap (%)</th><th>Retraso (días)</th><th>Severidad</th><th>Máxima</th><th>Estado</th><th>Etapa cuello</th></tr></thead>
<tbody>
<tr><td>S005-SUV-Europa</td><td>SUV</td><td>Europa</td><td>-4</td><td>-13.3%</td><td>0</td><td><span class="sev sev-critica">critica</span></td><td><span class="sev sev-critica">critica</span></td><td>escalado</td><td>calidad</td></tr>
<tr><td>S009-Pickup-Brasil</td><td>Pickup</td><td>Brasil</td><td>-2.5</td><td>—</td><td>—</td><td><span class="sev sev-media">media</span></td><td><span class="sev sev-alta peak">alta</span> <strong>pico</strong></td><td>en_seguimiento</td><td>—</td></tr>
</tbody>
</table>
</body>
</html>
```

**E5** (`tests/fixtures/html/index.html`; the shell lines 1–11 as in E2, with the title `Informes y alertas`):
```
<body>
<h1>Informes y alertas</h1>
<ol class="timeline">
<li><a href="S009-alerta_inmediata-S001-Sed%C3%A1n-Local.html">S009 · Alerta inmediata · S001-Sedán-Local</a> <span class="sev sev-critica">critica</span></li>
<li><a href="T05-informe.html">S010 · Informe de turno T05</a> · Novedades: 2 · Casos activos: 2</li>
<li><a href="T06-informe.html">S012 · Informe de turno T06</a> · Novedades: 0 · Casos activos: 0</li>
</ol>
</body>
</html>
```

## Edge cases and assumptions
- **X1** · Stale pages. A page from an earlier render (e.g. one rendered with the guard open) is never deleted; the index links only the current set. The README says to render into a fresh `OUTPUT_DIR` copy, or to empty `html/` by hand, before sharing. No test.
- **X2** · Free text is not parsed for ids (R12). A `texto` is written at or before its own snapshot, so it is covered by construction (013 R11 precedent). No test.
- **X3** · Unicode format characters outside the Q-81 ranges (e.g. U+202E) are not escaped. They can reorder how text looks but cannot run code (no JS, CSP). Accepted; no test.
- **X4** · Render during a live `run --speed`. `read_deliverables` is one `SELECT` on a `mode=ro` connection, so it sees one committed state, and the index matches its pages. No test (a race test would be flaky).
- **X5** · A write `OSError` part-way leaves the pages already written and the previous `index.html` (written last), and exits 2; a re-run repairs it. Not tested beyond 004 E30's atomic-write test.
- **X6** · A long float such as a `retraso_dias` of `1.0416666666666667` is shown as in JSON (Q-93). The real run's pages are checked by hand in T9.
- **X7** · A snapshot id that is not in `turnos.csv` is not in `HeldOutPolicy`'s refused sets, so with a valid shape it would be shown. The run cannot produce one today (every processed snapshot comes from the calendar); left as is, no test.
- **X8** · Both golden files hold the CSS verbatim, so a CSS change edits two fixtures. Accepted for byte-exact goldens.
- **X9** · `read_deliverables` parses every deliverable row before `select_shown` filters, so a corrupt held-out row would fail with an error message that may name its values, even with the guard closed. The run validates payloads before storing them, so only a hand-edited registry can trigger it; 013 `trace` has the same exposure. Accepted.

## Acceptance
- [ ] E1–E15 pass on synthetic fixtures; CI makes no network call and never calls the model (NFR-07). Every new test cites its spec id (`Risk:` tests too).
- [ ] Specs 001–013 tests pass unchanged. None is expected to change; if one must, it is re-expected (never deleted) and listed here.
- [ ] Refactors with no behavior and no test-expectation change: `escape_controls` moved to `domain/text.py` (I2); `write_atomic` extracted from `FileNotifier` (I3); `domain/text.py` added to the leaf-module list of the existing E18 boundary test (no new test function).
- [ ] Behavior change, neutral for ASCII text: `cli._fail` writes through `write_safe` (I12). It touches the stderr path that 012 and 013 tests assert (`run`, `trace` errors); their expectations stay as they are, none is removed. E14 covers the non-ASCII case.
- [ ] Docs: README "How to render the HTML reports" (command, exit codes, held-out note, read-only, X1), `docs/STRUCTURE.md` (new modules, `notify/file.py`, `telemetry/trace_render.py`, `runner/cli.py`, `config.py` rows, dependency line for `notify/html.py`), roadmap row 014, ADR-0021.
- [ ] Manual, after the held-out run, with the user's permission: the held-out `OUTPUT_DIR` rendered and its pages reviewed by hand (T9).
- [ ] `ruff`, `mypy --strict`, `pytest --cov` pass.

## Size
About 28 KB, over budget: the two golden blocks are byte-exact, as Q-95 asks, and R10/R12 must fix the id patterns, the check order and the omission rule precisely for the held-out guarantee to be testable.
