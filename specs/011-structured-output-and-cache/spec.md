# 011 · Structured output and prompt caching — Spec

- **Status:** Draft
- **Requirements:** FR-02 (hardening), FR-34, FR-35, NFR-03
- **Stories:** —
- **Week:** W5

## Goal
Make every model output a validated structure, cut cost with a cached stable prefix, and prove that the repeated snapshot changes nothing in the real series. This prepares the single run of the held-out days.

## Scope
- In: validated output with retry; stable prefix with cache breakpoints; cache verification; prefix-drift detection; idempotency hardening on the real S034 repeat; Batch API assessment.
- Out: the held-out run itself (a process step in the roadmap); the CLI (spec 012).

## Behavior
- Every notice and report the model drafts is validated against the spec 004 schemas; a failure is retried up to N times with the validation error, then fails loudly (FR-34).
- The prefix (system prompt, tool definitions, criteria) is byte-stable across snapshots and marked for caching (FR-35).
- From the second model call on, `cache_read_input_tokens` is greater than zero; a call without cache reads is logged with the prefix hash that changed.
- The S034 repeat in the real series produces no new cases, notices or state changes (FR-02).
- The brief asks to consider the Batch API: assess it and record the decision.

## Worked examples
To be written when the spec moves to Ready.

## Edge cases and assumptions
- D3: the minimum cacheable prefix length for Haiku 5.5 sets how the prefix is built.

## Acceptance
- [ ] Every rule above has a passing test (fake model for validation and prefix stability).
- [ ] A real run shows cache reads from the second call on; numbers recorded.
- [ ] Batch API decision recorded (ADR or roadmap note).
