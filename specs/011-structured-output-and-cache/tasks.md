# 011 · Structured output and prompt caching — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts (the pre-commit mypy hook stashes unstaged tracked changes but leaves untracked files, 008 note).

- A commit's tests use only symbols from that commit or earlier, so **each commit passes `mypy --strict` over `src tests evals` on its own**.
- A test that cannot type-check without its implementation shares the commit with it: every "Tests X → code" task below is one commit.
- Types land before their users:
  - the sanitizer (T10), the prefix module (T2), the trace fields (T12), the setting (T11) and `ModelRequest.output_schema` (T3) come before the loop (T4);
  - the loop comes before the factory and the step (T1).
- Every new defaulted field (`ModelRequest.output_schema`, `LoopConfig.max_notes`, `ModelCallRecord.prefix_hash`) leaves existing callers compiling unchanged.
- Each task also runs `uv run pytest` and ruff before committing. Every test cites its spec id (`Risk:` tests too). Helpers come `from builders import ...` (or the other `*_builders`), never `from tests.builders`.
- Owner: tests by `test-writer`, code by `domain-implementer`, unless stated.

Ids T1–T9 come from the Draft skeleton and keep their topic. T0 and T10–T12 are new. T6 is dropped.

- [x] T0 · **Main session and spec writer, before Ready:** ADR-0017 written; `docs/requirements.md` gains Q-56–Q-63 and amends Q-44 (`prefix_hash`, run cache sums) and Q-52 (configurable corrections) — refs: D1–D7 · plan: Design notes
- [x] T8 · **Main session, before Ready:** Batch API assessed and rejected for the agent loop, recorded in ADR-0017 (Q-62) — refs: R12
- [x] T10 · Tests E1, E2 (`Risk:` for E2, over `incident_tool_context` and every registered tool) → `agents/output.py` (`SUPPORTED_KEYWORDS`, `DROPPED_KEYWORDS`, `strict_schema` with the R1 step order, `investigator_output_schema`). E2 also asserts that the optional properties are nullable (`raise_severity.mercado`) — refs: R1, R2, R3, E1, E2, X2 · plan: `strict_schema`
- [x] T2 · Tests E9, E11a, E11b → `agents/prefix.py` (`prefix_bytes` with `default=dict`, `prefix_hash`, `PrefixMonitor()` keyed by agent) — refs: R8, R9, E9, E11, X5 · plan: Prefix
- [x] T12 · Tests E12 → `telemetry/trace.py`:
  - `ModelCallRecord.prefix_hash` and `TraceModelCall.prefix_hash`, both `str | None = None`, copied in `_costed`;
  - the three cache sums on `AgentRunTotals` and `RunTotals`, summed in `run_totals`.

  The existing trace tests stay green unchanged.

  — refs: R10, E12 · plan: Trace
- [x] T11 · Tests E8 → `config.py` (`investigator_output_corrections`, `ge=0`), `.env.example` (`INVESTIGATOR_OUTPUT_CORRECTIONS=1` in the multi-agent block, comment amended). Same commit: `tests/builders.py` `SETTINGS_ENV_NAMES` gains the name. The name is not added to `MULTI_AGENT_ENV_NAMES`, because 0 is valid here — refs: R4, E8 · plan: Settings
- [x] T3 · Tests E3, E4, E15 → `agents/model.py` (`ModelRequest.output_schema`, defaulted last field), `agents/anthropic_model.py`:
  - `_ephemeral`;
  - `_base_params` (system block, `strict` tools);
  - `to_params` = base plus `max_tokens`, `output_config` with `format` (`dict(request.output_schema)`), and both cache markers;
  - `_count_params` = base.

  E15 (`Risk:`, no network) lives in `tests/unit/agents/test_anthropic_model.py`, which already imports `anthropic`; the import scan covers `src` only. Same commit:
  - changed expectation 007 E11 (`test_anthropic_model.py:183-192`): the key set gains `cache_control`;
  - the count-body risk test stays green unchanged.

  — refs: R6, R7, E3, E4, E15, X3, I10, I12 · plan: Model port, Adapter
