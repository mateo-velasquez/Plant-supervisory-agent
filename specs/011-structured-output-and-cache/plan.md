# 011 · Structured output and prompt caching — Plan

## Modules

| File | Change | Responsibility |
|---|---|---|
| `agents/output.py` | New | `SUPPORTED_KEYWORDS`, `DROPPED_KEYWORDS`, `strict_schema`, `investigator_output_schema`. Pure, no SDK. |
| `agents/prefix.py` | New | `prefix_bytes`, `prefix_hash`, `PrefixMonitor`. Pure except logging. |
| `agents/model.py` | Changes | `ModelRequest.output_schema` (last field, default None). |
| `agents/anthropic_model.py` | Changes | `_ephemeral`, `_base_params`. `to_params` = base plus `max_tokens`, `output_config` (with `format`) and the two cache markers. `_count_params` = base. |
| `agents/loop.py` | Changes | `LoopConfig.max_notes`; `Coordinator(..., output_schema, prefix_monitor)`; offered schemas sanitized; one hash per run on every record; the note counter replaces `reminded`. |
| `agents/factory.py` | Changes | The investigator gets the format, `max_notes` from the corrections setting and a monitor. The coordinator gets a monitor. |
| `agents/investigator.py` | Docstring | `ProposalReview`: "correction notes up to the loop's budget". |
| `agents/fake_model.py` | Unchanged | It already records requests and replays scripted `Usage`. It enforces no schema (X1). |
| `runner/review_step.py` | Changes | The R4 WARNING (I7). |
| `telemetry/trace.py` | Changes | `prefix_hash` on `ModelCallRecord` and `TraceModelCall`; three cache sums on `RunTotals` and `AgentRunTotals`. |
| `config.py`, `.env.example` | Adds | `investigator_output_corrections` / `INVESTIGATOR_OUTPUT_CORRECTIONS=1`. |
| `tests/agent_builders.py`, `tests/builders.py` | Changes | `make_coordinator(max_notes=, output_schema=, prefix_monitor=)`; `FakeTools.criteria`, `FakeTools.suffix`; `SETTINGS_ENV_NAMES`. |

## Types and interfaces

### `strict_schema`
`agents/output.py`:
- `SUPPORTED_KEYWORDS: Final[frozenset[str]]` and `DROPPED_KEYWORDS: Final[frozenset[str]]` (R1). They are used only for membership tests, never iterated.
- `strict_schema(schema: Mapping[str, object]) -> dict[str, object]` (R1 steps 1–4, in order). Raises `ValueError` with the R1 messages. One private recursive helper takes `(node, path, is_root)`.
- `investigator_output_schema() -> Mapping[str, object]`, `functools.cache`d: `strict_schema(InvestigatorOutput.model_json_schema())`. It is the same object every call, and callers never mutate it.

### Prefix
`agents/prefix.py`:
- `prefix_bytes(system: str, tools: Sequence[ToolSpec], output_schema: Mapping[str, object] | None) -> bytes` (R8; `json.dumps(..., default=dict)`).
- `prefix_hash(system: str, tools: Sequence[ToolSpec], output_schema: Mapping[str, object] | None) -> str`: `hashlib.sha256(prefix_bytes(...)).hexdigest()`.
- `class PrefixMonitor`, no constructor arguments:
  - `on_run(self, agent: AgentName, snapshot_id: str, prefix_hash: str) -> None`;
  - `on_call(self, agent: AgentName, snapshot_id: str, turn: int, usage: Usage, prefix_hash: str) -> None`.

  State: `_last: dict[AgentName, str]`. It logs to `logging.getLogger(__name__)` (R9).

### Model port
`ModelRequest(system: str, tools: tuple[ToolSpec, ...], messages: tuple[Message, ...], max_tokens: int, effort: Effort, output_schema: Mapping[str, object] | None = None)`. Every existing positional construction stays valid.

### Adapter
- `_ephemeral() -> dict[str, str]`: a fresh `{"type": "ephemeral"}` per call.
- `_base_params(request: ModelRequest, model: str) -> dict[str, object]`: `model`, `system` (one text block, no marker), `tools` (`input_schema: dict(t.input_schema)`, `strict: True`), `messages`, `thinking`, `tool_choice`.
- `to_params(request, model) -> dict[str, object]`:
  - the base plus `max_tokens`;
  - `output_config` = `{"effort": ...}`, plus `{"format": {"type": "json_schema", "schema": dict(request.output_schema)}}` when it is set;
  - `system[0]["cache_control"] = _ephemeral()` and top-level `cache_control = _ephemeral()`.
