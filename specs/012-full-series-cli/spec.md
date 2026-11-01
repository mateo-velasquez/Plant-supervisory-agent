# 012 · Full-series CLI — Spec

- **Status:** Draft
- **Requirements:** FR-33, FR-36, FR-37, NFR-02, NFR-05, NFR-10
- **Stories:** US-11
- **Week:** W6

## Goal
Run the whole series (61 arrivals) with one command, unattended, and report its cost and duration, so runs are reproducible and comparable, and the Demo Day run is a single line.

## Scope
- In: CLI entry point and options; full-run summary (tokens, USD, time); resume; demo pacing; the recorded full run.
- Out: the trace viewer (spec 013).

## Behavior
- One command processes the 61 arrivals in order and produces 30 shift reports, with no manual steps (FR-36, FR-33).
- At the end it reports input, output and cache-read tokens, cost in USD and duration, and writes them under `output_dir` (FR-37).
- A run that failed at a snapshot resumes there without reprocessing earlier ones (NFR-10).
- Options: threshold-only mode (no model), `--until <snapshot>`, and `--speed <seconds>` to pace snapshots for the live demo.

## Worked examples
To be written when the spec moves to Ready. Seeds: the four US-11 scenarios.

## Edge cases and assumptions
- The held-out days are part of the full run after W5: running is not tuning (ADR-0006).

## Acceptance
- [ ] Every rule above has a passing test with `FakeModel` on a synthetic series.
- [ ] One full real run recorded: cost and time in the README.
- [ ] README "How to run" updated.
