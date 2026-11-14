# 010 · Guardrails and unattended run — Tasks

Ordered, test-first. Each task is one commit, committed before the next one starts (the pre-commit mypy hook stashes unstaged tracked changes but leaves untracked files, 008 note).

- A commit's tests use only symbols from that commit or earlier, so **each commit passes `mypy --strict` over `src tests evals` on its own**.
- A test that cannot type-check without its implementation shares the commit with it: every "Tests X → code" task below is one commit.
- Types land before their users:
  - tool names in `mcp_server/types.py` (T16) before the allowlists (T3) and the hooks;
  - trace records (T7) and the chain (T1) before the loop (T2);
  - `hooks/calls.py` (T5) before the text hooks (T4, T13);
  - `ToolClient.get_prompt` (T8) before `ToolPort.get_prompt` (T14);
  - every hook before `coordinator_hooks` (T15).
- A newly required argument changes every caller, `src`, `tests` and `evals`, in the same commit: `criteria` in T14, `hooks` in T15.
- Each task also runs `uv run pytest` and ruff before committing.
- Owner: tests by `test-writer`, code by `domain-implementer`, unless stated.

Ids T1–T11 come from the Draft skeleton and keep their topic. T0 and T12–T16 are new. T10 is dropped.

- [x] T0 · **Main session, before Ready:** ADR-0016 written (hook chain, allowlists, criteria prompt, failure policy, trace records) — refs: D1–D6 · plan: Design notes
- [x] T12 · **Main session, before Ready:**
  - `specs/stories/US-09-guardrails.md`: the four scenarios as reinterpreted, plus a note "reinterpreted in spec 010";
  - `docs/requirements.md`: Q-44 (`hooks` holds one record per block: agent, phase, hook, tool, turn, reason), Q-46 ("enforced by the cause hook in spec 010") and Q-55 decided (category words describing data are blocked);
  - roadmap row 010: US column gains 08, FR column gains 15 and 20, open items (ADR-0016, Q-44/Q-46/Q-55).

  — refs: D9, R7, R10
- [x] T16 · Tests E24 (names part) → `mcp_server/types.py` (`READ_TOOLS`, `WRITE_TOOLS`, one constant per name, `CRITERIA_PROMPT` not yet); `mcp_server/server.py` re-exports `READ_TOOLS as READ_TOOLS`, `WRITE_TOOLS as WRITE_TOOLS` and keys `available` by the constants. Every importer of `server.READ_TOOLS`/`WRITE_TOOLS` stays unchanged — refs: R2, D4, E24 · plan: Tool names and allowlists
- [x] T3 · Tests E6, E24 (lists part) → `agents/allowlists.py` (lists moved from `factory.py` and built from the `types` constants, `ALLOWLISTS`, `EXCLUDED`, `check_allowlists`). Same commit:
  - `build_coordinator`/`build_investigator` offer `ALLOWLISTS[agent]`;
  - `build_agent_pipeline` calls `check_allowlists(ALLOWLISTS)` first and builds each server from `ALLOWLISTS[agent]`;
  - the seven test files that import the lists from `agents.factory` import them from `agents.allowlists`;
  - changed expectation 009 E7 (`test_factory.py:88`) becomes E24's single-source assertion, and the factory's "copied as literals" comment goes.

  — refs: R2, E6, E24 · plan: Tool names and allowlists, Factory
- [x] T7 · Tests E16 → `telemetry/trace.py` (`HookPhase`, `HookRecord`, `TraceHook`, typed `TraceLine.hooks`, `build_line(hooks=)`). The existing trace tests asserting `hooks == []` stay green unchanged — refs: R10, E16 · plan: Trace
- [x] T1 · Tests E1, E5a and the `hooks` rules of E23 → `hooks/__init__.py` (docstring only), `hooks/chain.py`, `hooks/view.py`, `hooks/allowlist.py`; `tests/unit/test_import_boundaries.py` gains the R15 `hooks` rule — refs: R1, R3, R15, E1, E5, E23 · plan: `HookChain`, `SnapshotView`, Hooks
- [x] T5 · Tests E7, E13d, E13e → `hooks/calls.py` (`emitted_case_ids`, `targets`), `hooks/novelty.py` — refs: R4, I4, E7, E13, X5 · plan: Calls and texts, Hooks
- [x] T4 · Tests E8, E9 → `hooks/texts.py` (`fold`, `stated_severities`), `hooks/floor.py` (`TextFloorHook` over `targets`, `FloorCheck`) — refs: R5, R6, E8, E9, X2, X3, X6 · plan: Calls and texts, Hooks
- [x] T13 · Tests E10, E13a–c → `hooks/texts.py` (`named_categories`), `hooks/cause.py` (over `targets`). E13a–c cover novelty, floor and cause over malformed arguments — refs: R7, E10, E13, X1, X4, X9 · plan: Calls and texts, Hooks
- [x] T6 · Tests E11 → `hooks/completeness.py` — refs: R8, E11 · plan: Hooks
- [x] T2 · Tests E2, E3, E4, E5b, E14 → `agents/loop.py`:
  - `LoopLog.hooks`;
  - `Coordinator(..., agent, hooks)` with the allowlist first;
  - keyword-only `run(..., *, view=None)`;
  - pre, post and on-stop seams; the `names` check removed.

  Same commit:
  - `tests/agent_builders.py` `make_coordinator` gains `hooks` and `agent`;
  - changed expectations 007 E4 (`test_loop.py:121`) and 009 E10 (`test_factory.py:112-113`);
  - the import-boundary test lets `agents` import `hooks`;
  - `build_investigator` passes `agent="investigator"`;
  - 007 E8 and every other loop test stay green unchanged. `CoordinatorStep` still calls `run` without `view`.

  — refs: R1, R3, R8, R9, E2–E5, E14, X8 · plan: Loop
