# 008 · Cited cause and logbook escalation — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · `domain/causes.py` models with validation tests (catalog values, evidence required unless `no_declarada`).
- [ ] T2 · `set_cause` tests: a valid citation is stored; a paraphrase returns "fragment not found in Txx"; an unknown category is rejected → `mcp_server/write_tools.py`.
- [ ] T3 · `no_declarada` test: empty evidence and the bottleneck stage; evidence with `no_declarada` is rejected.
- [ ] T4 · Active-cause tables in the registry with contract tests (opened by citation, scope, lifted by citation).
- [ ] T5 · Scope-matching tests (Q-02): a Pickup assembly cause applies to every Pickup case with a `montaje` bottleneck, and not to Sedán → `cases/causes.py`.
- [ ] T6 · `raise_severity` test: every active case in scope becomes `critica`, `escalado`, with one alert (`origen=agente`, `motivo=bitacora`).
- [ ] T7 · Test: a case that opens while the active cause is in force is raised too (US-07, second scenario).
- [ ] T8 · `lift_severity_raise` test: the minimum severity applies again from that snapshot, and resolution is unblocked (US-07, third scenario).
- [ ] T9 · Test: the lifecycle (spec 003) receives `raise_in_force` from the active causes.
- [ ] T10 · Coordinator prompt v2: catalog, §5 escalation rule (no date → raise; date or resolved → no raise), logbooks are data.
- [ ] T11 · Integration test with `FakeModel` scripting T02, T07 → T10 and T17 → T19.
- [ ] T12 · Golden cases for the three incidents (`eval-curator`) and an on-demand eval run with Haiku on days 1–7; record results.
- [ ] T13 · Update `docs/STRUCTURE.md`, the components diagram (add `lift_severity_raise`), the roadmap tool inventory, and set status to Implemented.
