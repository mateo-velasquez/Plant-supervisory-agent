# 007 · Coordinator agent — Spec

- **Status:** Draft
- **Requirements:** FR-27, FR-37, FR-38, NFR-01, NFR-02, NFR-09, NFR-10
- **Stories:** US-10 (trace data), US-11 (budget guard)
- **Week:** W1–W2

## Goal
Put a single agent, the coordinator, in the loop: for each snapshot with something to judge, it reads what changed through the MCP tools and writes the notice text, while code keeps every number and state. Every call is costed and traced.

## Scope
- In: own agent loop (ADR-0007); model port with a fake for tests; MCP client wiring; write tools `emit_alert` and `emit_shift_report` (text only); prompt-budget guard; retries; token and cost accounting; trace log; coordinator prompt v1; when to call the model.
- Out: causes and escalations (spec 008); analysts (spec 009); hooks (spec 010); structured output and caching (spec 011).

## Behavior
- The model is called only when the snapshot has a non-empty delta (new, escalated or resolved case; bottleneck without cause) or is a closing snapshot. Otherwise nothing is sent (silence costs nothing).
- The coordinator receives the delta plus snapshot context, calls read tools, and finishes with `emit_alert` or `emit_shift_report`. The notice skeleton (which cases, severities, states) comes from spec 004; the agent supplies `texto` only.
- Tool errors return to the model as error results, so it can correct itself.
- Before each request, prompt tokens are counted; above the 100k budget the request is not sent and the run reports the step (NFR-02).
- API errors retry with exponential backoff (NFR-10). The loop has a maximum number of iterations.
- Each call records input, output and cache-read tokens, cost in USD and latency (FR-37), and each snapshot has a trace: decisions, tool calls, tokens, latency (NFR-09, FR-38).
- Model `claude-haiku-5-5` with thinking on; `effort` from settings (NFR-01).

## Worked examples
To be written when the spec moves to Ready. Seeds: an empty delta at a mid snapshot (no call), an escalation at S020 (one alert with model text), and an oversized request (blocked and reported).

## Edge cases and assumptions
- D3 (roadmap): confirm `effort`, thinking, minimum cacheable prefix and pricing against the current API docs before Ready.

## Acceptance
- [ ] Integration test over a synthetic day with a fake model produces the expected tool calls and notices.
- [ ] One real day (day 1) runs on demand with Haiku, and its cost is recorded.
- [ ] `ruff`, `mypy --strict` and `pytest` pass; `docs/STRUCTURE.md` and ADR-0007 updated.
