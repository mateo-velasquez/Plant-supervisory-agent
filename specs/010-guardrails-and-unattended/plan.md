# 010 · Guardrails and unattended run — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `hooks/__init__.py` | New | Package docstring only; every import names a submodule. |
| `hooks/chain.py` | New | `ToolCall`, `HookContext`, `HookBlock`, hook protocols, `HookChain`, `HookViolation`, `FloorViolation`, `MissingView`, `require_view`. |
| `hooks/view.py` | New | `SnapshotView` protocol. |
| `hooks/calls.py` | New | Lenient argument readers and `targets(call, view)`. |
| `hooks/texts.py` | New | `fold` and the pattern helpers (severity statement, category mention). |
| `hooks/allowlist.py`, `novelty.py`, `floor.py`, `cause.py`, `completeness.py` | New | `AllowlistHook`; `NoveltyHook`; `TextFloorHook` (pre) and `FloorCheck` (post); `CauseHook`; `CompletenessHook`. |
| `mcp_server/types.py` | Adds | `READ_TOOLS`, `WRITE_TOOLS` and one constant per tool name (moved from `server.py`); `CRITERIA_PROMPT`. |
| `mcp_server/server.py` | Changes | Re-exports `READ_TOOLS as READ_TOOLS`, `WRITE_TOOLS as WRITE_TOOLS`; registers the `criteria` prompt when set. |
| `mcp_server/context.py` | Changes | `ToolContext.criteria: str | None = None`. |
| `mcp_server/client.py` | Changes | `ToolClient.get_prompt`. |
| `agents/allowlists.py` | New | `INVESTIGATOR_TOOLS`, `COORDINATOR_TOOLS` (moved, built from the `types` constants), `ALLOWLISTS`, `EXCLUDED`, `check_allowlists`. |
| `agents/loop.py` | Changes | `ToolPort.get_prompt`; `LoopLog.hooks`; `Coordinator(..., agent, hooks, criteria_prompt)`; keyword-only `view` on `run`; hook seams; `compose_system`. |
| `agents/factory.py` | Changes | `coordinator_hooks()`; `build_coordinator(..., *, hooks)` and `build_investigator` offer `ALLOWLISTS[agent]` and set `criteria_prompt`. |
| `agents/prompts/coordinator.md`, `investigator.md` | Changes | v4 and v2: one `<criterios>` line in `## Role`. |
| `config.py` | Adds | Derived `Settings.criteria_path`. |
| `telemetry/trace.py` | Changes | `HookPhase`, `HookRecord`, `TraceHook`; `TraceLine.hooks` typed; `build_line(hooks=)`. |
| `runner/coordinator_step.py` | Changes | `DecisionView` (structural `SnapshotView`, no `hooks` import); binds `view` with `functools.partial`. |
| `runner/agent_pipeline.py` | Changes | Required `criteria` argument, `check_allowlists`, servers from `ALLOWLISTS`, `coordinator_hooks()`, hook records on both line kinds. |
| `evals/agent_days_1_3.py`, `agent_days_1_7.py` | Changes | Pass `settings.criteria_path.read_text("utf-8-sig")`. |
| `tests/builders.py`, `agent_builders.py`, `judgment_builders.py`, `mcp_builders.py`, `incident_builders.py` | Changes | `CRIT` literal; `FakeTools.get_prompt`, `make_coordinator` kwargs; `criteria=CRIT` in the tool contexts; `copy_incident_logbooks(..., append=)`. |

## Types and interfaces

### `HookChain`
`hooks/chain.py`:
- `@dataclass(frozen=True) ToolCall(name: str, arguments: Mapping[str, object])`.
- `@dataclass(frozen=True) HookContext(agent: str, turn: int, view: SnapshotView | None)`.
- `@dataclass(frozen=True) HookBlock(hook: str, reason: str)`.
- Protocols, each with a read-only `name: str`:
  - `PreToolHook.check(call, ctx) -> str | None`;
  - `PostToolHook.verify(call, outcome: ToolOutcome, ctx) -> None`;
  - `StopHook.check(text: str, ctx) -> str | None`.
- `HookChain(pre: Sequence[PreToolHook] = (), post: Sequence[PostToolHook] = (), stop: Sequence[StopHook] = ())`:
  - `pre_tool(call, ctx) -> HookBlock | None` and `on_stop(text, ctx) -> HookBlock | None`: the first non-None reason wins, and later hooks are not called;
  - `post_tool(call, outcome, ctx) -> None` calls every hook;
  - `with_first(hook: PreToolHook) -> HookChain`.

  It catches nothing.
- `HookViolation(RuntimeError)`; `FloorViolation(HookViolation)`; `MissingView(HookViolation)` (`hook <name> needs a snapshot view`); `require_view(ctx, name) -> SnapshotView`.

### `SnapshotView`
`hooks/view.py`, `Protocol`: `alerts() -> tuple[Notice, ...]`, `news() -> tuple[Notice, ...]`, `floors() -> Mapping[str, Severity]`, `missing() -> tuple[str, ...]`.

