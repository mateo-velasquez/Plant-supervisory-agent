# 010 · Guardrails and unattended run — Plan

## Modules

| File | Responsibility |
|---|---|
| `hooks/chain.py` | Chain of Responsibility: pre-tool, post-tool and on-stop guards; the first block returns its reason. |
| `hooks/allowlist.py` | Rejects tools outside the agent's list. |
| `hooks/floor.py` | Rejects severities below the minimum. |
| `hooks/novelty.py` | Rejects repeats without news (uses `cases/novelty.py`). |
| `hooks/completeness.py` | On stop: every active case is in the report. |
| `mcp_server/prompts.py` | Serves `criterio.md` as the `criteria` MCP prompt. |
| `agents/loop.py` | Calls the hook chain around every tool call and at stop. |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- The guards mirror the Claude Code hooks this repo already uses (ADR-0006), now in product code (Module 5).
- Allowlists live in `agents/factory.py` (spec 009) and are enforced here, in code.

## Test strategy
Unit tests per guard; integration with `FakeModel` scripting each violation; check the trace records the block.

## Risks
A guard that blocks a correct action would loop the agent: the iteration cap (spec 007) and the trace make it visible.
