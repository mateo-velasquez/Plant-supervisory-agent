# 007 · Coordinator agent — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `agents/__init__.py` | New | Package docstring only. |
| `agents/model.py` | New | Port types: content blocks, `Message`, `ModelRequest`, `ModelReply`, `ModelSession`, `ModelPort`, `ModelCallFailed`. No SDK. |
| `agents/fake_model.py` | New | `FakeModel` (scripted, records requests and counts). |
| `agents/anthropic_model.py` | New | `AnthropicModel`, `RetryPolicy`, `backoff_delay`, `is_retryable`, `to_params`, `from_message`. The only `anthropic` importer. |
| `agents/loop.py` | New | `ToolPort`, `TextProgress`, `LoopOutcome`, `LoopConfig`, `LoopLog`, `Coordinator`. |
| `agents/brief.py` | New | `render_brief`, `render_reminder`. |
| `agents/factory.py` | New | `COORDINATOR_TOOLS`, `load_prompt`, `build_coordinator`. |
| `agents/prompts/coordinator.md` | New | Prompt v1 (R15), packaged data. |
| `cases/draft.py` | New | `NoticeDraft` and its refusals. Only `runner` uses it; `mcp_server` depends only on the `NoticeTextWriter` protocol, never on `cases.draft`. |
| `mcp_server/types.py` | New (006 module touched) | `ToolSpec`, `ToolOutcome` moved here, with no `mcp` import. |
| `mcp_server/client.py` | Changes (006) | Re-exports `ToolSpec` and `ToolOutcome` from `types.py`; 006 code and tests are unchanged. |
| `mcp_server/context.py` | Adds | `NoticeTextWriter`; `SnapshotFrame.notices`. |
| `mcp_server/write_tools.py` | New | `NewsText`, `emit_alert`, `emit_shift_report`; pure, no `mcp`. |
| `mcp_server/server.py` | Adds | `WRITE_TOOLS`; `build_server(..., tools=READ_TOOLS)`. |
| `telemetry/__init__.py`, `usage.py`, `trace.py` | New | `Usage`, `PriceCard`, `cost_usd`; trace records, `TraceWriter`, `trace_path`, `read_trace`, `run_totals`. |
| `runner/pipeline.py` | Changes | `SnapshotDecision`; `ThresholdPipeline.decide` and `finish`. `process` = `finish(decide())`, same behavior. |
| `runner/agent_pipeline.py` | New | `OpenUnit`, `NoticeSteps`, `AgentPipeline`, `build_agent_pipeline`. |
| `runner/post_commit.py` | New | `PostCommitChain`. |
| `config.py`, `.env.example` | Adds | R16 settings, `traces_dir`. |
| `evals/agent_days_1_3.py` | New | R18 real run (thin, user-run). |

## Types and interfaces

### Port types
`agents/model.py`, frozen dataclasses:
- `TextBlock(text)`, `ThinkingBlock(thinking, signature)`, `RedactedThinkingBlock(data)`, `ToolUseBlock(id, name, input: Mapping[str, object])`, `ToolResultBlock(tool_use_id, content: str, is_error: bool)`;
- `ContentBlock` = their union;
- `Message(role: Literal["user", "assistant"], content: tuple[ContentBlock, ...])`;
- `ModelRequest(system: str, tools: tuple[ToolSpec, ...], messages: tuple[Message, ...], max_tokens: int, effort: Effort)`, with `Effort = Literal["low", "medium", "high"]`;
- `ModelReply(content: tuple[ContentBlock, ...], stop_reason: str, usage: Usage)`.

`ToolSpec` and `ToolOutcome` come from `mcp_server.types`, so importing `agents` never loads `mcp`.

### `ModelSession` / `ModelPort`
- `class ModelSession(Protocol)`: `async def count_tokens(self, request: ModelRequest) -> int`; `async def create(self, request: ModelRequest) -> ModelReply`.
- `class ModelPort(Protocol)`: `def session(self) -> AbstractAsyncContextManager[ModelSession]`. The loop enters it once per snapshot (X5).
- `class ModelCallFailed(Exception)`: `operation: str`, `status: int | None`; the message holds no key and no body (R7).

