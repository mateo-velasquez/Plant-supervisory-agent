# 006 · Logbook store and MCP server — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Synthetic logbook fixtures and loader tests (UTF-8, ID from file name) → `logbooks/store.py`.
- [ ] T2 · Availability tests (Q-01): at S001 none, at S002 T01, at S003 T01; `get` on a shift not yet closed raises.
- [ ] T3 · Verbatim tests (Q-12): exact fragment passes, whitespace and line-break differences pass, a paraphrase fails with "fragment not found in Txx".
- [ ] T4 · Delimiting test (US-08): rendered logbooks are wrapped as quoted data with their ID → `logbooks/render.py`.
- [ ] T5 · Settle the MCP transport and where the client is imported; update ADR-0007 and `docs/STRUCTURE.md`.
- [ ] T6 · MCP server skeleton with an in-process test client; a ping-style test → `mcp_server/server.py`.
- [ ] T7 · `get_deviations(snapshot_id)` returns the 9 compact metric rows → `mcp_server/read_tools.py`, `views.py`.
- [ ] T8 · `get_active_cases()` and `get_case(case_id)` (history plus last reported state and severity).
- [ ] T9 · `list_available_logbooks()` and `get_logbook(turno_id)`; a tool error for shifts not yet closed.
- [ ] T10 · `get_delayed_units(modelo, mercado)`: compact detail for the bottleneck and shipment analysts.
- [ ] T11 · Size-budget test per view, with the limit from `Settings` (`.env.example` and settings test).
- [ ] T12 · Import-boundary test (only `mcp_server`, plus the client location chosen in T5, imports `mcp`); update `docs/STRUCTURE.md`, the roadmap tool inventory, and set status to Implemented.
