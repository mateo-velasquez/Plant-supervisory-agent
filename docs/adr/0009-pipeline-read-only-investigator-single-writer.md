# 0009 · Code-driven pipeline: read-only cause investigator, code control and a single-writer coordinator

- **Status:** Accepted
- **Date:** 2026-11-11
- **Requirements:** FR-28, FR-29, FR-37, NFR-03 (Q-41 amended, Q-50–Q-54)

## Context
Spec 009 must choose a multi-agent orchestration pattern (FR-28), with a single agent writing to the registry (ADR-0003). Four forces shape it:
- Code already computes every rule in `criterio.md`: gap, delay, bottleneck, severity, lifecycle, novelty and alerts (ADR-0002). The only judgment code cannot make is reading free-text logbooks.
- The work splits into two tool families: judging untrusted text (logbooks becoming readable at a closing, Q-01) and writing texts over structured data (alerts and shift reports). Since 008 one coordinator does both: it reads raw logbooks and holds every write tool.
- The steps are known before any model call: `decide` already tells whether a logbook became readable and which notices need a text.
- Cost and testability: CI tests everything with `FakeModel` (NFR-07), and every request stays under 100k prompt tokens (NFR-02).

## Decision
A sequential pipeline driven by code, one pass per snapshot:
1. `decide` (code).
2. A read-only **investigator** runs when a readable logbook is neither reviewed nor given up. It also runs a cause lookup when an alert's case has no cited cause and no review runs (Q-54). It returns typed proposals with citations and `estado_causa`, never numbers.
3. A **code control** checks schema, size, `estado_causa` against the proposal type, and `verify_citation`. It allows one correction round; a second failure is a safe fallback with no judgment, and the logbook is retried at the next snapshot, at most twice (schema v4 review marks).
4. A brief built by code: the required notices, gap, shipment and bottleneck perspectives computed by code, and the validated proposals delimited as data.
5. The **coordinator**, the only writer, runs only when there are texts or proposals. It never reads raw logbooks, and it applies a proposal only by its id (`apply_proposal`).
6. `finish`, one save.

## Alternatives considered
- **Orchestrator-worker (analysts as coordinator tools):** the steps are already known, so letting the model choose adds cost and variance. At S034 the Pickup raise would depend on the coordinator remembering to consult the investigator, and `FakeModel` scripts would depend on its choices.
- **Pipeline with an LLM fan-out (gap, shipment and bottleneck analysts):** FR-28 read literally, but those analysts would only re-read numbers code already computed. It adds a code aggregator, about 30–35 sub-runs over days 1–7 instead of about 21, and a risk of misquoted numbers.
- **Code applies validated proposals directly:** cheapest, but in practice the reader would decide the writes, against ADR-0003.
- **The coordinator keeps `get_logbook` (as in 008), or gets it back on fallback:** simpler, but the writer would see untrusted text, which is the blast radius 009 removes.

## Consequences
- Positive:
  - Whoever reads logbooks cannot write, and whoever writes never reads them. An injected line must fool the investigator, pass the schema and the citation check, and be applied by id, and even then the severity floor never drops.
  - The steps are deterministic and `FakeModel` scripts are linear.
  - The FR-39 cause metric measures the investigator alone.
  - Cost is recorded per agent (FR-37).
- Negative / risks:
  - FR-28 is met as interpreted (Q-50): three perspectives in code, two agents.
  - A mid snapshot can call the investigator on a retry.
  - Registry schema v4.
  - If the coordinator falls back after validated proposals, the logbook is retried (Q-53).
  - A line injected verbatim into a later logbook still passes `verify_citation`. A `lift` then only restores the code floor.
- Follow-ups:
  - Spec 010 enforces the agents' tool lists in code and must exclude the 008 judgment tools (`set_cause`, `raise_severity`, `lift_severity_raise`), which stay registered but are offered to no agent. 010 also owns the US-08 injection tests (FR-20).
  - Spec 011 caches both prompt prefixes.
  - Spec 016 adds `tendencia` to the brief's gap perspective.
  - Renaming `Coordinator` to `AgentLoop` is deferred.
