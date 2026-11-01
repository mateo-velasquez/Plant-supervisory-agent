# 006 · Logbook store and MCP server — Plan

## Modules

| File | Responsibility |
|---|---|
| `logbooks/store.py` | `LogbookStore`: load `Txx.txt`, `available_until(snapshot)`, `get(turno_id, at)`, `contains_verbatim(turno_id, fragment)`. |
| `logbooks/render.py` | Wrap a logbook as delimited, quoted data with its ID. |
| `mcp_server/server.py` | Server built with the `mcp` SDK; registers tools; transport selection. |
| `mcp_server/read_tools.py` | The six read tools. |
| `mcp_server/views.py` | Compact views (metrics rows, case summaries, delayed units). |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- `mcp_server` depends on `cases`, `metrics` and `logbooks`, never the reverse (dependency rule).
- Decide where the MCP **client** lives (ADR-0007 follow-up): either `agents` may import the `mcp` client, or a thin client adapter sits in `mcp_server/client.py`.

## Test strategy
Unit tests for the store with synthetic logbooks; tool tests through an in-process client; a size-budget test per view.

## Risks
Views that leak whole snapshots would blow the token budget: the size-budget test guards it.
