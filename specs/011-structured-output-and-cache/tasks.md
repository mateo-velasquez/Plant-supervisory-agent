# 011 · Structured output and prompt caching — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Validation tests: a valid draft passes; an invalid one is retried with the error; after N failures the step fails loudly → `agents/output.py`.
- [ ] T2 · Prefix tests: the same inputs give byte-identical prefixes; per-snapshot data stays after the last breakpoint → `agents/prefix.py`.
- [ ] T3 · Cache breakpoints placed on the stable prefix; test the request shape with a fake transport.
- [ ] T4 · Usage test: cache reads and the prefix hash are recorded per call; a call without cache reads is logged with the changed hash.
- [ ] T5 · Idempotency test on the SQLite registry: S034 processed twice changes nothing (cases, notices, history).
- [ ] T6 · Resume test: a failure in the middle of a snapshot leaves no partial writes, and a rerun completes it.
- [ ] T7 · Real run of one day: confirm `cache_read_input_tokens` > 0 from the second call; record the numbers.
- [ ] T8 · Assess the Batch API for this workload; record the decision (ADR or roadmap note).
- [ ] T9 · Update `docs/STRUCTURE.md` and set status to Implemented. Next: the held-out run (roadmap process step).