- `_count_params(request, model) -> dict[str, object]`: `_base_params(request, model)`.
- The adapter does not sanitize (I4).

### Loop
`agents/loop.py`:
- `LoopConfig(max_turns: int, prompt_token_limit: int, max_tokens: int, effort: Effort, max_notes: int = 1)`.
- `Coordinator(model, tools, system, allowed, config, clock=…, *, agent="coordinator", hooks=None, criteria_prompt=None, output_schema: Mapping[str, object] | None = None, prefix_monitor: PrefixMonitor | None = None)`.
- `run` signature unchanged. Inside it:
  - `offered = tuple(ToolSpec(s.name, s.description, strict_schema(s.input_schema)) for s in await self._offered(port))`;
  - after the system is composed, `prefix = prefix_hash(system, offered, self._output_schema)`, then `monitor.on_run(self._agent, snapshot_id, prefix)`.
- `_loop`:
  - builds `ModelRequest(..., self._output_schema)`;
  - appends `ModelCallRecord(turn, reply.stop_reason, reply.usage, latency, prefix)`;
  - calls `monitor.on_call(self._agent, snapshot_id, turn, reply.usage, prefix)` after each reply;
  - keeps `notes_sent: int` instead of `reminded`, and returns `end_review.exhausted` when `notes_sent >= config.max_notes`.
- `EndReview.exhausted` docstring: "The outcome when the note budget is spent."

### Factory
- `_config(settings, max_turns)` is unchanged.
- `build_coordinator(...)`: as today, plus `prefix_monitor=PrefixMonitor()`. `max_notes` is `LoopConfig`'s default (Q-43).
- `build_investigator(...)`:
  - `replace(_config(settings, settings.investigator_max_turns), max_notes=settings.investigator_output_corrections)`;
  - `output_schema=investigator_output_schema()`;
  - `prefix_monitor=PrefixMonitor()`.
- Each factory call builds its own monitor. A shared one would be equally correct, since the agent is an argument.

### Review step
`InvestigatorStep.run`: after `run_in_frame`, it logs the R4 WARNING on `logging.getLogger(__name__)` when the outcome is `INVALID_OUTPUT`, or `TURN_CAP` with `review_log.rejections` non-empty. Nothing else changes.

### Settings
`investigator_output_corrections: int = Field(default=1, ge=0)`, in the multi-agent block. There is no cross-field validator. `.env.example`: `INVESTIGATOR_OUTPUT_CORRECTIONS=1`, with the block comment amended to say that this one may be 0.

### Trace
- `ModelCallRecord(turn: int, stop_reason: str, usage: Usage, latency_ms: int, prefix_hash: str | None = None)`.
- `TraceModelCall.prefix_hash: str | None = None`, copied in `_costed`.
- `AgentRunTotals` and `RunTotals` each gain `cache_read_tokens`, `cache_write_5m_tokens` and `cache_write_1h_tokens: int = 0`.

  `run_totals` sums them from `row.totals` (run level) and from each costed call's `usage` (per agent).

### Test builders
- `make_coordinator(..., max_notes: int = 1, output_schema: Mapping[str, object] | None = None, prefix_monitor: PrefixMonitor | None = None)`.
- `FakeTools`:
  - `criteria: str = CRIT`, served by `get_prompt`;
  - `suffix: str = ""`, appended to every description;
  - both plain attributes that tests may reassign between runs.

## Design notes
- **Why the format is a `Coordinator` keyword, and `max_notes` lives in `LoopConfig` (I1, I3).**
  - `LoopConfig` is a frozen dataclass of loop limits. A schema dict would make it unhashable.
  - The schema is per agent, not a limit.
  - `max_notes` sits next to `max_turns` (already per agent), needs no change to `EndReview` or the test fakes, and its default 1 reproduces 007–010 exactly: one counter for hook and review notes.
  - The factory overrides it with `replace`, so the default lives in one place.