### `FakeModel`
`FakeModel(script: Sequence[ModelReply | Exception], count: int | Callable[[ModelRequest], int] = 3000)`:
- `create` pops the next item and raises it if it is an exception. An empty script raises `ScriptExhausted` (an `AssertionError`).
- `requests: list[ModelRequest]` and `counted: list[ModelRequest]` record the calls.
- `session()` yields itself.

### `AnthropicModel`
- `AnthropicModel(*, api_key: SecretStr, model: str, policy: RetryPolicy, client_factory: Callable[[], AsyncAnthropic] | None = None, sleep: Callable[[float], Awaitable[None]] = anyio.sleep, rand: Callable[[], float] = random.random)`.
- `classmethod from_settings(settings: Settings) -> AnthropicModel`.
- `session()` creates an `AsyncAnthropic(api_key=…, max_retries=0)` (or the factory's client) and closes it on exit. Tests pass a factory whose client uses a mock HTTP transport (E10).
- `RetryPolicy(max_retries: int, base_seconds: float, cap_seconds: float)`.
- `def backoff_delay(retry: int, policy: RetryPolicy, r: float) -> float` (R7 formula).
- `def is_retryable(error: BaseException) -> bool`: `APIConnectionError` (timeouts included) or `APIStatusError` with a status in {408, 409, 429} or ≥ 500.
- `def to_params(request: ModelRequest, model: str) -> dict[str, object]`: the E11 keys for `create`. `count_tokens` receives the same minus `max_tokens` and `output_config`.
- `def from_message(message: anthropic.types.Message) -> ModelReply`: blocks map one to one. `usage.cache_creation` splits writes into 5m and 1h; without it, all writes count as 5m.
- Each retry logs one WARNING with the operation, status and delay.

### `ToolPort` / `TextProgress`
- `class ToolPort(Protocol)`: `async def list_tools(self) -> tuple[ToolSpec, ...]`; `async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome`. `ToolClient` satisfies it structurally.
- `class TextProgress(Protocol)`: `def missing(self) -> tuple[str, ...]` (notice ids). `NoticeDraft` satisfies it.

### `LoopOutcome` / `LoopConfig` / `LoopLog`
- `class LoopOutcome(StrEnum)`: `DONE = "done"`, `SKIPPED = "skipped"`, and one member per fallback, whose values are `fallback:budget_exceeded`, `fallback:turn_cap`, `fallback:refusal`, `fallback:max_tokens`, `fallback:missing_texts` and `fallback:unexpected_stop`. Aborts are not members: the trace layer formats `aborted:<Class>`.
- `LoopConfig(max_turns: int, prompt_token_limit: int, max_tokens: int, effort: Effort)`.
- `LoopLog`: a mutable dataclass the caller creates per snapshot, so partial records survive an exception (E21). It holds `outcome: LoopOutcome | None`, `model_calls: list[ModelCallRecord]` (usage and latency, no cost), `tool_calls: list[ToolCallRecord]` and `thinking: list[str]`.

### `Coordinator`
- `Coordinator(model: ModelPort, tools: Callable[[], AbstractAsyncContextManager[ToolPort]], system: str, allowed: tuple[str, ...], config: LoopConfig, clock: Callable[[], float] = time.perf_counter)`. It holds no prices (R13).
- `async def run(self, snapshot_id: str, brief: str, progress: TextProgress, log: LoopLog) -> LoopOutcome`: sets `log.outcome`. `snapshot_id` is used for the R6 WARNING and for log context only.
- **Offered tools** = the server's tools named in `allowed`, in `allowed` order. An allowed name the server lacks raises `ValueError` (a wiring bug).
- **Algorithm (R3–R6):** `messages = [user(brief)]`; then, while turns remain:
  - build the request; `count_tokens`; over the limit → `fallback:budget_exceeded`;
  - `create`; record usage and latency; append the reply's content unchanged;
  - dispatch on the stop reason: `tool_use` → run the calls, append the results, and return `done` if `missing()` is empty; `end_turn` → reminder or `fallback:missing_texts`; the other R3 stops → their fallback;
  - when no turn is left → `fallback:turn_cap`.
- Messages are only ever appended, kept as tuples rebuilt with `(*old, new)`, so earlier items are never mutated (R5).

### `render_brief` / `render_reminder`
- `def render_brief(snapshot_id: str, turno_id: str, position: ShiftPosition, alerts: Sequence[Notice], news: Sequence[Notice]) -> str`: the R2 instruction line, `\n`, then compact JSON.
- `def render_reminder(missing: Sequence[str]) -> str`: a constant sentence plus the ids, comma-separated.

### `build_coordinator`
- `COORDINATOR_TOOLS: Final = (*READ_TOOLS, *WRITE_TOOLS)`, with the names copied as literals so `agents` does not import `mcp_server.server`. A test checks they are equal.
- `def load_prompt() -> str`: `importlib.resources` over `agents/prompts/coordinator.md`.
- `def build_coordinator(settings: Settings, model: ModelPort, tools: Callable[[], AbstractAsyncContextManager[ToolPort]]) -> Coordinator`: builds `LoopConfig` from settings.

### `NoticeDraft`
`cases/draft.py`: `NoticeDraft(notices: SnapshotNotices, max_chars: int)`.
- `required() -> tuple[str, ...]`: alert ids, then news ids in report order (R1).
- `missing() -> tuple[str, ...]` and `written() -> tuple[str, ...]`, both in decision order.
- `write_alert(case_id: str, texto: str) -> str` and `write_news(texts: Sequence[tuple[str, str]]) -> tuple[str, ...]`: R8 and R9 check order and messages; a news write is atomic.
- `build() -> SnapshotNotices`: rebuilds each written notice with `Notice.model_validate({**notice.model_dump(), "texto": text})`. The report is rebuilt from the rebuilt news decisions in the same order; `casos_activos` and `to_mark` are unchanged. It is idempotent.
- Refusals are `RejectedRequest` subclasses: `NoticeNotDecided`, `ReportNotDecided`, `TextAlreadyWritten`, `NotNews`, `DuplicateNews`, `MissingNews`, `InvalidText`.

### `NoticeTextWriter` / `SnapshotFrame.notices`
- `class NoticeTextWriter(Protocol)` in `mcp_server/context.py`: `write_alert`, `write_news`, `missing` (the `NoticeDraft` signatures).
- `SnapshotFrame` gains `notices: NoticeTextWriter | None = None`, so 006 call sites stay valid.
- **Why on the frame, not on `ToolContext` or a second holder:** the writer lives exactly as long as the frame. One `entered` sets and clears both, so a write outside the snapshot is impossible, and no second holder can fall out of sync.
- `mcp_server` sees only the protocol; the runner passes the draft. 008's per-run writers (`CaseWriter`) go on `ToolContext` (Q-24).

### Write tools
- `mcp_server/write_tools.py`: `class NewsText(BaseModel)` with `case_id: str` and `texto: str`.
- `def emit_alert(frames: FrameHolder, case_id: str, texto: str) -> str` and `def emit_shift_report(frames: FrameHolder, textos: Sequence[NewsText]) -> str`.
- Both read `frames.current().notices`; `None` raises `RuntimeError`, a wiring bug that reaches the model as the generic error.
- Both return compact JSON `{"escritos": …, "pendientes": …}`.

### `build_server`
- `WRITE_TOOLS: Final = ("emit_alert", "emit_shift_report")`.
- `build_server(ctx, frames, tools: Collection[str] = READ_TOOLS) -> MCPServer` registers only the named tools (an unknown name raises `ValueError`), each as an `async def` wrapper with the same `RejectedRequest` → `ToolError` mapping.

### Telemetry
- `Usage(input_tokens, output_tokens, cache_read_tokens, cache_write_5m_tokens, cache_write_1h_tokens)` (ints ≥ 0), with the property `prompt_tokens`.
- `PriceCard(input, cache_write_5m, cache_write_1h, cache_read, output: Decimal; long_context_threshold: int; long_context_multiplier: Decimal)`.
- `def cost_usd(usage: Usage, card: PriceCard) -> Decimal` (R13).
- `ModelCallRecord(turn, stop_reason, usage, latency_ms: int)` and `ToolCallRecord(turn, name, arguments, is_error, result_chars, error, latency_ms)`.
- `TraceLine` (frozen pydantic, the R14 fields) and `RunTotals(snapshots, called, model_calls, tokens…, usd)`. `usd` is written as a JSON number rounded to 8 decimals.
- `def build_line(*, snapshot_id, turno_id, status, decision, outcome: str, required, model_calls: Sequence[ModelCallRecord], tool_calls, thinking, notices_agent, notices_template, report_id, card: PriceCard) -> TraceLine`: computes each call's `usd` and the totals here (R13).
- `def abort_outcome(error: BaseException) -> str`: returns `aborted:<type(error).__name__>`.
- `def trace_path(directory: Path, started: datetime) -> Path`.
- `class TraceWriter(path: Path)`:
  - `stage(line)` replaces any staged line, with a WARNING;
  - `after_commit()` appends the staged line and clears it; it is a no-op when nothing is staged (run start);
  - `write_now(line)` appends aborted lines.
  - Both writers catch `OSError`, log it at ERROR and return, so they never mask the pipeline's original exception. Files are opened in append mode only when writing.
- `def read_trace(path: Path) -> tuple[TraceLine, ...]` and `def run_totals(lines: Iterable[TraceLine]) -> RunTotals`.

### `SnapshotDecision` / `ThresholdPipeline.decide` / `finish`
- `SnapshotDecision(snapshot: Snapshot, shift: Shift, position: ShiftPosition, metrics: Mapping[Combination, CombinationMetrics], notices: SnapshotNotices)`.
- `decide(snapshot, shift, position) -> SnapshotDecision`: spec 004's steps up to `build_snapshot_notices`. It **writes** releases and lifecycle rows to the open unit of work. R11 and R12 rely on the unit's rollback to undo them when the snapshot aborts. 008 adds a `redecide` step (re-run `track` with raises, Q-27).
- `finish(snapshot_id: str, notices: SnapshotNotices) -> None`: `save` once, then mark `to_mark`.

### `AgentPipeline`
- `class OpenUnit(Protocol)`: `current_snapshot() -> str | None`.
- `class NoticeSteps(Protocol)`: `decide`, `finish`. `ThresholdPipeline` satisfies it.
- `AgentPipeline(steps: NoticeSteps, unit: OpenUnit, frames: FrameHolder, coordinator: Coordinator, trace: TraceWriter, prices: PriceCard, max_chars: int)` implements `SnapshotPipeline`.
- `process`:
  1. `decide`, then create the draft;
  2. with no required text → `finish(draft.build())`, then stage a `skip` line;
  3. otherwise: the R11 check, enter the frame with the draft, `anyio.run(coordinator.run, sid, brief, draft, log)`, leave the frame, `finish(draft.build())`, then stage a `call` line built by `build_line`;
  4. at the `anyio.run` boundary, a `BaseExceptionGroup` with exactly one leaf exception is unwrapped, and that exception is re-raised (`raise leaf from None` keeps its own traceback). Other groups propagate as is;
  5. on any `Exception`, `write_now` an aborted line (`abort_outcome`) from `log`, then re-raise the original exception.
- `def build_agent_pipeline(settings: Settings, registry: SqliteRegistry, ctx: PlantContext, policy: HeldOutPolicy, model: ModelPort, trace: TraceWriter) -> AgentPipeline`:
  - builds the `ToolContext`, the `FrameHolder`, `build_server(..., COORDINATOR_TOOLS)`, the coordinator and the `PriceCard`;
  - builds the tool factory, annotated once: `tools: Callable[[], AbstractAsyncContextManager[ToolPort]] = lambda: ToolClient(server)`.

### `PostCommitChain`
`PostCommitChain(steps: Sequence[PostCommit])`: `after_commit` runs every step in order. Each `Exception` is logged with `logger.exception`, and the next step still runs.

### Settings
R16 fields with `Field` bounds. A model validator checks `anthropic_retry_cap_seconds >= anthropic_retry_base_seconds`. Prices are typed `Decimal`.

## Design notes
- **Threading (ADR-0013).** `anyio.run` runs the event loop on the runner's thread, so the `async def` tool wrappers, reads and draft writes alike, touch the registry connection there. Never `check_same_thread=False`. E20 uses a file-backed registry to guard it. Pipeline tests are sync, because `anyio.run` cannot nest inside an anyio test.
- **Append-only history.** Replayed thinking with an edited history gives a 400 (D1). So the loop never trims, summarizes or re-orders, and a reminder is a new turn. Fresh conversations per snapshot keep requests small instead (FR-29).
- **Why own retries.** The SDK's built-in retries are invisible to the trace and to tests. Owning them gives one policy for `create` and `count_tokens`, injectable sleep and jitter, and a single `ModelCallFailed` type for the runner.
- **Why a fallback, not an abort, for model behavior.** A refusal or a wandering loop is about wording, not about facts: the template text is already correct (spec 004). Aborting would block an unattended run (FR-33) on cosmetics. API outages, by contrast, are resumable (NFR-10).
- **Done without a closing request.** The loop stops once nothing is missing, which saves one request per snapshot. The unanswered `tool_use` is harmless, because the history is discarded.
- **Code computes (ADR-0002).** Write tools can change only `texto` of notices code decided. Refusals teach the model, and the validators check the rebuild.
- **Extension points.**
  - **008:** `NoticeDraft` gains causes and evidence. `raise_severity` must re-run `track` (Q-27), which is runner work. So 008's frame writer is a runner-side adapter (draft plus `NoticeSteps.redecide`) that implements the writer protocols and rebases the draft by `(tipo, case_id)`. New write tools register through `build_server(tools=…)`.
  - **009:** analysts are more `Coordinator` instances with read-only `allowed`.
  - **010:** hooks wrap `ToolPort.call` and the stop check, and fill `hooks`.
  - **011:** caching adds breakpoints in `to_params`; structured output validates in the loop.

## Test strategy
- **Unit, no I/O:**
  - `cost_usd` (E17), `backoff_delay` (E10 values), `NoticeDraft` (E1, E14, write refusals at draft level only when not covered by E12/E13);
  - `render_brief` (E2) and settings (E19).
- **Loop** (`tests/unit/agents/`, `@pytest.mark.anyio`): `FakeModel` and a fake `ToolPort` for E3–E9.
- **Conversion and retries:** E10 and E11 with a mock HTTP transport and an injected sleep. No network.
- **Tools through `ToolClient`:** E12 and E13 over the in-process server, with a draft in the frame and E41's S003/S004 decisions built from a `:memory:` registry.
- **Pipeline** (sync): E15 and E16 with a fake `NoticeSteps`, a fake `OpenUnit`, `FakeModel` and a counting sink.
- **Telemetry:** E18 with `tmp_path` and `caplog`.
- **Integration** (`tests/integration/test_agent_runner.py`): E20 and E21 over `notice_builders.write_series`, with a file-backed registry and a `RecordingNotifier`.
- **Imports:** E22 extends `tests/unit/test_import_boundaries.py`. `telemetry` joins the SDK-free scan; the R17 probes check `anthropic` and `mcp` separately; `agents` gets a module-level allow-list (`mcp_server.types` only).
- One layer per rule; tests cite E ids; at most 2 `Risk:` extras per group.

## Risks
- **SDK surface** (`http_client` type in the httpx2-based 1.15, the `output_config` and `thinking.display` params, `usage.cache_creation`) is contained in `anthropic_model.py`; E10 and E11 pin it.
- **The prompt file missing from the wheel:** `load_prompt` is tested from the installed package.
- **Haiku loops or skips emitting:** the turn cap, the reminder, the fallback and the trace make it visible and cheap.
- **Count drift** of `count_tokens`: the 5% margin; real usage is in the trace.
- **Exception groups:** `mcp.Client` runs an anyio task group, so errors inside `async with ToolClient` arrive as `BaseExceptionGroup`. The single-leaf unwrap at the `anyio.run` boundary keeps `RunAborted.cause` meaningful; E21 pins it.
- **The `ThresholdPipeline` refactor** must keep 004's E40–E45 green.
