# 014 · Visual shift reports — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `domain/text.py` | New | `escape_controls` (moved verbatim from `telemetry/trace_render.py`, I2). |
| `telemetry/trace_render.py` | Refactor | Imports `escape_controls` from `domain.text`; no other change. |
| `notify/atomic.py` | New | `write_atomic(target, data)` (extracted from `FileNotifier._write`, I3). |
| `notify/file.py` | Refactor | `FileNotifier` uses `write_atomic`; bytes unchanged. Whether `_write` stays as a one-line wrapper or the calls go direct is left to the implementer (O12). |
| `notify/html.py` | New | Pure renderer: escaping, formatting, id checks, pages, `render_site`; the held-out filter `select_shown` with the private `_shown_ids` (I7). Imports only `domain` (incl. `domain.calendar`). |
| `config.py` | Adds | `Settings.html_dir`. |
| `runner/cli.py` | Changes | `HtmlOptions`, third subparser, `_html`, `main` dispatch; `_fail` through `write_safe` (I12). |
| `tests/html_builders.py` | New | N_SE, N_PB, ROW_SE, ROW_PB, REPORT_T05, A1, EMPTY_T06, `GOLDEN` path, `golden`, `rendered(settings, capsys)`. |
| `tests/fixtures/html/report_T05.html`, `index.html` | New | Golden files (E2, E5), LF, one final `\n`. |
| `tests/unit/test_import_boundaries.py` | Changes | `domain/text.py` added to the leaf list of `test_e18_verbatim_and_errors_import_nothing_from_the_project` (O11); no new test function. |
| Registry, trace schema, pipelines, `series.py`, `run` wiring | Unchanged | — |

## Types and interfaces

### `escape_controls`
`domain/text.py`: `escape_controls(text: str) -> str`. Same regex `[\x00-\x1f\x7f-\x9f]` and `\xHH` output as 013 R12.

### `write_atomic`
`notify/atomic.py`: `write_atomic(target: Path, data: bytes) -> None`. `target.parent.mkdir(parents=True, exist_ok=True)`, `tempfile.mkstemp(dir=target.parent, suffix=".tmp")`, write bytes, `os.replace`; on any `BaseException` unlink the temp file and re-raise. `FileNotifier` writes through it; keeping `_write` as a wrapper or calling `write_atomic` directly is the implementer's choice (O12).

### `Settings.html_dir`
`config.py`: `@property html_dir -> Path`: `self.output_dir / "html"`, docstring "HTML pages of the reports and alerts, derived from output_dir."

### Renderer types
`notify/html.py`:
```python
class Markup(str):
    """Already-escaped HTML; created only by '_fill', '_join' and the template constants."""

class UnsafeId(ValueError):
    """An id outside its allowed pattern; message 'html: invalid <field>: <escape_controls(value)>'."""

@dataclass(frozen=True)
class Page:
    name: str
    data: bytes

@dataclass(frozen=True)
class _ShownIds:
    snapshots: frozenset[str]
    shifts: frozenset[str]

type Deliverable = Notice | ShiftReport
```

