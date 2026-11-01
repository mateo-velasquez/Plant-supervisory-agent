# 007 · Coordinator agent — Plan

## Modules

| File | Responsibility |
|---|---|
| `agents/model.py` | `ModelPort` protocol, `AnthropicModel` (retries, token counting) and `FakeModel` (scripted). |
| `agents/loop.py` | Agent loop: send, run tool calls, return results, stop conditions. |
| `agents/factory.py` | Builds the coordinator with its prompt and tool list. |
| `agents/prompts/coordinator.md` | System prompt v1. |
| `mcp_server/write_tools.py` | `emit_alert`, `emit_shift_report` (text only; skeleton from spec 004). |
| `telemetry/usage.py` | Token and cost accounting; prices from settings. |
| `telemetry/trace.py` | Per-snapshot trace log (JSON lines under `output_dir`). |
| `runner/pipeline.py` | `AgentPipeline`: threshold pipeline plus the coordinator when there is something to judge. |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- Only `agents` imports `anthropic` (dependency rule).
- `FakeModel` lets CI test the loop without network (NFR-07).
- Write tools fill text into notices the code already decided; they never decide which notices exist.

## Test strategy
Unit tests for the loop with `FakeModel`; integration over a synthetic day; an on-demand real run of day 1 (an eval, not a test).

## Risks
Haiku may loop on tool calls: the iteration cap and the trace make it visible.