- [x] T8 · Tests E17 → `mcp_server/types.py` (`CRITERIA_PROMPT`), `mcp_server/context.py` (`ToolContext.criteria`), `mcp_server/server.py` (prompt registration), `mcp_server/client.py` (`get_prompt`, error mapping). `ToolPort` is not changed yet — refs: R11, E17 · plan: MCP
- [x] T14 · Tests E18, E19a → criteria end to end:
  - `agents/loop.py`: `ToolPort.get_prompt`, `criteria_prompt`, `compose_system`;
  - `agents/factory.py`: `build_*` set `criteria_prompt`;
  - prompts coordinator v4 and investigator v2;
  - `config.py`: derived `Settings.criteria_path`;
  - `runner/agent_pipeline.py`: `build_agent_pipeline(..., criteria: str)` into `ToolContext`;
  - `evals/agent_days_1_3.py`, `evals/agent_days_1_7.py`: pass `settings.criteria_path.read_text("utf-8-sig")`.

  Same commit:
  - `CRIT` in `tests/builders.py`;
  - `FakeTools.get_prompt` and `make_coordinator(criteria_prompt=)`;
  - `incident_tool_context` and `mcp_builders` set `criteria=CRIT`;
  - every `build_agent_pipeline` call passes `criteria=CRIT` (`test_agent_runner`, `test_judgment_runner`, `test_multi_agent_runner` ×2, the composition-root risk test);
  - changed expectations 007 E5, 009 E7 (`test_investigator.py:74`, `:94`), 009 E8 (`test_factory.py:71`), 009 E19 (`test_multi_agent_runner.py:381`, now E19b), Settings E36 (`test_config.py:84-91`, derived set gains `criteria_path`).

  — refs: R11, R12, E18, E19, X11 · plan: Loop, Factory, MCP, Settings, Runner
- [x] T15 · Tests E12 → the wiring:
  - `runner/coordinator_step.py`: `DecisionView` (structural, no `hooks` import), `functools.partial(self._coordinator.run, view=DecisionView(writer))`;
  - `agents/factory.py`: `coordinator_hooks()`, `build_coordinator(..., *, hooks: HookChain)` required;
  - `runner/agent_pipeline.py`: `hooks=coordinator_hooks()`, `hooks` on staged and aborted lines.

  Same commit:
  - every `build_coordinator` caller passes `hooks=` (`HookChain()` in 007 E5 and 009 E10; `coordinator_hooks()` in `test_agent_pipeline` and E12);
  - every 007–009 integration test stays green (their texts trigger no hook);
  - E23 checks `coordinator_step.py` imports no `hooks`.

  — refs: R1, R4, R6, R8, R15, E12, E23 · plan: Factory, Runner
- [x] T9 · Integration E15, E20, E21, E22 (`tests/integration/test_guardrails_runner.py`, `criteria=CRIT`; `incident_builders.copy_incident_logbooks(..., append=)`; the 009 script builders are shared if needed) → fixes in `src/` only if they fail — refs: R9, R13, R14, E15, E20–E22, X10 · plan: Test strategy
- [ ] ~~T10~~ · **Dropped:** no on-demand real run in 010. The demo block comes from E22 (FakeModel, in CI). Hooks are live in the user's pending paid days 1–7 run (009 T18), and a real block may be used by spec 013.
- [x] T11 · **Main session, docs:**
  - `docs/STRUCTURE.md`:
    - rows for `hooks/*`, `agents/allowlists.py`, `mcp_server/types.py` (tool names);
    - the dependency rule (`hooks` → `domain`, `mcp_server.types`; `agents` → `hooks`; `DecisionView` structural);
    - the `cases/novelty.py` row reworded to "reused by spec 010's hooks through the decision's notices";
    - updated rows for loop, factory, server, client, context, config (`criteria_path`), trace, coordinator step and pipeline;
  - `docs/agent-capabilities.md`: allowlists enforced in code with the three barriers; hooks per agent (investigator: allowlist; coordinator: allowlist, novelty, floor, cause, post floor, completeness); `<criterios>` in both systems;
  - diagrams: `snapshot-sequence.md` (pre/post/on-stop around tool calls), `shift-close.md` (completeness on stop), `components.md` (`hooks` package, `criteria` prompt);
  - roadmap row 010 (scope, ADR-0016, Q-44/Q-46 amended, status) and the inventory row `criteria` ("Implemented (010): full `criterio.md`, both agents");
  - check ADR-0016 against D1–D8;
  - spec status Implemented;
  - `/check`.

  — refs: Acceptance · plan: Modules