### Calls and texts
- `hooks/calls.py`:
  - `emitted_case_ids(call) -> tuple[str, ...]`: the string `case_id`s of `EMIT_ALERT`, or of each `EMIT_SHIFT_REPORT` item, in order; others skipped;
  - `targets(call, view) -> tuple[tuple[str, Notice, str], ...]`: `(case_id, notice, texto)`, with the notice taken from `view.alerts()` for `EMIT_ALERT` and from `view.news()` per report item; an item without a notice or a string `texto` is dropped;
  - tool-name constants come from `mcp_server.types`.
- `hooks/texts.py`:
  - `fold(text) -> str` (NFKD, drop combining marks, `casefold`);
  - `stated_severities(folded) -> tuple[tuple[bool, Severity], ...]` (`is_maxima`, level; change phrases skipped, R5);
  - `named_categories(folded) -> tuple[CauseCategory, ...]` (text order, R7).

  The regexes are compiled once from `Severity` and `CauseCategory` values.

### Hooks
- `AllowlistHook(agent: str, tools: Sequence[str])`, name `allowlist` (R3).
- `NoveltyHook()`, name `novelty`, over `emitted_case_ids` (R4).
- `TextFloorHook()`, name `floor`, over `targets` (R5). Reason `below notice severity (<level>)` (user decision): `<level>` is the notice's `severidad` or `severidad_maxima`, which may sit above the computed minimum when raised.
- `FloorCheck()`, name `floor`: acts only on `APPLY_PROPOSAL` (R6).
- `CauseHook()`, name `cause`, over `targets` (R7).
- `CompletenessHook(render: Callable[[Sequence[str]], str])`, name `completeness` (R8).

### Tool names and allowlists
- `mcp_server/types.py`:
  - `LIST_AVAILABLE_LOGBOOKS`, `GET_LOGBOOK`, `GET_DEVIATIONS`, `GET_ACTIVE_CASES`, `GET_CASE`, `GET_DELAYED_UNITS`, `SET_CAUSE`, `RAISE_SEVERITY`, `LIFT_SEVERITY_RAISE`, `APPLY_PROPOSAL`, `EMIT_ALERT`, `EMIT_SHIFT_REPORT`: `Final` strings;
  - `READ_TOOLS`, `WRITE_TOOLS: Final[tuple[str, ...]]`;
  - `CRITERIA_PROMPT: Final = "criteria"`.
- `server.py` keeps its wrapper names and its `available` map, keyed by the constants.
- `agents/allowlists.py`:
  - `INVESTIGATOR_TOOLS`, `COORDINATOR_TOOLS` (009 order, from the constants);
  - `ALLOWLISTS: Final[Mapping[AgentName, tuple[str, ...]]]`;
  - `EXCLUDED: Final[frozenset[str]]`;
  - `check_allowlists(lists: Mapping[AgentName, Sequence[str]]) -> None`, which raises the R2 `ValueError` for the first offending agent.

### Loop
`agents/loop.py`:
- `ToolPort.get_prompt(self, name: str) -> Awaitable[str]` (async, like `call`).
- `LoopLog.hooks: list[HookRecord]`.
- `Coordinator(model, tools, system, allowed, config, clock=…, *, agent: AgentName = "coordinator", hooks: HookChain | None = None, criteria_prompt: str | None = None)`. The effective chain is `(hooks or HookChain()).with_first(AllowlistHook(agent, allowed))`.
- `run(snapshot_id, brief, progress, log, review: EndReview | None = None, *, view: SnapshotView | None = None)`.
- `compose_system(role: str, criteria: str) -> str` (R11).
- The `names` check in `_run_tools` is replaced by the chain. The post hook runs after the `ToolCallRecord` is appended; the on-stop hook runs before `review.review`.

### Factory
- `coordinator_hooks() -> HookChain`: pre (`NoveltyHook`, `TextFloorHook`, `CauseHook`), post (`FloorCheck`), stop (`CompletenessHook(render_reminder)`).
- `build_coordinator(settings, model, tools, *, hooks: HookChain)`: required keyword; offers `ALLOWLISTS["coordinator"]`.
- `build_investigator(settings, model, tools)`: no `hooks` parameter (the loop adds the allowlist); offers `ALLOWLISTS["investigator"]`, `agent="investigator"`.
- Both set `criteria_prompt=CRITERIA_PROMPT`.

### MCP
- `ToolContext.criteria: str | None = None` (last field). It stays optional: 006–008 contexts that never serve a prompt stay valid, and the required `build_agent_pipeline` argument guarantees it in production.
- `build_server`: when `ctx.criteria is not None`, it registers an async prompt function named `CRITERIA_PROMPT` that returns it.
- `ToolClient.get_prompt(name) -> str`: `client.get_prompt(name)` joins every message's `TextContent.text`. The SDK's error for an unknown prompt maps to `ValueError("prompt <name> is not available")`.

### Settings
`Settings.criteria_path` is a derived property: `rules_dir / "criterio.md"`. There is no field, env var or `.env.example` line.

