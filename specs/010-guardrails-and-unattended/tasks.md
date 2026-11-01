# 010 · Guardrails and unattended run — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Hook-chain tests: guards run in order, the first block wins, and the reason reaches the model as a tool error → `hooks/chain.py`.
- [ ] T2 · Loop integration: the chain runs before and after every tool call and on stop (`agents/loop.py`).
- [ ] T3 · Allowlist test (US-09): an analyst calling a write tool is rejected before reaching the MCP server → `hooks/allowlist.py`.
- [ ] T4 · Floor test (US-09): minimum `alta`, notice at `media` → "below minimum severity (alta)" → `hooks/floor.py`.
- [ ] T5 · Novelty test (US-09): a case reported at `alta` in `en_seguimiento`, re-reported unchanged → "no news since last report" → `hooks/novelty.py`.
- [ ] T6 · Completeness test (US-09): 3 active cases, a report with 2 → blocked on stop, naming the missing case → `hooks/completeness.py`.
- [ ] T7 · Trace test: every block is recorded with guard, reason and tool call.
- [ ] T8 · Criteria MCP prompt: the server serves `criterio.md`, and the coordinator loads it as system context → `mcp_server/prompts.py`.
- [ ] T9 · Unattended test: a synthetic two-shift series runs and closes both shifts with no manual step (FR-33).
- [ ] T10 · On-demand real run of one day; capture a real hook block for the demo.
- [ ] T11 · Update the snapshot-sequence and shift-close diagrams, `docs/STRUCTURE.md`, and set status to Implemented.
