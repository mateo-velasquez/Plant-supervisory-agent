# 002 · Series runner — Spec

- **Status:** Draft
- **Requirements:** FR-01, FR-02, FR-04, NFR-10
- **Stories:** US-01
- **Week:** W1

## Goal
Replay the series in the order of `llegadas.csv`, hand each new snapshot to the processing pipeline exactly once, and tell the pipeline which shift the snapshot belongs to and whether it closes it.

## Scope
- In: loading `llegadas.csv`; snapshot → shift mapping (mid or closing); idempotency with a content hash; the run loop over an injected pipeline; a run summary.
- Out: the SQLite store for processed snapshots (spec 003 implements the protocol defined here); the pipeline itself (spec 004); the CLI (spec 012).

## Behavior
- Arrivals are processed in ascending `orden` (FR-01). `recibido` is informative only.
- Each snapshot maps to exactly one shift through `turnos.csv`: it is either that shift's `snapshot_medio` or its `snapshot_cierre` (FR-04). The snapshot's own `turno` field must agree; a mismatch is a data error.
- A snapshot already processed is skipped with no side effects, and the run log records `"<id> skipped: already processed"` (FR-02).
- Every processed snapshot stores a content hash. A repeat with a different hash is not reprocessed; it is logged and reported as an anomaly (Q-10).
- A snapshot is marked processed only after the pipeline succeeds. If the pipeline fails, the run stops and the next run resumes at that snapshot (NFR-10).
- The time reference handed to the pipeline is the snapshot `timestamp`, never the wall clock.

## Worked examples
To be written when the spec moves to Ready. Seeds: US-01 scenarios (order S001 → S003, S034 repeated, closing S002 of T01), a repeat with a different hash, and a failure at the third snapshot followed by a resume.

## Edge cases and assumptions
- **Q-10:** the first processed version of a snapshot wins.
- A snapshot listed in `llegadas.csv` but missing on disk is a data error that names the file.
- Missing snapshots in the series (FR-42) are out of scope here.

## Acceptance
- [ ] Every rule above has a passing test.
- [ ] `ruff`, `mypy --strict` and `pytest` pass.
- [ ] `docs/STRUCTURE.md` updated.