- **Why the format is also a request field.** The port stays SDK-free, and `FakeModel` sees the schema, so E5 and E14 assert it without the adapter.
- **Why the adapter always caches (I2).** Both agents always want the same layout, so there is nothing to toggle, and a flag would be one more input that could drift. Markers are adapter syntax, like `strict`. `_ephemeral()` returns a fresh dict, so no request can mutate a shared marker.
- **One base for both param builders (I10).** `to_params` and `_count_params` cannot drift apart: the count is the base, and the request adds only the fields count must not carry. E15 checks both against the SDK's TypedDicts.
- **Why the loop sanitizes (I4).** The hash must describe the content sent, and the loop is the only producer of `ModelRequest`. Sanitizing once per run keeps the tools byte-identical across turns and snapshots. Key order is stable by construction: `strict_schema` walks each node's own keys in input order and appends `required` and `additionalProperties` in fixed positions (E1d). The hash also uses sorted keys, so it covers content, not order.
- **Two-tier sanitizer (I5).**
  - Silently dropping an unknown keyword could remove a constraint nobody noticed.
  - Sending one returns a 400 in the held-out run.
  - The fixed DROPPED set covers what pydantic and FastMCP emit today, and anything else raises in CI through E2, which runs over every registered tool.
- **Monitor without an agent (I6).** The loop knows its agent, and the monitor keeps a per-agent map, so a shared instance cannot mix agents. Only factory-built agents log, so the 007 E6 warnings assertion stays unchanged.
- **Warning in the step (I7).** The step knows the snapshot and the `ReviewLog`. A turn cap reached while correcting is the same failure seen from outside, so it gets the same warning; a turn cap with no rejection (tool turns only) does not.
- **No new coordinator review (D3).** Its output is tool arguments, already validated three ways (strict schema, server validation, hooks plus draft).
- **Cache markers vs count (R7).** The SDK's `count_tokens` type accepts `cache_control`, but the docs do not say what it does there. The base carries none, so the count stays identical to 010's.

## Test strategy
- **Unit, no I/O:**
  - sanitizer (E1);
  - prefix bytes (E9);
  - monitor (E11a, E11b);
  - settings (E8);
  - trace (E12);
  - adapter params (E3, E4a, E4b);
  - SDK shape (E15, `Risk:`).
- **Adapter over the mock transport:** E4c (existing `Harness`).
- **MCP through `ToolClient`:** E2 (`incident_tool_context`, every registered tool, `Risk:`).
- **Loop with `FakeTools`:** E7, E10, E11c, E11c′, E11d.
- **Factory:** E5.
- **Step (`s010_rig` in `test_review_step.py`):** E6, with `caplog` filtered by the `plant_monitor.runner.review_step` logger.
- **Integration** (`tests/integration/test_output_cache_runner.py`, new): E13 (`run_full` helpers, `Recorder`, `query`) and E14 (`run_ids`, HEAD). Helpers come `from multi_agent_builders import ...`, `from incident_builders import ...`, `from builders import ...`, never `from tests.builders`.
- Each test cites its spec id in its name or docstring.

## Risks
- **Silent cache miss.** For example, a timestamp creeping into a tool description. The hash is logged on change (E11). E14 proves one hash per agent over a series, and E10 that the brief never enters it.
- **Schema 400 from an unsupported feature.** Guarded by the two-tier sanitizer, which raises on anything unknown, and by E2 over the investigator schema and every registered tool.
- **A param the SDK or API does not know.** E15 checks every top-level, tool and `output_config` key against the SDK's TypedDicts, with no network.
- **Cache invalidated by a format change.** The format is built once (`functools.cache`) from a frozen model, and it is part of the hash. E14 asserts that every investigator request carries the same schema and the coordinator none.
- **Strict mode makes optional parameters required.** One case today: `raise_severity`'s `mercado: Market | None = None`. It is safe because it is nullable: the model sends `null` for "any market", exactly what the default meant. E2 asserts that every property missing from a server's `required` is nullable, so a new non-nullable optional parameter fails in CI.
- **Test churn.** Limited to 007 E11's key set. `ModelRequest`, `LoopConfig` and `ModelCallRecord` gain defaulted last fields, so existing constructions compile unchanged.
