# 0018 · Full-series CLI: composition root, resume by output directory, held-out via settings, run summary

- **Status:** Accepted
- **Date:** 2026-11-14
- **Requirements:** FR-33, FR-36, FR-37, FR-40, NFR-02, NFR-03, NFR-05, NFR-10 (spec 012, Q-64–Q-70)

## Context
The full series (61 arrivals) must run with one command, unattended, and report its cost and duration (FR-36, FR-37). The Demo Day run is that command, paced for a live audience. The pieces exist:
- `run_series` already orders, deduplicates by content hash, commits each snapshot in one unit of work and stops with a resumable `RunAborted` (ADR-0008);
- the trace file and `run_totals` already cost every model call outside the loop (ADR-0014);
- the held-out guard is a product setting, `HELDOUT_OPEN` (Q-37).

Wiring lives today only in the eval scripts, each in a new timestamped directory, so a failed run cannot resume. The held-out days run once, as-is (FR-40). A late failure in that run must not force a restart from S001.

## Decision
- **One top-level composition root.** `runner/cli.py` (`plant-monitor run`) builds the concrete adapters: registry, model, trace writer and notifiers. It calls `build_agent_pipeline` as the agent sub-assembly, which builds the tool servers and the logbook store. Its options are `--thresholds-only`, `--until <snapshot>` and `--speed <seconds>`, with an injectable model factory, sleep and clock. `series.py` is unchanged: `--until` truncates the arrivals, and pacing is a post-commit step.
- **Resume by output directory (Q-69).** A run lives in `OUTPUT_DIR` (registry, traces, notices, summaries). Running again with the same directory resumes at the first snapshot not yet committed; a fresh run uses a new directory. A directory that holds agent-mode traces stays in agent mode (Q-71): `--thresholds-only` is refused there. The threshold pipeline has no cause ledger, so it would drop an agent raise in force (§3, §5).
- **Held-out via settings only (Q-65).** Closed reads S001–S042 through the streaming loader; open reads every arrival. There is no CLI flag.
- **Run summary (Q-66, Q-67).** Each invocation prints and writes a JSON summary under `OUTPUT_DIR/runs/`. It has two scopes:
  - **run:** this invocation's trace, its duration and arrivals, and the steps that hit the prompt budget;
  - **series:** every trace file in the directory, so aborted lines count, plus reports and alerts from the registry.

  The summary only sums totals that telemetry already computed, and it never sees prices.
- **The API key is optional (Q-68).** Threshold-only mode needs none. Agent mode without a key fails before reading data.
- **The first full real run is the held-out run (Q-64).** The user runs it once, after the paid days 1–7 run.

## Alternatives considered
- **Timestamped run directory plus `--resume <dir>`:** more flags, and it duplicates the output paths `Settings` already derives.
- **A `--heldout` flag:** a second guard next to `HELDOUT_OPEN`, against Q-37.
- **Cost of the current invocation only:** a resumed full run would under-report the series cost that NFR-03 asks to measure.
- **Abort the run when a step exceeds the prompt budget:** against ADR-0014; the guard already avoids the 5× request, and the summary makes it visible.
- **Reuse the eval scripts as the CLI:** they create a new directory per run and cannot resume. Changing them before the paid days 1–7 run would also put that gate at risk.

## Consequences
- Positive:
  - The Demo Day run is one line.
  - A failed full run resumes where it stopped.
  - Cost and duration are comparable across runs.
  - CI exercises the whole command with `FakeModel` on synthetic fixtures.
- Negative / risks:
  - Mixing modes in one directory (threshold-only, then agent) skips everything already processed. The summary shows it (0 processed) and the README warns about it. The opposite order is refused (Q-71).
  - The eval scripts keep their own wiring.
- Follow-ups:
  - The held-out run records the full series' cost and duration in the README and the roadmap.
  - Spec 013 reads the same trace and registry for the navigable trace.
