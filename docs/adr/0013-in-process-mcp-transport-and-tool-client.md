# 0013 · In-process MCP transport, ToolClient adapter and in-unit-of-work writes

- **Status:** Accepted
- **Date:** 2026-11-08
- **Requirements:** FR-17, FR-27, FR-31, FR-32, NFR-03, NFR-07
- **Revises:** [ADR-0007](0007-own-agent-loop-with-mcp-client.md) (transport only; the own agent loop stands)

## Context
ADR-0007 left the MCP transport open: stdio in real runs and in-process in tests, to confirm in spec 006 (roadmap D2). It also left open where the `mcp` client may be imported, since the dependency rule lets only `mcp_server` import `mcp`. Q-24 asked how write tools reach the registry: the runner processes each snapshot in one unit of work (Q-23, ADR-0008), and SQLite has a single writer (ADR-0003). Spec 006's read tools read a per-snapshot frame (metrics, delayed units) and a registry whose cases the tracker may have opened earlier in the same, uncommitted, unit of work.

## Decision
- **Transport:** the MCP server runs in-process in real runs and in tests (the SDK's in-process client). Tools are registered as `async def` wrappers over pure sync functions, so they run on the runner's thread and use its SQLite connection.
- **Client:** a thin adapter `mcp_server/client.py` (`ToolClient`, with plain `ToolSpec` and `ToolOutcome`) is the only client of the server. `agents` never imports `mcp`; the allowlist (FR-32) and the hook chain (FR-31) wrap calls through it.
- **Writes (Q-24):** write tools (specs 007 and 008) write directly inside the runner's open unit of work, through narrow writer protocols held by the tool context.

## Alternatives considered
- **stdio subprocess in real runs:** a real process boundary, but the server would not see the uncommitted unit of work, so reads miss cases opened in the same snapshot and writes cannot join the transaction. Metrics would have to be recomputed or persisted in the subprocess. Too much cost for no project need.
- **`agents` imports the `mcp` client (`agents/mcp_client.py`):** shows the client more directly, but needs an exception to the dependency rule and gives agent-loop tests no plain test double.
- **Write tools return write requests the coordinator applies:** works with any transport, but a later `get_case` in the same loop would not see an earlier `set_cause`, and it adds a request type and an applier with no current need.
- **`check_same_thread=False` on the registry connection:** would let sync tools run in SDK worker threads, but a second thread would touch the runner's open transaction, against ADR-0003.

## Consequences
- Positive: tests run the production path; reads see the open unit of work; one process and one connection write (ADR-0003 holds); `agents` stays free of `mcp`, and the agent loop is tested against a fake `ToolClient`.
- Negative / risks: no process isolation between the agent loop and the server; a crashing tool runs in the runner's process (the SDK turns exceptions into tool errors).
- Follow-ups:
  - ADR-0007 is set to Accepted, with its transport sentence revised by this ADR.
  - Spec 007: entering a snapshot frame checks it matches the registry's current snapshot.
  - Specs 007 and 008 define the writer protocols for `emit_*`, `set_cause`, `raise_severity` and `lift_severity_raise`.
