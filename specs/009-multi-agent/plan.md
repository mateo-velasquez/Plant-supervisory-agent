# 009 · Multi-agent with a single writer — Plan

## Modules

| File | Responsibility |
|---|---|
| `agents/roles.py` | Role definitions: prompt, tool list, output schema per analyst. |
| `agents/orchestrator.py` | The coordinator calls analysts (as tools or sub-loops) and merges their findings. |
| `agents/factory.py` | Builds every agent with its prompt and tool list. |
| `agents/delta.py` | Builds the per-snapshot delta from the registry. |
| `agents/prompts/*.md` | One prompt per analyst. |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- Pattern to decide in ADR-0009 (orchestrator-workers is the working assumption, per Module 4).
- Alternative for ADR-0009: hybrid. Code picks the analysts from the delta (escalated by delay → shipment risk; bottleneck without cause → cause investigator; gap → gap analyst) and runs them in parallel; the coordinator only merges findings and writes. Cheaper and more predictable than letting the LLM choose, since the subtasks are known from the delta beforehand (Module 4: orchestrator-workers fits subtasks discovered at runtime).
- Analysts return structured findings, not prose, so the coordinator merges them without re-reading data.

## Test strategy
`FakeModel` per role; an integration test of one snapshot through every role; on-demand real run of days 1–7.

## Risks
Calling every analyst on every snapshot multiplies cost: the coordinator calls only the ones the delta needs.
