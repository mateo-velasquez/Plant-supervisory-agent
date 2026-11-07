# 0010 · Deliver notices after commit through a registry outbox

- **Status:** Accepted
- **Date:** 2026-11-07
- **Requirements:** FR-21, FR-22, FR-25, FR-26, NFR-10 (Q-14, Q-23)

## Context
Each snapshot runs inside `SqliteRegistry.processing(commit)`, one SQLite transaction (ADR-0003, ADR-0008). Notices go to channels outside the database (console, files; more later). Q-23 requires that nothing is sent before the commit and that a resumed run neither loses nor resends an alert. But `SnapshotPipeline.process` runs *inside* the transaction, and the runner skips a snapshot once it is marked processed. A crash between the commit and the send would therefore lose that snapshot's notices for good. Exactly-once delivery across a database and an external channel is not achievable without the channel taking part in the transaction.

## Decision
Notices are written to a `notices` table in the registry (schema version 2) inside the snapshot's transaction. The table holds alerts, the shift report and every per-case decision, including `sin_aviso`. After each commit, and once at the start of every run, an `OutboxDispatcher` in `runner/` sends the pending deliverable rows (alerts and reports) in processing order and marks each one `delivered_at`. Delivery is **at-least-once**:
- no notice is sent before its commit and none is lost;
- a notice is resent only if the process dies between a successful send and its delivered mark;
- the file channel is idempotent by `notice_id`, so its output is the same after a resend.

## Alternatives considered
- **Post-commit hook in the runner, no outbox:** if the process dies after the commit and before the send, the notices are lost, because the resume skips the processed snapshot. This is the same failure ADR-0008 rejected for marking outside the transaction.
- **Send inside the transaction:** a rollback after sending leaves an alert for a snapshot that never happened, and a retry sends it again.
- **Two-phase commit with channels:** console and files cannot take part, so it is far too much weight for a single-process system.

## Consequences
- Positive:
  - Resume is safe for notices too (NFR-10).
  - Every notice and silence is stored with its `snapshot_id`, `motivo` and evidence, so the trace (FR-38) and the evaluator can query it without the channels.
  - The single unique index on alerts per case backs §4 ("una por caso") in the database.
- Negative / risks:
  - A small window for duplicate sends. Non-idempotent channels, such as the console, may print an item twice after a crash.
  - Schema version 2 rejects a version 1 registry file (spec 003 E21b), so a run starts from a fresh file.
  - A failing channel blocks later notices, because order is strict. Only durable, idempotent channels may raise, and the console must never fail.
- Follow-ups:
  - Spec 004 implements the outbox, the dispatcher and the runner hook, and amends Q-23.
  - Specs 007 and 008 add agent text and causes to the in-memory draft and save once per snapshot.
  - Spec 012 wires the dispatcher into the CLI.