### Renderer functions
```python
def escape_text(value: str) -> str: ...
def format_plain(value: float | None) -> str: ...
def format_pct(value: float | None) -> str: ...
def validate_ids(item: Deliverable) -> None: ...
def page_name(item: Deliverable) -> str: ...
def select_shown(
    items: Sequence[Deliverable], policy: HeldOutPolicy
) -> tuple[tuple[Deliverable, ...], int]: ...
def render_report(report: ShiftReport) -> str: ...
def render_alert(notice: Notice) -> str: ...
def render_index(items: Sequence[Deliverable]) -> str: ...
def render_site(items: Sequence[Deliverable]) -> tuple[Page, ...]: ...
```
- `escape_text`: `html.escape(escape_controls(value), quote=True)`.
- `format_plain` / `format_pct`: R8; `format_pct` is `f"{round_display(v) + 0.0:.{DECIMALS}f}%"` with `DECIMALS` and `round_display` from `domain.numbers` (I13, not shared with `trace_render`).
- `validate_ids`: R10 order; raises `UnsafeId`. A top-level `Notice` is checked for `tipo is NoticeType.ALERT` first (`html: invalid tipo: <value>`); news items get no `tipo` check, since `ShiftReport`'s validator already requires `informe_de_turno`. `NOTICE_ID` accepts both types; the `tipo` check, not the pattern, keeps a news or `sin_aviso` notice from becoming a page.
- `page_name`: `report_id_for(turno_id) + ".html"` or `notice_id + ".html"`; call after `validate_ids`.
- `select_shown`: keeps, in order, each item whose `_shown_ids` meet neither `policy.refused_snapshots` nor `policy.refused_shifts`, and, when `not policy.is_open`, whose `validate_ids` does not raise; returns the kept items and the omitted count (R12, O9).
- `_shown_ids(item) -> _ShownIds`: R12 sets; never raises (prefix = `case_id.split("-", 1)[0]`).
- `render_report`, `render_alert`, `render_index`: each calls `validate_ids` on its item(s) (from T4; in T2 `render_report` does not validate yet), then fills the templates; return the page text ending with `\n`.
- `render_site`, in order: `validate_ids` on every item; a duplicate `page_name` raises `ValueError(f"html: duplicate page {name}")` (I14); render the item pages in input order and `index.html` last; encode each with `text.encode("utf-8")`, re-raising `UnicodeEncodeError` as `ValueError(f"html: {name} is not encodable as UTF-8")` (I10, F3).
- Private: `_fill(template: Template, **values: str) -> Markup` (the choke point: `Markup` values inserted as is, any other `str` through `escape_text`; `Template.substitute`, so a missing key raises `KeyError`); `_join(parts: Iterable[Markup]) -> Markup` (`"\n"`); `_badge(severity: Severity, *, peak: bool = False) -> Markup`; `_notice(notice: Notice) -> Markup`; `_evidence(items: Sequence[Evidence]) -> Markup`; `_row(row: ActiveCaseRow) -> Markup`; `_page(title: str, body: Markup) -> str`; `_href(name: str) -> str` (`quote(name, safe="")`).
- Pattern constants, compiled once, used with `fullmatch`: `SNAPSHOT_ID = r"S[0-9]{3}"`, `SHIFT_ID = r"T[0-9]{2}"`, `CASE_ID` = `S[0-9]{3}-(?:<Model values>)-(?:<Market values>)` built with `re.escape` over the enums, `NOTICE_ID` = `S[0-9]{3}-(?:alerta_inmediata|informe_de_turno)-` + `CASE_ID`, with the two types taken from `NoticeType`.

### Templates and labels
All are `string.Template` constants; no trailing spaces; `\n` line breaks; no final newline except `_PAGE`. `—` is U+2014, `·` U+00B7.

`CSS` (inserted as `Markup`, no final newline):
```
body{font-family:system-ui,sans-serif;margin:2rem;max-width:72rem;color:#1a1a1a}
table{border-collapse:collapse}
th,td{border:1px solid #999;padding:.25rem .5rem;text-align:left}
.sev{padding:0 .4rem;border:1px solid #555;border-radius:.2rem;font-weight:bold}
.sev-ninguna{background:#e9ecef}
.sev-media{background:#fff3bf}
.sev-alta{background:#ffc078}
.sev-critica{background:#c92a2a;color:#fff}
.peak{outline:2px solid #c92a2a}
.notice{border-top:1px solid #ccc;padding:.5rem 0}
.empty{font-style:italic}
blockquote{margin:.25rem 0;padding-left:.75rem;border-left:3px solid #999}
figure{margin:.25rem 1rem}
code{background:#f1f3f5;padding:0 .2rem}
```

`_PAGE` (ends with `\n` after `</html>`):
```
<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$title</title>
<style>
$css
</style>
</head>
<body>
$body
</body>
</html>
```

`_REPORT`:
```
<nav><a href="index.html">Índice</a></nav>
<h1>$title</h1>
<p>Snapshot de cierre: $snapshot_id</p>
<h2>Novedades</h2>
$news
<h2>Casos activos</h2>
$active
```
`$title` = `Informe de turno <turno_id>` (also the `<title>`). `$news` = the joined `_NOTICE` blocks, or `_NO_NEWS` = `<p class="empty">Sin novedades en este turno</p>`. `$active` = `_TABLE`, or `_NO_ACTIVE` = `<p class="empty">Sin casos activos</p>`.

`_NOTICE`:
```
<article class="notice">
<h3>$case_id</h3>
<p>Severidad $severity · Máxima $maximum · Estado $estado</p>
<p>Motivo: $motivo · Origen: $origen</p>
<p class="text">$texto</p>
<p>Causa: $categoria · Etapa: $etapa</p>
$evidence
<p>Traza: <code>plant-monitor trace $notice_id</code></p>
</article>
```
`$evidence` = `<p>Evidencia: —</p>`, or `<p>Evidencia:</p>` followed by one `_QUOTE` line per item: `<figure><blockquote>$fragmento</blockquote><figcaption>Bitácora $bitacora</figcaption></figure>`.

`_BADGE` = `<span class="sev sev-$value">$value</span>`; `_PEAK_BADGE` = `<span class="sev sev-$value peak">$value</span> <strong>pico</strong>`.