### Trace
- `HookPhase = Literal["pre_tool", "on_stop"]`.
- `@dataclass(frozen=True) HookRecord(agent: AgentName, phase: HookPhase, hook: str, tool: str | None, turn: int, reason: str)`.
- `TraceHook` (frozen pydantic, same fields).
- `TraceLine.hooks: list[TraceHook] = []`.
- `build_line(..., hooks: Sequence[HookRecord] = ())`.

### Runner
- `runner/coordinator_step.py`, `DecisionView(writer: SnapshotWriter)`: structural, it imports nothing from `hooks`. Over `final = writer.final()`:
  - `alerts()`: the decisions of type alert;
  - `news()`: `report.novedades` or `()`;
  - `floors()`: `{c.case_id: c.minimum_severity for c in final.delta.cases}` (`{}` when `delta` is None);
  - `missing()`: `writer.missing()`.

  `CoordinatorStep.run` passes `functools.partial(self._coordinator.run, view=DecisionView(writer))` to `run_in_frame` with the positional arguments. The partial plugin of mypy types it against `run_in_frame`'s `Callable[[*Args], Awaitable[T]]`.
- `InvestigatorStep` is unchanged (its loop runs with `view` None).
- `build_agent_pipeline(settings, registry, ctx, policy, model, trace, criteria: str)`, in order:
  1. `check_allowlists(ALLOWLISTS)`;
  2. `ToolContext(..., criteria=criteria)`;
  3. each server with `tools=ALLOWLISTS[agent]`;
  4. `build_investigator(...)` and `build_coordinator(..., hooks=coordinator_hooks())`.
- `_stage` and `_aborted` pass `hooks=[*run.inv_log.hooks, *run.log.hooks]`.

## Design notes
- **Why a chain in the loop, not a wrapped port.** The loop is the one seam both agents share (007 extension point), and it owns turn and agent. Wrapping `ToolPort` would hide blocks from `ToolCallRecord` and miss the stop seam.
- **One list object (I1, D4).** `ALLOWLISTS[agent]` is what `check_allowlists` checks, what `build_server` serves, what the factory offers, and what the loop builds its allowlist hook from. Tool names have one source (`mcp_server/types.py`), so no copied literal has to be kept in sync.
- **Hooks read decisions, never rules (D1).**
  - The novelty set comes from the draft, which `cases/novelty.py` built.
  - Floors are each case's `minimum_severity`, set by the lifecycle from the snapshot's metrics.
  - Causes come from the notice.

  `hooks` imports no `cases`, so it cannot drift into a second implementation.
- **One reader of arguments.** `hooks/calls.py` is the only code that interprets raw model arguments, so leniency (X4) lives in one place, and floor and cause see identical targets.
- **View adapter in `runner`, structural.** `SnapshotWriter` and the test `FakeSnapshotWriter` stay unchanged, and `runner` needs no `hooks` import. `DecisionView` reads `final()`, which is cheap at this scale and always reflects the last rebase.
- **Criteria as an argument.** The composition root reads no file. The eval scripts read `criteria_path`, the way they locate `umbrales.yaml`, and tests pass a literal, so no fixture folder is needed.
- **Post-tool raises, never undoes (ADR-0016).** The write is already inside the unit of work, so aborting rolls it back with the rest of the snapshot.
- **Text checks are narrow.** Patterns were chosen so the template shapes pass (`severidad x → y`, `máxima`, `pico de`, the cause sentence; E8b, E10a), and so do common words ("a media mañana", E8e).
- **Criteria per run, not per request.** The loop fetches the prompt once per conversation; the system is then constant within the run and across snapshots (011's cache prefix).
- **Fail-closed.** No `try` in the chain or around it. The anyio single-leaf unwrap (`runner/bridge.py`) already gives `RunAborted` the real cause (E15).

## Test strategy
- **Unit, no I/O:**
  - chain (E1);
  - each hook and `targets` over a fake view (E5a, E7–E11, E13);
  - allowlists and names (E6a, E6b, E24);
  - trace (E16);
  - settings (E19a);
  - prompts (E18c).
- **Loop** with `FakeTools` and fake hooks: E2–E4, E5b, E14, E18a/b/d.
- **MCP through `ToolClient`:** E17.
- **Step:** E12 (`CoordinatorStep` over a real server and `FakeSnapshotWriter`; `DecisionView` over `SnapshotJudgment`).
- **Integration** (`tests/integration/test_guardrails_runner.py`, new): E15, E20, E21, E22 on IF with a file-backed registry and `criteria=CRIT`, reusing the `test_multi_agent_runner` script builders (moved to a shared helper if needed). E19b adapts 009's integration. E6c is in the composition-root tests.
- **Imports:** E23 in `tests/unit/test_import_boundaries.py`.

## Risks
- **False blocks on legitimate text** would cost turns, then a template fallback. Mitigations: narrow patterns; the template shapes pass by construction (E8b); E22's trace and the paid run show every block with its reason.
- **Missed paraphrases** (X1): accepted. The text checks are a net, not a proof; evals measure the rest.
- **Test churn:** limited to the Acceptance list. The required `criteria` and `hooks` arguments touch every caller in one commit each (T14, T15).
- **Prompt size:** about 1,500 more tokens per request (ADR-0016). Still far below `prompt_token_limit`; 011 caches it.
