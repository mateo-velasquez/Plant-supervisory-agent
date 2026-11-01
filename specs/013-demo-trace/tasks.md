# 013 · Alert trace for the demo — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Trace-query test (US-10): an alert at S020 shows its metrics, transition, citations, tool calls and hook decisions → `telemetry/trace_query.py`.
- [ ] T2 · Test: a threshold-only alert states that no agent was involved.
- [ ] T3 · `plant-monitor trace <notice_id>` subcommand with a rendering test.
- [ ] T4 · Pick the demo alert from the real full run (spec 012) and check its trace by hand against `criterio.md`.
- [ ] T5 · Demo script with steps, timings, live command (`--speed`) and a recorded fallback → `docs/demo.md`.
- [ ] T6 · Full rehearsal; fix what it reveals; set status to Implemented.
