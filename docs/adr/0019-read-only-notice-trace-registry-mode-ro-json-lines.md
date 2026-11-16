# 0019 · Read-only notice trace: registry read `mode=ro` plus JSON lines, no schema change

- **Status:** Accepted
- **Date:** 2026-11-14
- **Requirements:** FR-25, FR-38, FR-40, NFR-09 (spec 013, Q-72–Q-83)

## Context
The Demo Day shows the trace of one alert: the snapshot where it fired, the reason and the logbook quote (FR-38, US-10). Every piece is already stored:
- the registry holds the notice (`motivo`, `origen`, `causa`, `evidencia`), the case history rows (metrics and states), the active causes with their links and citations, and the processing order;
- the trace files under `output_dir/traces/` hold, per snapshot, the agents that ran, their tool calls, the hook blocks and the costed totals (Q-44).

ADR-0014 kept the trace as JSON lines and left open whether to move it into the registry if spec 013 needed queries. `SqliteRegistry` creates or migrates its file when it opens, so opening it is a write. `telemetry` may import only `domain`, and `cases` may not import `telemetry`. The trace must also respect the held-out guard (Q-37) and treat logbook text as data (FR-20).

## Decision
- **No schema change (Q-82).** Traces stay JSON-lines files, and the registry schema stays at v4. A resumed run's files are all read: the committed line of a snapshot wins, and its aborted lines are listed (Q-76).
- **A second read-only registry reader (Q-72).** `cases/registry/notice_reader.py` (`read_notice`) sits next to the writers, like `read_deliverables` (ADR-0011). It opens the file with `?mode=ro`, never builds `SqliteRegistry`, checks only the tables and columns it needs (no whole-schema version check), does every read inside one read transaction, and returns domain types: a `StoredNotice` (`domain/stored.py`) or the stored `ShiftReport`.
- **A pure join and renderer in `telemetry`.** `telemetry/trace_query.py` (`build_notice_trace`) joins the registry's domain types with `TraceLine`s. `telemetry/trace_render.py` renders the text and escapes control characters on every line (Q-81). Both import only `domain` and `telemetry`. `TraceFile` and `read_trace_files` live in `telemetry/trace.py` and also feed the run summary.
- **The subcommand in the composition root (ADR-0018).** `plant-monitor trace <notice_id>` in `runner/cli.py` reads settings, applies `HeldOutPolicy` before it reads any trace and again over everything shown (Q-79), and exits 0, 1 or 2 (Q-78). It never builds the model, the pipelines or the ledger.

## Alternatives considered
- **Trace rows in the registry (schema v5):** queries would be easy, but it is a migration right before the single held-out run, to serve one lookup per notice.
- **Open `SqliteRegistry` to read:** it can create or migrate the file, so a read could become a write. A trace command must never touch the run's data.
- **Join in `runner`:** it works, but it moves logic into the composition root and widens `runner/summary.py`'s neighbours. Join in `telemetry` keeps the core testable without SQLite.
- **`telemetry` imports `cases`:** breaks the dependency rule that keeps `telemetry` a leaf over `domain`.
- **Rerun the model to explain a notice:** costs money and can give a different answer from the one stored. FR-38 asks for a reconstruction.

## Consequences
- Positive:
  - The trace changes nothing in the run's directory: `mode=ro` cannot write.
  - Old registries and old trace lines stay readable (no version check, optional trace fields).
  - The demo trace runs offline from a copied `OUTPUT_DIR`, which is also the fallback.
- Negative / risks:
  - `apply_proposal` stores only the proposal id, so the link from a raise to its proposal is rebuilt. The traced proposals are parsed into domain types; only successful applies count; the match is on scope, category and citation, cross-checked with the cause id's ordinal (`<S>-causa-k`). Zero or several candidates show "no matching proposal", never a guess.
  - Tool calls and hooks are stored per snapshot, not per notice. The trace shows them all and marks only the calls that name the case.
  - The storage format now has two read-only readers outside the runner (`read_deliverables`, `read_notice`).
- Follow-ups:
  - Spec 013 implements the reader, the view, the renderer and the subcommand.
  - The demo alert is chosen from the held-out run's directory (013 T4), with the user's permission.
