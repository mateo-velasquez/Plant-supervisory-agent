# 0021 · Local read-only live dashboard with replay

- **Status:** Accepted
- **Date:** 2026-11-20
- **Requirements:** FR-22, FR-23, FR-25, FR-31, FR-37, FR-38, FR-40, FR-20, NFR-06, NFR-07, NFR-09 (spec 014, Q-84–Q-100)

## Context
The plant manager needs to see the run as it happens and to replay it for the demo, including what the agents did per snapshot. Static post-run HTML pages were built on the spec branch and rejected for their look before merge; a prototype with JavaScript was approved.

Constraints:
- the run path and the single held-out run must not be put at risk: the dashboard only reads;
- logbook fragments and agent texts are untrusted data (FR-20): a page must not run them as code or reach the network;
- held-out data (FR-40, Q-37) must never be shown while the guard is closed;
- no new dependency for a Could-priority spec.

## Decision
- `plant-monitor dashboard` serves a local dashboard on `127.0.0.1:DASHBOARD_PORT` with the standard-library `http.server`. It reads `OUTPUT_DIR` only: the registry with `mode=ro` in one transaction and the trace files. It never calls the model or writes anything.
- Endpoints are stateless and take an optional `at=<seq>`. The client owns live polling and replay, and syncs the Agentes window over `BroadcastChannel`.
- Python builds every rule-bearing view. The frontend is small hand-written JS with no framework, library or build step, and inserts values only as text nodes. A test checks for the forbidden sinks.
- Every response sends `Content-Security-Policy: default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'`, `X-Content-Type-Options: nosniff` and `Cache-Control: no-store`. The server accepts GET only, serves an explicit asset allowlist and checks the `Host` name (DNS rebinding, Q-98).
- With `HELDOUT_OPEN=false`, held-out and unverifiable items are omitted and counted.
- The frontend lives in `src/frontend/`, outside the `plant_monitor` package. It does not ship in a wheel; the project runs from the repo with `uv run`, and startup fails if the assets are missing.

## Alternatives considered
- **Static post-run HTML pages** (the first design of this spec): rejected for their look and because they do not update live.
- **React or another framework:** a build step and dependencies for two small windows.
- **A server-held replay position:** needs a write endpoint; the dashboard must not write.

## Consequences
- Positive:
  - No new dependency; the run path is unchanged.
  - A finished run can be replayed any number of times with the agents' real texts and decisions, without calling the model.
- Negative / risks:
  - The JS is covered only by the sink scan and manual review.
  - A registry or trace schema change must update `run_reader` and the read model.
- Follow-ups:
  - The dashboard is reviewed by hand on a real run's `OUTPUT_DIR`, with the user's permission (014 T14).
