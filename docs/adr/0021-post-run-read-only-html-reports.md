# 0021 · Post-run read-only HTML reports: standard-library templates, one escape point, CSP, held-out omission

- **Status:** Accepted
- **Date:** 2026-11-18
- **Requirements:** FR-26, FR-22, FR-25, FR-20, FR-40, NFR-04, NFR-06 (spec 014, Q-84–Q-95)

## Context
The plant manager reads shift reports and alerts as JSON files (`notices/informe_<turno>.json`, `alertas.jsonl`). A browsable view helps at a glance (US-05), but it adds no data: everything is already validated and stored in the registry outbox (FR-25, ADR-0010). FR-26 (pluggable channel, file plus console) is met by spec 004.

Constraints:
- the single held-out run must not be put at risk, so the `run` path stays untouched;
- an index needs the state of every earlier delivery, which a per-delivery notifier does not have;
- logbook fragments and agent texts are untrusted data (FR-20): a page must not run code or reach the network;
- `notify` imports only `domain`; no new dependency is wanted for a Could-priority spec;
- held-out data (FR-40, Q-37) must never be shown while the guard is closed.

## Decision
- **A separate post-run subcommand.** `plant-monitor html` reads the registry through the existing `read_deliverables(path)` (`mode=ro`, `(seq, idx)` order) and renders the whole set into `OUTPUT_DIR/html/` (`Settings.html_dir`): one page per report, one per alert and a timeline `index.html`. Writes are atomic per file, overwrite and never delete; the index goes last. It never builds `SqliteRegistry`, the model or the pipelines.
- **A pure renderer in `notify/html.py`**, importing only `domain`: functions from domain types to text and UTF-8 bytes, so an adapter could be added later without changing it. It also holds the held-out filter (`select_shown`, over `domain.calendar.HeldOutPolicy`), since it knows which ids each page shows. The subcommand in `runner/cli.py` (composition root) reads, calls the filter and the renderer, and writes. Every page is validated, rendered and encoded before the first write, so an error writes nothing.
- **Standard-library templates with one escape point.** `string.Template` constants; every interpolated value, enums included, goes through `escape_controls` (Q-81, moved to `domain/text.py`) and then `html.escape(quote=True)`. Escaping is the default: only template output (`Markup`) is inserted unescaped. File names and `href`s come only from ids validated by pattern, encoded with `urllib.parse.quote`; any other id stops the command with exit 2.
- **Defense in depth in the page shell.** Embedded CSS, no JavaScript, no external URL, `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'` as a `<meta>`, `charset=utf-8`. Severity is shown by colour class and by its text label.
- **Held-out omission.** With `HELDOUT_OPEN=false`, an item that would show any held-out snapshot or shift id is left out whole (page and index entry), and so is an item whose ids fail validation (it cannot be proven not held out); stderr gives the count in one line. With the guard open, an invalid id exits 2. Pages are byte-deterministic (no timestamp), so a re-render is byte-identical.
- **Error lines never crash.** `cli._fail` writes through `write_safe`, so an error message carrying a stored value is escaped on a narrow-encoding console (also for `run` and `trace`).

## Alternatives considered
- **An `HtmlNotifier` inside `CompositeNotifier`, behind the outbox:** the index needs every prior delivery; a render failure would stall the outbox (ADR-0010 retries the whole item); and it changes the `run` wiring right before the held-out run.
- **Jinja2:** autoescaping and nicer templates, but a new dependency for a handful of fixed pages; `string.Template` with one escape function is enough and easy to audit.
- **HTML pages for the 013 trace:** a second rendering of a complex view; each notice shows the copyable `plant-monitor trace <notice_id>` command instead.
- **Refuse on held-out data, as `trace` does (exit 2):** right for a single id, but a whole-set render would then fail on any registry that holds held-out items; omitting them with a visible count keeps the command useful and leaks nothing.

## Consequences
- Positive:
  - The run path and its tests are unchanged; the command can be run any time after (or during) a run, offline, on a copied `OUTPUT_DIR`.
  - A logbook cannot inject markup, scripts or terminal sequences into a page; the CSP blocks scripts and network loads even if escaping failed.
  - Golden-file tests pin the exact bytes; a re-render is byte-identical.
- Negative / risks:
  - Pages are not updated live; the user re-runs the command.
  - Stale pages from an earlier render are never deleted (only overwritten); the index links only the current set.
  - Labels are Spanish while code is English (precedent ADR-0020); the label strings are fixed in the plan.
- Follow-ups:
  - Spec 014 implements the renderer, the setting and the subcommand.
  - The held-out run's directory is rendered and reviewed by hand after that run, with the user's permission (014 last task).
