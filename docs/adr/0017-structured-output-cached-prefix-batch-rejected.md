# 0017 · Structured output, cached stable prefix and Batch API rejected

- **Status:** Accepted
- **Date:** 2026-11-14
- **Requirements:** FR-34, FR-35, NFR-02, NFR-03, NFR-10 (spec 011)

## Context
Spec 011 must make model output a validated structure (FR-34), cut cost with a cached stable prefix (FR-35, NFR-03), and assess the Batch API, as the brief asks. Since 009 and 010:
- the investigator's final JSON is checked in code (`check_output`), with one correction note and then `fallback:invalid_output`;
- the coordinator writes only through tool arguments (`emit_*`, `apply_proposal`), which the tool schemas, the hooks and the draft validators check;
- each agent's system prompt (role plus `<criterios>`) and tool list are already byte-stable across snapshots (ADR-0016), but no request carries `cache_control`.

API facts, checked against the official docs on 2026-11-14 for `claude-haiku-5-5`:
- **Caching:** the minimum cacheable prefix is 512 tokens. Render order is tools → system → messages, with at most 4 breakpoints. Reads cost ×0.1, writes ×1.25 with a 5-minute TTL and ×2 with 1 hour. Changing thinking, effort or `output_config.format` invalidates the cache.
- **JSON outputs:** `output_config.format` works together with tools. The schema subset has no `oneOf`, no string-length or numeric constraints, and needs `additionalProperties: false` on every object. Anything unsupported returns a 400.
- **Batch API:** asynchronous, 50% off every token, usually done within 1 hour and at most 24 hours. Results come back in any order and may be `errored` or `expired`. Each item is one Messages call, with no conversation.

## Decision
- **Structured output:**
  - The investigator request sends `output_config.format` with a JSON schema derived from `InvestigatorOutput`.
  - Every offered tool is sent with `strict: true`.
  - A pure sanitizer in `agents` turns pydantic and MCP schemas into the supported subset. Code still enforces what it drops.
  - `check_output` stays as the second barrier (size, scope, states, citations, `no_declarada`).
  - The correction count is a setting (default 1). When it runs out, the outcome is the existing fallback, with a warning and the trace outcome; it never aborts.
  - The coordinator gets no new review.
- **Cache:**
  - One explicit 5-minute breakpoint on the last `system` block, which covers tools and system.
  - Top-level automatic caching for the snapshot's conversation tail.
  - Thinking, effort and the output format stay fixed per agent.
  - `count_tokens` is sent without cache markers.
- **Drift:**
  - Every model call records a `prefix_hash`: sha256 of the canonical system, tools and output schema.
  - A hash change between snapshots, or a cache read of zero from a session's second call on, is logged. It never aborts.
- **Batch API:** not used for the agent loop.

## Alternatives considered
- **Code-only validation** (generalize `check_output`, no API change): no 400 risk, but form errors stay possible and every one costs a correction turn.
- **A 1-hour TTL:** the series runs back to back, so each prefix is read again within minutes, and the doubled write price buys nothing.
- **Aborting on drift or on exhausted corrections:** a miss costs money but breaks nothing, while an abort would stop the unattended series and the single held-out run (ADR-0014).
- **Batch API for the agent loop.** It does not fit the workload, for four reasons:
  1. *Snapshots depend on each other.* The brief of snapshot N is built from the state N−1 committed (cases, raises, review marks, notices). The 61 requests cannot be sent together, because N's request does not exist until N−1 commits.
  2. *Each snapshot is a multi-turn tool loop.* Every turn needs tool results that run in our process, inside the open SQLite unit of work (ADR-0003, ADR-0013, ADR-0014). One batch per turn means minutes to hours per turn, which leaves two bad choices:
     - hold the transaction open that long, breaking the single-writer, one-thread, one-unit-of-work design;
     - close it between turns, losing no-partial-writes and clean resume.
  3. *It loses the cache.* The docs warn that a cache entry written inside a batch will likely expire before the follow-up request runs, and order is not guaranteed. The cached prefix (most of each prompt) at ×0.1 can cost less than ×0.5 on everything with no cache.
  4. *It adds operational risk.* Expired and errored items need resubmission logic, and a 61-snapshot series with several turns each could take days instead of minutes, in the one held-out run.

  With Haiku 5.5 prices and caching, the whole series costs in the order of cents (measured by the days 1–7 run). Half of that does not justify redesigning the runner.
- **Batch only for the investigator:** its task depends on state (cases without a cause, active causes), and it uses tools over several turns, so the same objections apply.

## Consequences
- Positive:
  - Form errors in model output become near impossible, and corrections are left for semantic errors.
  - The prefix is billed at ×0.1 from the second call of each agent.
  - A silent cache miss shows up as a logged hash.
  - The Batch assessment is recorded.
- Negative / risks:
  - A schema feature the sanitizer misses returns a 400. A unit test asserts that no unsupported keyword remains in any sanitized schema.
  - Changing a prompt, a tool description or the output schema invalidates the cache until the first new write. That is expected, and the hash makes it visible.
- Follow-ups:
  - The paid days 1–7 run after 011 records the cache numbers in the roadmap.
  - Revisit Batch only for an independent single-shot workload, such as an offline LLM judge of emitted notice texts. None exists today, because the evaluator is deterministic.
  - Spec 012 adds the one-command run with cost and duration.
