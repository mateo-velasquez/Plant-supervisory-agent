# 0008 · Series runner resilience: content-hash idempotency, unit of work, non-fatal anomalies

- **Status:** Accepted
- **Date:** 2026-11-01
- **Requirements:** FR-01, FR-02, FR-03, FR-04, FR-33, FR-40, NFR-04, NFR-10

## Context
The series is 61 arrivals for 60 snapshots (`S034` arrives twice) and must run with one command, unattended (brief week 6). The held-out days 8–10 run once, as-is, before anything is touched (brief week 5). A repeated snapshot must change nothing (FR-02), and a failed run must resume without reprocessing earlier snapshots (NFR-10). Real data may hold quirks the synthetic fixtures do not, and stopping a whole run for one odd unit would waste the single held-out run.

## Decision
1. **Idempotency by content hash, first version wins.** Each processed snapshot stores the SHA-256 of its file bytes, computed before parsing. A repeat with the same hash is skipped; a repeat with a different hash is never reprocessed and is reported as an anomaly (Q-10).
2. **Unit of work.** The runner calls the pipeline inside `ProcessedStore.processing(SnapshotCommit)`. A clean exit marks the snapshot processed together with its anomalies and new unit sightings; an exception marks nothing and stops the run with `RunAborted`. Spec 003 implements it as one SQLite transaction shared with the pipeline's writes (ADR-0003); side effects outside the database happen only after commit (Q-23).
3. **Fatal vs non-fatal input.** Problems that make the run wrong or impossible stop it: a missing file or an unknown snapshot (checked upfront, nothing processed) and a snapshot that fails to load mid-series (Q-21, Q-22). Quirks that leave the metrics computable are anomalies: logged as WARNING, listed in the run summary, and the run continues (`shift_mismatch`, `stage_entry_after_snapshot`, `unit_combination_changed`; Q-18 to Q-20).

## Alternatives considered
- **Dedupe by `snapshot_id` only:** misses a resent file with different content.
- **Last version wins:** would reprocess a snapshot whose effects (cases, notices) already exist.
- **Mark processed after the pipeline, outside its transaction:** a crash between both writes either repeats notices or loses a snapshot on resume.
- **Fail on every data quirk:** safest locally, but one unit could stop the unattended series and the single held-out run.
- **Skip snapshots that fail to load:** leaves a silent hole that reads as recovery and can drop a shift report.

## Consequences
- Positive: reruns are safe and resumable; the held-out run reports quirks instead of dying on them.
- Negative / risks: anomalies can be noisy (one per unit per snapshot). Every registry write for a snapshot must go through the store's connection; if the MCP server runs as a separate process (ADR-0007), its writes cannot join that transaction (Q-24).
- Follow-ups: spec 003 persists anomalies and unit identity; spec 004 delivers notices only after commit; spec 006 settles the MCP transport against the shared transaction (Q-24).