`_TABLE`:
```
<table>
<thead><tr><th>Caso</th><th>Modelo</th><th>Mercado</th><th>Gap (u)</th><th>Gap (%)</th><th>Retraso (días)</th><th>Severidad</th><th>Máxima</th><th>Estado</th><th>Etapa cuello</th></tr></thead>
<tbody>
$rows
</tbody>
</table>
```
`_ROW` = `<tr><td>$case_id</td><td>$modelo</td><td>$mercado</td><td>$gap_unidades</td><td>$gap_pct</td><td>$retraso_dias</td><td>$severity</td><td>$maximum</td><td>$estado</td><td>$etapa_cuello</td></tr>`.

`_ALERT`:
```
<nav><a href="index.html">Índice</a></nav>
<h1>$title</h1>
<p>Snapshot: $snapshot_id</p>
$notice
```
`$title` = `Alerta inmediata · <case_id>`.

`_INDEX`:
```
<h1>Informes y alertas</h1>
$entries
```
`$entries` = `<ol class="timeline">`, the entry lines, `</ol>`; or `<p class="empty">Sin informes ni alertas</p>`. `_ALERT_ENTRY` = `<li><a href="$href">$snapshot_id · Alerta inmediata · $case_id</a> $badge</li>`; `_REPORT_ENTRY` = `<li><a href="$href">$snapshot_id · Informe de turno $turno_id</a> · Novedades: $news · Casos activos: $active</li>`. Page title `Informes y alertas`.

### `main` (html branch)
`runner/cli.py`:
- `@dataclass(frozen=True) class HtmlOptions` (no fields; docstring "The parsed 'html' command line.").
- `parse_args(argv) -> RunOptions | TraceOptions | HtmlOptions`: adds `html` (help "render the stored reports and alerts as HTML pages"); `_HTML_COMMAND = "html"`.
- `_html(settings: Settings) -> int`, in order:
  1. `policy` from `load_shifts(settings.plant_dir / _SHIFTS_FILE)`, `heldout_first_shift`, `heldout_open`;
  2. `items = read_deliverables(settings.registry_path)`;
  3. `shown, omitted = select_shown(items, policy)` (from `notify.html`);
  4. `pages = render_site(shown)` (ids validated, names unique, bytes encoded; nothing written yet);
  5. `write_atomic(settings.html_dir / page.name, page.data)` per page, in order (index last);
  6. `omitted > 0` → stderr `html: <k> held-out or unverifiable items omitted (HELDOUT_OPEN=false)` through `write_safe`;
  7. `write_safe(f"html: shift reports {r}, alerts {a}, in {settings.html_dir}\n", sys.stdout)`, return 0.
- `main`: `isinstance(opts, HtmlOptions)` → `_html(settings)` inside `except (DataLoadError, ValueError, OSError, sqlite3.Error)` → `_fail` (2). No logging setup, no key check. The docstrings of the module and `main` mention `html`.
- `_fail(message: str) -> int`: `write_safe(message + "\n", sys.stderr)` (looked up at call time), return 2 (I12). Same text as `print(..., file=sys.stderr)` for ASCII.
- New imports: `notify.atomic.write_atomic`, `notify.html.render_site, select_shown`. All within 012 R11.

### Test builders
`tests/html_builders.py` (imports `from notice_builders import ...`):
- N_SE, N_PB (built with `Notice(...)` directly: `make_notice` fixes origin and evidence), ROW_SE, ROW_PB, REPORT_T05, A1, EMPTY_T06 as in the spec;
- `GOLDEN = Path(__file__).resolve().parent / "fixtures" / "html"`; `golden(name) -> str` reads UTF-8 with `newline=""` so LF is kept (the golden files hold the CSS verbatim);
- `rendered(settings, capsys) -> tuple[int, str, str]`: `main(["html"], deps=cli_deps(settings, None))` with captured streams, like `traced`.

## Data flow
```
argv → parse_args → HtmlOptions
settings → turnos.csv → HeldOutPolicy
registry.sqlite3 (mode=ro) → read_deliverables → (Notice | ShiftReport)[] in (seq, idx) order
→ select_shown (_shown_ids ∩ refused sets; unverifiable ids when closed) → kept[], omitted k
kept[] → render_site (validate_ids all → unique names → pages, index last → UTF-8 bytes) → write_atomic each → html/
k > 0 → stderr; counts → stdout
```