- [x] T4 · Tests E7, E10, E11c, E11c′, E11d → `agents/loop.py`:
  - `LoopConfig.max_notes = 1`;
  - `Coordinator(..., output_schema=None, prefix_monitor=None)`;
  - offered schemas sanitized once per run;
  - `prefix_hash` per run on every `ModelCallRecord`;
  - `on_run` and `on_call` calls, passing `self._agent`;
  - the `notes_sent` counter replaces `reminded`;
  - the `EndReview.exhausted` docstring.

  Same commit:
  - `tests/agent_builders.py`: `make_coordinator(max_notes=, output_schema=, prefix_monitor=)`, and `FakeTools.criteria` / `FakeTools.suffix`;
  - 007 E6, E8, 009 E5 and 010 E2/E3/E14 stay green unchanged.

  — refs: R3, R4, R8, R9, R10, E7, E10, E11, I1, I4, I6, X4 · plan: Loop, Test builders
- [x] T1 · Tests E5, E6 → the wiring:
  - `agents/factory.py`:
    - `build_investigator` uses `replace(_config(...), max_notes=settings.investigator_output_corrections)` and passes `output_schema=investigator_output_schema()` and `PrefixMonitor()`;
    - `build_coordinator` passes `PrefixMonitor()` and keeps `LoopConfig`'s default `max_notes`;
  - `runner/review_step.py`: the R4 WARNING on `fallback:invalid_output`, and on `fallback:turn_cap` with rejections recorded;
  - `agents/investigator.py`: the `ProposalReview` docstring.

  E6 lives in `tests/unit/runner/test_review_step.py` (reuses `s010_rig`, with a `corrections` parameter added), with `WRONG_RAISE5` and `FRAGMENT_ERROR` from `multi_agent_builders`. 009 E25 and the factory tests stay green unchanged.

  — refs: R2, R4, R5, E5, E6, I3, I7, I11, X1 · plan: Factory, Review step
- [x] T5 · Integration E13, E14 (`tests/integration/test_output_cache_runner.py`, new; `run_full`, `run_ids`, `Recorder`, `query` and HEAD from `multi_agent_builders`, with `S005-bis.json` written by the test) → fixes in `src/` only if they fail — refs: R11, R2, R8, R9, E13, E14, FR-02 · plan: Test strategy
- [ ] ~~T6~~ · **Dropped:** no new resume test. 009 E20, 007 E21, 008 E22 and 003 E30 already cover it (X7).
- [x] T9 · **Main session, docs:**
  - `docs/STRUCTURE.md`: rows for `agents/output.py` and `agents/prefix.py`; updated rows for model, adapter (cache markers, strict, format), loop (note budget, prefix hash), factory, review step, trace, config; the dependency rule unchanged;
  - `docs/agent-capabilities.md`: strict tools for both agents, the investigator's output format and corrections setting, the cached prefix per agent;
  - roadmap row 011: scope as built, Q-56–Q-63, ADR-0017, status;
  - check ADR-0017 against D1–D7;
  - spec status Implemented;
  - `/check`.

  — refs: Acceptance · plan: Modules
- [ ] T7 · **User, manual, after merge (not a test):** one paid run of days 1–7 (`evals/agent_days_1_7.py`).
  - It confirms `cache_read_tokens` > 0 from the second call of each agent's session, no `prefix changed` WARNING, and "S034 skipped: already processed" in the log.
  - It also covers 009 T18 and 008 R22.
  - Cost, cache read/write totals per agent and duration go in the roadmap.
  - **Gate:** T7 must pass before the held-out run starts. A failed check (no cache reads, prefix drift, S034 reprocessed) is fixed and the run is repeated first.

  — refs: Q-61, Q-63, FR-35, NFR-03
