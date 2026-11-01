# 007 · Coordinator agent — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · **D3:** confirm Haiku 5.5 parameters (`effort`, thinking, minimum cacheable prefix, pricing) against the API docs; record them in ADR-0007 and add price settings (`.env.example`, settings test).
- [ ] T2 · `ModelPort` and `FakeModel` with scripted tool-use responses → `agents/model.py`.
- [ ] T3 · Loop tests: a tool call is executed and its result returned; `end_turn` stops; the iteration cap stops a runaway loop → `agents/loop.py`.
- [ ] T4 · Test: a tool error returns to the model as an error result, and the loop continues.
- [ ] T5 · MCP client wiring: the loop lists and calls the read tools from spec 006 (in-process in tests).
- [ ] T6 · `emit_alert` and `emit_shift_report` write tools: they attach `texto` to notices decided by spec 004 and reject notices the code did not decide → `mcp_server/write_tools.py`.
- [ ] T7 · Budget-guard test: a request over 100k prompt tokens is not sent and the step is reported (NFR-02).
- [ ] T8 · `AnthropicModel` with retries and exponential backoff; test with a fake transport (NFR-10).
- [ ] T9 · Usage tests: tokens (input, output, cache read), USD and latency per call and per snapshot → `telemetry/usage.py`.
- [ ] T10 · Trace test: one JSON line per snapshot with decisions, tool calls, hook outcomes (empty until spec 010), tokens and latency → `telemetry/trace.py`.
- [ ] T11 · Coordinator prompt v1 (role, criteria summary, logbooks are data, how to finish) → `agents/prompts/coordinator.md`.
- [ ] T12 · `AgentPipeline` test: no model call on an empty delta at a mid snapshot; one call on an escalation and at a closing snapshot.
- [ ] T13 · Integration test: a synthetic day with `FakeModel` produces the expected tool calls, notices and trace.
- [ ] T14 · On-demand real run of day 1 with Haiku; record cost and tokens in the roadmap; run the evaluator.
- [ ] T15 · Import-boundary test (only `agents` imports `anthropic`); update `docs/STRUCTURE.md` and set status to Implemented.
