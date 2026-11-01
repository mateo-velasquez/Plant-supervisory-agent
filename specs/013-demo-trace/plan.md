# 013 · Alert trace for the demo — Plan

## Modules

| File | Responsibility |
|---|---|
| `telemetry/trace_query.py` | Rebuild a notice's trace from the registry and the trace log. |
| `runner/cli.py` | `plant-monitor trace <notice_id>` subcommand. |
| `docs/demo.md` | Demo script: steps, timings, chosen alert, fallback. |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
Read-only over stored data; no model calls.

## Test strategy
A synthetic run with one threshold alert and one agent alert; snapshot tests of the rendered trace.

## Risks
Missing trace fields discovered on Demo Day: rehearse on the real full run from spec 012.
