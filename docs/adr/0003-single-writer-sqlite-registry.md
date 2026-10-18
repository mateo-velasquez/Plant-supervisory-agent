# 0003 · Case registry in SQLite with a single writer

- **Status:** Accepted
- **Date:** 2026-10-18
- **Requirements:** FR-02, FR-14, FR-28, FR-32, NFR-10

## Context
The registry must live outside the model, remember what was reported last, and survive reruns. A snapshot that arrives twice must change nothing, and a failed run must resume where it stopped. The brief requires a single agent writing to the registry.

## Decision
Use **SQLite** (Python standard library) behind a `Repository` interface. A `processed_snapshots` table makes ingestion idempotent; marking a snapshot processed shares the transaction with its writes. Only the coordinator's tool allowlist contains write tools, and the threshold-driven lifecycle writes from code before the agent runs.

## Alternatives considered
- **JSON files:** simple, but no transactions; a crash mid-snapshot leaves inconsistent state.
- **In-memory only:** no resume, no audit after the run.
- **PostgreSQL:** unnecessary operational weight for a single-process system.

## Consequences
- Positive: atomic per-snapshot updates, free resume, and a queryable history for traces and evals. Tests use an in-memory SQLite.
- Negative: a schema to maintain; migrations if the model changes.
- Follow-up: database file path goes into `Settings` (`OUTPUT_DIR`).