## Design notes
- **Why post-run, not an adapter (Q-84).** The index depends on every earlier delivery, which a per-item `Notifier` does not see; the outbox retries a whole item on any channel failure, so a template bug would stall delivery; and the run path stays frozen for the held-out run. The renderer's functions take domain types, so a future adapter can call them.
- **Escape by default (I4).** `_fill` escapes every plain `str`. Only `Markup` passes through, and only template output is `Markup`. A value can be double-escaped by mistake (visible in the goldens) but never left raw. Enums are `str` subclasses, so they are escaped too.
- **Order: controls, then HTML (Q-87).** `escape_controls` first makes control characters visible text; `html.escape` then handles `&<>"'`. Neither output contains what the other escapes, so the order changes nothing today, but it is fixed so the choke point has one definition.
- **Ids in names and links (I5, I6).** Only validated ids reach a file name, so no `..`, `/` or `\` can. `quote(name, safe="")` makes the `href` ASCII; the result is then escaped like any value (a no-op for `quote` output). `[0-9]` instead of `\d` keeps Arabic-Indic digits out.
- **Filter before validation (R12).** An `UnsafeId` message names a value; filtering first means it can only name a shown item.
- **Unverifiable means omitted while closed (O9).** The held-out check compares ids with the refused sets; a malformed id (`../T06`) would match nothing and slip through, then its error would print it. With the guard closed such an item is omitted and counted; with it open nothing is secret, so the error (exit 2) is the useful answer.
- **Why `select_shown` lives in `notify/html.py` (O8, I7).** It needs `_shown_ids` and `validate_ids`, both renderer knowledge, and `HeldOutPolicy`, a domain type; keeping it there makes E9 a pure unit test and leaves `cli.py` as composition only.
- **Whole-item omission (Q-91).** Showing part of a report would contradict the report the system delivered. An item at an allowed snapshot normally shows only allowed ids (logbook availability, Q-01), so whole omission costs nothing in practice; E9 pins the rule with synthetic items.
- **Render, encode, then write (I10, F3).** Validation, duplicate and encoding errors all happen inside `render_site`, so none writes anything; the index last means a partial write `OSError` never links a missing page.
- **`_fail` through `write_safe` (I12).** An error message may carry a stored value (`UnsafeId`, the encoding error); on a `cp1252` stderr a `print` would raise inside the error path.
- **No timestamp, no path in pages (Q-95).** Byte-identical re-renders make the golden and E11 checks meaningful and keep diffs clean.
- **Why `escape_controls` moves to `domain` (I2).** `notify` may import only `domain`; a copy would let the two escapers drift. `domain/text.py` is pure and imports nothing.
- **Dependency rule additions** (docs, T8): "`notify/html.py` and `notify/atomic.py` import only `domain`"; "`domain/text.py` holds `escape_controls`, shared by `telemetry/trace_render.py` and `notify/html.py`".

## Test strategy
- **Unit, renderer** (`tests/unit/notify/test_html_render.py`, new): E1–E9 and E15 a. E2 compares `render_report`'s `str` with the golden text; E5 compares `Page.data` with the golden bytes; E3, E4, E6, E7 are structural; E8 and E9 are parametrized where they have variants. E9 builds its policy with `HeldOutPolicy.from_calendar(plant_shifts(), ...)`; no I/O beyond the fixture `turnos.csv`.
- **Unit, settings** (`tests/test_config.py`, existing): E10.
- **CLI integration** (`tests/integration/test_cli_html.py`, new): E11–E14 and E15 b over `copied` TH_DIR (module-scoped `thresholds_dir` from `trace_builders`), `isolate_settings_env` and `capsys` (E14 replaces `sys.stderr` with a `cp1252` wrapper through `monkeypatch`). E13 is parametrized.
- The import boundary is already enforced by the `notify` scan in `tests/unit/test_import_boundaries.py`; `domain/text.py` joins the E18 leaf list (O11); no new test function.
- Basenames checked unique: `test_html_render.py`, `test_cli_html.py`. Every test cites its spec id.

## Risks
- **The golden drifts from the templates.** The test-writer writes the goldens by hand from the spec blocks and the plan's `CSS`, before any code exists, never by running the renderer. A mismatch is fixed in the code, or in the spec with the user.
- **Pre-commit rewrites a golden.** `end-of-file-fixer`, `trailing-whitespace` and `mixed-line-ending` run on `.html`. The templates have no trailing spaces and end with one `\n`, so the hooks are no-ops; `.gitattributes` keeps LF.
- **Non-ASCII file names on Windows/OneDrive.** `Sedán` in a file name works on NTFS and in browsers through the quoted `href`; E11 runs on both CI OSes.
- **CSS in both goldens (O13).** A CSS change edits both fixture files. Accepted for byte-exact goldens.
- **Held-out leak.** R12 filters before rendering and validation, and omits unverifiable ids while closed; E12 checks that no page holds a held-out id token.
- **mypy order.** See tasks.md: the refactors (T1) land before the renderer, `render_report` (T2) before the site functions and `validate_ids` (T4), those before `select_shown` (T10), and the setting (T5) before the CLI (T6).
