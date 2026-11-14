# 011 · Structured output and prompt caching — Spec

- **Status:** Implemented
- **Requirements:** FR-02 (hardening), FR-34, FR-35, NFR-02, NFR-03, NFR-07, NFR-10
- **Stories:** —
- **Decisions:** ADR-0017 (structured output, cached stable prefix and Batch API rejected), ADR-0007, ADR-0013, ADR-0014, ADR-0015, ADR-0016. Q-56–Q-63 decided; Q-44 and Q-52 amended. Q-10, Q-43, Q-53 reused unchanged.
- **Week:** W5

## Goal
Make model output a validated structure at the API and keep code control behind it, bill the stable prompt prefix at the cache-read price, make a silent cache miss visible, and prove with synthetic fixtures that a repeated snapshot changes nothing. This prepares the single run of the held-out days.

## Scope
- **In:** a schema sanitizer (`agents/output.py`); the investigator's output format; `strict: true` on every offered tool; a configurable correction budget; cache breakpoints in the Anthropic adapter; the prefix bytes and hash and a drift monitor (`agents/prefix.py`); `prefix_hash` in the trace and cache sums in run totals; an idempotency integration on the SQLite registry; the Batch API decision (ADR-0017).
- **Out:** the one-command CLI, cost and duration report (012); the navigable trace (013); any prompt wording change; reading real data. The paid days 1–7 run is a manual task (T7), not a test.

## Decisions
- **D1 · API-native plus code control (Q-56).** The investigator request carries `output_config.format` with the sanitized `InvestigatorOutput` schema. Every tool of both agents is sent with `strict: true`. `check_output` stays the second barrier, and everything the sanitizer drops is still enforced by code.
- **D2 · Corrections (Q-57).** The investigator's note budget is `Settings.investigator_output_corrections` (default 1). When it runs out, the outcome is today's `fallback:invalid_output`, plus a WARNING. It never aborts: "fails loudly" means visible in the log and the trace. The coordinator keeps one note (Q-43).
- **D3 · Coordinator (Q-58).** No new end-of-turn review: strict tools, the server's schema validation, the hooks and the final draft rebuild stay. ADR-0016's follow-up is met by the investigator's `ProposalReview`, which runs as the `EndReview` behind the on-stop hook phase.
- **D4 · Cache (Q-59).** One explicit breakpoint on the single `system` block (it covers tools and system), plus top-level automatic caching for the conversation tail. TTL 5 minutes. Thinking, effort and format stay fixed per agent. `count_tokens` carries no cache marker.
- **D5 · Drift (Q-60).** A sha256 `prefix_hash` over canonical bytes on every model call. A per-agent monitor logs WARNINGs and never aborts.
- **D6 · Idempotency (Q-61).** Synthetic fixtures only. The real S034 repeat is confirmed by the user's paid run log.
- **D7 · Batch API rejected (Q-62).** See ADR-0017.
- **D8 · Interface choices** (taken by the spec writer; see plan):
  - **I1** the note budget is `LoopConfig.max_notes: int = 1`. It counts on-stop hook notes and review notes together, as 010's single `reminded` flag did.
  - **I2** the adapter always places the cache markers; `ModelRequest` gets no cache field.
  - **I3** the format travels as `ModelRequest.output_schema` (default None), set from `Coordinator(..., output_schema=)`.
  - **I4** the loop sanitizes the offered tool schemas once per run, so `ModelRequest.tools`, `FakeModel` and the hash all see the sent schemas. The adapter only adds `strict: true`.
  - **I5** the sanitizer works in two tiers. A fixed DROPPED set of known-harmless keywords is removed. Any other keyword outside SUPPORTED raises, so an unforeseen feature fails in CI (E2) instead of being silently dropped or sent.
  - **I6** the monitor is injected (`prefix_monitor`, default None) and holds no agent: the loop passes its own `agent` on every call, and the monitor keeps the last hash per agent. One instance may serve both agents. The factory always passes one. Loops built in 007–010 tests log no new warning, while the hash is always recorded.
  - **I7** the corrections WARNING is logged by `InvestigatorStep.run`, not by the loop. It fires on `fallback:invalid_output`, and on `fallback:turn_cap` when control rejected at least one output.
  - **I8** `RunTotals` and `AgentRunTotals` gain the three cache sums.
  - **I9** `system` stays one string in the port and goes out as one text block.
  - **I10** the count params are `_base_params` (they keep `strict: true` and drop `output_config`). `to_params` extends the same base.
  - **I11** `build_investigator` sets `max_notes` with `dataclasses.replace` on `_config(...)`, so `LoopConfig` holds the only default (1).
  - **I12** E15 imports `anthropic` types in `tests/unit/agents/test_anthropic_model.py`. The import scan (`test_import_boundaries.py`, E22) only covers `src`, and that test file already imports `anthropic`.

## Behavior

### R1 · Schema sanitizer (FR-34, Q-56, I5)
`strict_schema(schema) -> dict[str, object]` is pure: a new dict, input untouched, same output for the same input, and idempotent.
- **Keyword sets.**
  - SUPPORTED = {`type`, `properties`, `required`, `additionalProperties`, `items`, `enum`, `const`, `anyOf`, `allOf`, `$ref`, `$defs`, `description`, `minItems`}.
  - DROPPED = {`title`, `default`, `examples`, `discriminator`, `minLength`, `maxLength`, `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `format`, `pattern`, `maxItems`}, plus `minItems` above 1.
  - `oneOf` is renamed to `anyOf`.
  - Any other keyword raises.
- **Per node, in this order:**
  1. An `allOf` with one item is merged into its node. An `allOf` of several items that holds a `$ref` raises.
  2. A node holding `$ref` keeps only `$ref` (and `$defs` at the root). `$ref` must be local (`#/$defs/<name>`).
  3. The node's own keys are walked in input order: DROPPED keys are removed, `oneOf` → `anyOf` in place, SUPPORTED keys are kept in place, and any other key raises. Values are sanitized recursively (`properties`, `items`, `anyOf`, `allOf`, `$defs`). The SUPPORTED set is never iterated, so the output keeps the input's key order.
  4. An object node (`type` `object` or `properties` present) gets `required` listing every property in property order: rewritten in place, or appended when absent. It also gets `additionalProperties: false`, kept in place or appended last. An `additionalProperties` that is `true` or a schema raises. A non-root `{"type": "object"}` without `properties` raises (the root may have none, as with `FakeTools`).
- A `$ref` cycle among `$defs`, or nested `$defs`, raises.
- Errors are `ValueError("unsupported schema feature: <feature> at <path>")`, with path `#` for the root and `#/properties/x` style below it. `<feature>` is the keyword, `non-local $ref <ref>`, or `object without properties`; a cycle gives `… recursive $defs <name>`.

### R2 · Investigator output format (FR-34, Q-56, I3)
`investigator_output_schema()` = `strict_schema(InvestigatorOutput.model_json_schema())`, built once and identical on every call. `build_investigator` passes it as `output_schema`. Every investigator `ModelRequest` carries it, and every coordinator request carries None. Prompts are unchanged.

### R3 · Strict tools (FR-34, Q-56, Q-58, I4)
At each run the loop offers `ToolSpec(name, description, strict_schema(input_schema))` for the allowlisted tools, in allowlist order. A schema that cannot be sanitized raises out of `run` (fail-closed, like a missing allowed tool). The adapter adds `"strict": true` to every tool. The tool servers keep validating the arguments in full (010 X4 unchanged). Strict mode makes every property required. The one optional parameter today, `raise_severity`'s `mercado: Market | None = None`, stays safe because it is nullable (`anyOf` with `{"type": "null"}`): the model sends `null` for "any market".

### R4 · Correction budget and terminal fallback (FR-34, Q-57, Q-43, Q-52, I1, I7)
- `LoopConfig.max_notes` (default 1): at an `end_turn` with a note (from an on-stop hook or from the review), when `max_notes` notes have already been sent, the loop returns `review.exhausted`; otherwise it appends the note as a user turn.
- `build_investigator` sets `max_notes = settings.investigator_output_corrections` (I11), and `build_coordinator` keeps the default 1.
- The note is `ProposalReview`'s, unchanged: `CORRECTION_HEADER` and then `- <error>` per error.
- When `InvestigatorStep.run` gets `fallback:invalid_output`, or `fallback:turn_cap` with at least one rejection recorded, it logs one WARNING `<sid> investigator output invalid after <n> rejected outputs: <outcome>; causes stay no_declarada` (n = `len(review_log.rejections)`). Accepted stays `()`, marks follow Q-52/Q-53, and the trace outcome is the investigator's outcome (009 R14).
- The turn cap still applies. A budget larger than the turns allow ends in `fallback:turn_cap`, with the same effect and the same WARNING. There is no new Settings validator.

### R5 · Code control stays (FR-34, 009 R5, §6)
`check_output` is unchanged and runs on every investigator `end_turn` text: size, JSON, schema, scope, states, citations and the `no_declarada` refusal. The API schema still allows `no_declarada` in `categoria` (the enum is shared), so control refuses it.

### R6 · Cache layout (FR-35, NFR-03, Q-59, I2, I9)
Both param builders start from one base. `_base_params` holds `model`, `system` = `[{"type": "text", "text": request.system}]`, `tools` (each with `strict: true`), `messages`, `thinking` and `tool_choice`. `to_params` = base plus:
- `max_tokens`;
- `output_config` = `{"effort": e}`, plus `"format": {"type": "json_schema", "schema": dict(request.output_schema)}` when it is set;
- `cache_control` = `{"type": "ephemeral"}` on `system[0]`;
- top-level `cache_control` = `{"type": "ephemeral"}`.

Each marker is a fresh dict from `_ephemeral()`. `thinking` and `tool_choice` are unchanged, and message blocks carry no markers. That makes 2 breakpoints (the limit is 4) with a 5-minute TTL. Nothing per snapshot (ids, timestamps, deltas, brief, task) is in tools or system: those go in messages, after the explicit breakpoint.

### R7 · Count params (NFR-02, Q-59, I10)
`_count_params` = `_base_params` only: no `max_tokens`, no `output_config`, no cache marker. The tools keep `strict: true`. A unit test with no network checks every param key against the SDK's TypedDicts (E15). The budget guard (007 R6) is otherwise unchanged.

### R8 · Prefix bytes and hash (FR-35, Q-60)
`prefix_bytes(system, tools, output_schema)` = `json.dumps({"system": system, "tools": [{"name", "description", "input_schema"} per tool in order], "output_schema": output_schema}, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=dict).encode("utf-8")`. `default=dict` serializes any non-dict `Mapping`. The hash describes the content sent; key order does not affect it. `prefix_hash(...)` is its sha256 hex digest (64 lowercase characters). The loop computes it once per run from the composed system, the sanitized offered tools and its `output_schema`. Every `ModelCallRecord` of the run carries it. Messages never enter it.

### R9 · Drift monitor (FR-35, Q-60, I6)
`PrefixMonitor()` takes no agent. It keeps the last run's hash per agent in memory (`dict[AgentName, str]`), for one run of the series:
- `on_run(agent, sid, h)`: when that agent has a previous hash that differs, it logs `<agent> prefix changed at <sid>: <old> -> <new>`;
- `on_call(agent, sid, turn, usage, h)`: when `turn ≥ 2` and `usage.cache_read_tokens == 0`, it logs `<agent> call <turn> at <sid> read no cached tokens (prefix <h>)`.

Both log at WARNING on logger `plant_monitor.agents.prefix`. Neither ever raises. The loop passes its own `agent`, calling `on_run` after composing the system and `on_call` after each reply.

### R10 · Trace (Q-44 amended, I8)
- `ModelCallRecord.prefix_hash` and `TraceModelCall.prefix_hash` are `str | None = None`. `_costed` copies the hash, for both the coordinator and the investigator. Lines without the key parse to None.
- `RunTotals` gains `cache_read_tokens`, `cache_write_5m_tokens` and `cache_write_1h_tokens`, and so does `AgentRunTotals`. All default to 0 and are summed like `input_tokens`.

### R11 · Idempotency hardening (FR-02, Q-10, Q-61)
Through `build_agent_pipeline` on a file-backed `SqliteRegistry`, a repeat with identical bytes is skipped (INFO). A repeat with different bytes is skipped as a Q-10 anomaly (WARNING, one `anomalies` row, first version kept). Neither sends a model request, writes a case, history, notice, cause or review row, writes a trace line, delivers anything or calls `after_commit`. The run continues.

### R12 · Batch API (Q-62)
Not used for the agent loop. The four reasons are in ADR-0017.

### R13 · Unchanged invariants and imports
- Only `agents/anthropic_model.py` imports `anthropic`. `agents/output.py` and `agents/prefix.py` import no SDK and no `mcp`; they use `mcp_server.types`, `domain` and `telemetry`.
- `metrics` and `cases` never import `agents`, `mcp_server` or `anthropic`, and `evaluation` never imports `cases.novelty`.
- Unchanged:
  - the single writer;
  - the floor;
  - logbooks as data;
  - notices rebuilt through validators (never `model_copy`) and saved once per snapshot.
- The existing import scan covers the new modules.

## Worked examples

**Notation.** IF, `out`, `end`, `tool`, `RAISE5`, `WRONG_RAISE5`, `FRAGMENT_ERROR`, HEAD, `CRIT`, `FakeTools`, `FakeProgress`, `FakeReview`, `s010_rig` as in 007–010. Prices are the Settings defaults: input 0.10, cache write 5m 0.125, cache read 0.01, output 0.50 USD/MTok.
- **GC:** `{"type": "object", "properties": {"case_id": {"type": "string"}}, "required": ["case_id"], "additionalProperties": false}`.
- **OUT:** `{"type": "object", "properties": {"propuestas": {"type": "array", "items": {"type": "string"}}}, "required": ["propuestas"], "additionalProperties": false}`.
- **SYS:** `"ROLE\n\n<criterios>\nC\n</criterios>"`.
- **REQ:** `ModelRequest(SYS, (ToolSpec("get_case", "Return one case with its history.", GC),), (Message("user", (TextBlock("brief"),)),), 16000, "medium")`.
- **NOTE:** `"Code rejected your output. Fix these errors and send the whole JSON again:\n- propuestas[0]: fragment not found in T05"`.
- **Usage:**
  - U1 = `Usage(input_tokens=300, output_tokens=50, cache_write_5m_tokens=2000)`;
  - U2 = `(400, 60, cache_read 2000, cache_write_5m 350)`;
  - U3 = `(120, 40, cache_read 2350)`;
  - U4 = `(300, 50, cache_read 2000)`.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **Sanitizer (R1).** (a) `strict_schema(InvestigatorOutput.model_json_schema())`; (b) the `get_case` input schema as listed by `build_server` (FastMCP, with `title`s); `{"type": "object"}`; `{"type": "array", "items": {"type": "string"}, "minItems": 2}` and the same with `minItems` 1; (c) `{"type": "object", "additionalProperties": {"type": "string"}}`; `{"$ref": "https://x/s.json"}`; `{"type": "object", "properties": {"n": {"$ref": "#/$defs/N"}}, "$defs": {"N": {"type": "object", "properties": {"next": {"$ref": "#/$defs/N"}}}}}`; `{"type": "string", "contentEncoding": "base64"}`; `{"type": "object", "properties": {"m": {"type": "object"}}}`; (d) (b)'s `get_case` schema sanitized twice | (a) Root: `required` `["propuestas"]`, `additionalProperties` false, `properties.propuestas` = `{"type": "array", "items": {"anyOf": [{"$ref": "#/$defs/SetCauseProposal"}, {"$ref": "#/$defs/RaiseProposal"}, {"$ref": "#/$defs/LiftProposal"}]}}`. `$defs` keys = {CauseCategory, CauseState, LiftProposal, Market, Model, RaiseProposal, SetCauseProposal, Stage}. `RaiseProposal`: `required` = [tipo, categoria, etapa, modelo, mercado, bitacora, fragmento, estado_causa], `mercado` = `{"anyOf": [{"$ref": "#/$defs/Market"}, {"type": "null"}]}`, `tipo` = `{"const": "raise", "type": "string"}`, `additionalProperties` false. `CauseCategory.enum` lists every value, `no_declarada` included. No `title`, `default`, `discriminator` or `oneOf` anywhere. `strict_schema(a) == a`, and the input is unchanged. (b) GC; `{"type": "object", "additionalProperties": false}` (root without `properties` allowed); `minItems` dropped / kept. (c) `ValueError("unsupported schema feature: additionalProperties at #")`; `… non-local $ref https://x/s.json at #`; `… recursive $defs N`; `… contentEncoding at #`; `… object without properties at #/properties/m`. (d) Both runs give the same key list, and it keeps the input's order: the input's own keys with `title` removed, then `additionalProperties` (FastMCP lists `type`, `properties`, `required`, `title` → `["type", "properties", "required", "additionalProperties"]`; the test derives the expectation from the input, never a hard-coded FastMCP order); the root of (a) keeps pydantic's order with `title` removed. |
| E2 | **Risk: a 400 from an unsupported feature (R1, R2, R3).** Every tool of `build_server(incident ctx, frames, tools=(*READ_TOOLS, *WRITE_TOOLS))` through `ToolClient.list_tools`, sanitized, plus `investigator_output_schema()` | In every schema: every keyword (outside `properties`/`$defs` name maps) is in the R1 allowlist; every object has `additionalProperties` false and `required == list(properties)`; `minItems` ∈ {0, 1}; every `$ref` resolves to a root `$defs` entry; no cycle; no call raises. For every tool, each property missing from the server's original `required` is nullable (its sanitized schema is an `anyOf` containing `{"type": "null"}`). Today that is exactly `raise_severity.mercado`. |
| E3 | **Coordinator request shape (R6, R3).** `to_params(REQ, "claude-haiku-5-5")` | Exactly `{"model": "claude-haiku-5-5", "max_tokens": 16000, "system": [{"type": "text", "text": SYS, "cache_control": {"type": "ephemeral"}}], "tools": [{"name": "get_case", "description": "Return one case with its history.", "input_schema": GC, "strict": true}], "messages": [{"role": "user", "content": [{"type": "text", "text": "brief"}]}], "thinking": {"type": "adaptive", "display": "summarized"}, "output_config": {"effort": "medium"}, "tool_choice": {"type": "auto"}, "cache_control": {"type": "ephemeral"}}`. |
| E4 | **Investigator shape and count params (R6, R7).** (a) `to_params(replace(REQ, output_schema=OUT), …)`; (b) `_count_params` of REQ and of (a); (c) through the mock transport: one `create` and one `count_tokens` of (a) | (a) As E3, but `output_config` = `{"effort": "medium", "format": {"type": "json_schema", "schema": OUT}}`. (b) Both: keys {model, system, tools, messages, thinking, tool_choice}; `system` = `[{"type": "text", "text": SYS}]`; tools keep `"strict": true`. (c) The create body has `cache_control` at the top level and in `system[0]`, `tools[0].strict` true, and `output_config.format.schema` == OUT. The count body's raw text holds no `cache_control` and no `output_config`. |
| E5 | **The loop sends what the agent owns (R2, R3, R8).** (a) `build_investigator(settings, FakeModel([out()]), FakeTools(…, offered=INVESTIGATOR_TOOLS).opener())`, run with `NothingRequired()`; (b) `build_coordinator(…, hooks=HookChain())` over `FakeTools` with `COORDINATOR_TOOLS`, `[end("Listo.")]` | (a) `requests[0].output_schema == investigator_output_schema()`; each of the 4 tools has `input_schema` `{"type": "object", "additionalProperties": false}`, names in allowlist order. (b) `output_schema` None; same sanitized schemas. In both, `log.model_calls[0].prefix_hash == prefix_hash(requests[0].system, requests[0].tools, requests[0].output_schema)`. |
| E6 | **Validated output with retry (R4, R5).** `s010_rig` (IF to S009, T05 pending): (a) `[out(RAISE5)]`; (b) `[out(WRONG_RAISE5), out(RAISE5)]`; (c) `[out(WRONG_RAISE5)] × 2`; (d) (c)'s first reply only, `INVESTIGATOR_OUTPUT_CORRECTIONS=0`; (e) `[out(WRONG_RAISE5)] × 2 + [out(RAISE5)]`, corrections 2; (f) `[out(WRONG_RAISE5)] × 2`, corrections 2, `INVESTIGATOR_MAX_TURNS=2` | (a) 1 request; `done`; accepted [`S010-p1`]; `rejections` []; no WARNING from `plant_monitor.runner.review_step`. (b) 2 requests; request 2's last message = `Message("user", (TextBlock(NOTE),))`; `done`; accepted [`S010-p1`]; `rejections` [(`propuestas[0]: fragment not found in T05`,)]. (c) 2 requests; `fallback:invalid_output`; accepted `()`; 2 rejections; one WARNING `S010 investigator output invalid after 2 rejected outputs: fallback:invalid_output; causes stay no_declarada`; `record(…, None, "S010")` → {T05: `reintento`}. The trace outcome is covered by 009 E21 (`test_multi_agent_runner.py:368`). (d) 1 request; `fallback:invalid_output`; WARNING `… after 1 rejected outputs: …`. (e) 3 requests; requests 2 and 3 end with NOTE; `done`. (f) 2 requests; `fallback:turn_cap`; accepted `()`; WARNING `S010 investigator output invalid after 2 rejected outputs: fallback:turn_cap; causes stay no_declarada`. |
| E7 | **Note budget in the loop (R4, I1).** `make_coordinator(…, max_notes=n)` with `FakeReview(rejects)`: (a) n 0, rejects 1, `[end("x")]`; (b) n 2, rejects 2, `[end("x"), end("y"), end("z")]`; (c) n 2, rejects 3, the same script | (a) 1 request; `fallback:invalid_output`. (b) 3 requests; requests 2 and 3 end with user text `N1`; `done`. (c) 3 requests; `fallback:invalid_output`; texts [x, y, z]. At the default (n 1), 009 E5, 007 E8 and 010 E2/E3/E12/E22 are unchanged. |
| E8 | **Setting (R4).** (a) `Settings(anthropic_api_key="k")`; (b) env `INVESTIGATOR_OUTPUT_CORRECTIONS=0`; (c) `-1`; (d) `.env.example` | (a) `investigator_output_corrections == 1`. (b) 0. (c) `ValidationError`. (d) Exactly one line `INVESTIGATOR_OUTPUT_CORRECTIONS=1`, in the multi-agent block. |
| E9 | **Prefix bytes (R8).** (a) `prefix_bytes("ROLE", (ToolSpec("get_case", "One case.", {"type": "object", "additionalProperties": false}),), None)`; (b) the same with the schema's keys in the other order; (c) with `output_schema=OUT`; (d) system `"ROLE "`; description `"One case!"`; two tools swapped | (a) `b'{"output_schema":null,"system":"ROLE","tools":[{"description":"One case.","input_schema":{"additionalProperties":false,"type":"object"},"name":"get_case"}]}'`; `prefix_hash` = `hashlib.sha256(a).hexdigest()`, 64 lowercase hex. (b) The same bytes. (c), (d) Each gives a different hash. |
| E10 | **Cache verification with FakeModel (R8, R9, R10).** `make_coordinator(…, criteria_prompt="criteria", prefix_monitor=PrefixMonitor())` over `FakeTools(FakeProgress())`. Run S003, brief `brief A`: `tool(get_deviations, {}, "tu-1")` U1, `tool(get_case, {"case_id": "S001-Sedán-Local"}, "tu-2")` U2, `end("Listo.")` U3. Run S004 on the same loop, brief `brief B`: `end("Listo.")` U4. Then `build_line` for each and `run_totals` | 4 records, all with the same `prefix_hash` H = `prefix_hash(compose_system("SYSTEM", CRIT), <sanitized offered>, None)`: the brief never changes it. No WARNING on `plant_monitor.agents.prefix`. S003 line `totals`: input 820, output 150, `cache_read_tokens` 4350, `cache_write_5m_tokens` 2350, usd `0.00049425`; each `model_calls[i].prefix_hash` H. S004 line: `cache_read_tokens` 2000, usd `0.000075`. `run_totals`: input 1120, output 200, `cache_read_tokens` 6350, `cache_write_5m_tokens` 2350, usd `0.00056925`; `by_agent["coordinator"]`: `cache_read_tokens` 6350, `cache_write_5m_tokens` 2350, `cache_write_1h_tokens` 0. |
| E11 | **Drift (R9).** (a) `m = PrefixMonitor()`: `on_run("coordinator", …)` S003 `H1`, then `on_run("investigator", "S004", "H3")`, then coordinator S004 `H1`, S005 `H2`, S006 `H2`; (b) `on_call("coordinator", "S003", 1, U(read 0, write 2000), "H1")`, `on_call("coordinator", "S003", 2, U(read 0), "H1")`, `on_call("coordinator", "S003", 3, U(read 5), "H1")`; (c) E10's loop, `FakeTools.criteria` changed to `CRIT + "Extra.\n"` before run S004; (c′) instead `FakeTools.suffix = " v2"` (tool descriptions); (d) `make_coordinator` with no monitor, 2 calls with `USAGE` (read 0) | (a) One WARNING: `coordinator prefix changed at S005: H1 -> H2`. The investigator's `H3` never counts as a coordinator change, so one shared instance is correct. (b) One WARNING: `coordinator call 2 at S003 read no cached tokens (prefix H1)`. (c), (c′) One WARNING `coordinator prefix changed at S004: <Ha> -> <Hb>`, Ha the S003 records' hash and Hb the S004 record's (Ha ≠ Hb). (d) No WARNING; records still carry `prefix_hash`. |
| E12 | **Trace (R10).** (a) `build_line` with `ModelCallRecord(1, "end_turn", U3, 100, prefix_hash="ab" * 32)` on the coordinator and the investigator; (b) a 010 line JSON whose model calls lack `prefix_hash` | (a) Both `TraceModelCall`s have `prefix_hash` `"ab" * 32`; the line is equal after `write_now` + `read_trace`. (b) Parses; `prefix_hash` None; `run_totals` cache fields come from the line totals. |
| E13 | **A repeated snapshot changes nothing (R11, FR-02).** File registry, `run_full` wiring (trace, outbox, `Recorder`). Run 1: IF S001–S006 plus an identical-bytes repeat of S004 at `orden` 5 (others shifted); script `[*S002, *S004, *S005, *S006]` (10 replies). Count the rows of every table and the `out/` files. Run 2 on the same file with `FakeModel([])`: run 1's arrivals plus S005 rewritten with other bytes (same payload, `indent=2`, file `S005-bis.json`) at `orden` 8 | Run 1: 10 requests; processed S001–S006; skipped (S004,); INFO `S004 skipped: already processed`. Run 2: no `RunAborted`, 0 requests, processed `()`, skipped all 8 arrivals. One anomaly `repeated_with_different_content` for S005, with the WARNING `S005 repeated with different content (hash <h2>); first processed version (hash <h1>) kept`. After run 2, `processed_snapshots`, `known_units`, `released_units`, `cases`, `case_history`, `notices`, `active_causes`, `active_cause_links`, `case_causes` and `logbook_reviews` have the same rows as before, and `anomalies` has exactly one more. `processed_snapshots` keeps h1 for S005. `Recorder.calls` []; `out/` byte-identical; run 2's trace file is not created. |
| E14 | **Prefix stable across the series (R2, R8, R9).** `run_ids` over IF S001–S008 with HEAD (production wiring with both monitors) | Every investigator `TraceModelCall` has one `prefix_hash` value Hi and every coordinator one Hc, with Hi ≠ Hc. Hi equals `prefix_hash` of the first investigator request's system, tools and `output_schema`. Every investigator request's `output_schema == investigator_output_schema()`, and every coordinator request's is None. No `prefix changed` WARNING. |
| E15 | **Risk: params the SDK does not know (R6, R7).** No network. Keys of the SDK TypedDicts (`__required_keys__ \| __optional_keys__`): `MessageCreateParamsNonStreaming` (`anthropic.types.message_create_params`), `MessageCountTokensParams`, `ToolParam`, `OutputConfigParam` (`anthropic.types`). Checked on E3's and E4a's params and on both `_count_params` | `set(to_params(...)) ⊆` create keys; `set(_count_params(...)) ⊆` count keys; each tool dict's keys `⊆ ToolParam` keys; `output_config` keys `⊆ OutputConfigParam` keys. |

## Edge cases and assumptions
- **X1** · `FakeModel` does not enforce the schema, so 009/010 tests that script invalid output (010 E20a `close_case`, 009 E21) still reach `check_output`. The real API makes form errors near impossible, and corrections are left for semantic errors (citations, scope, states, `no_declarada`).
- **X2** · Constraints dropped by R1 stay enforced: tool arguments by the server's pydantic validation, the investigator output by `check_output` (`proposal_output_max_chars`, `extra="forbid"`, the discriminated union).
- **X3** · The count excludes the format's injected instructions and the cache markers, so the real prompt may exceed the count by a little. The 95k limit against the 100k hard ceiling leaves the margin (NFR-02).
- **X4** · A miss at the first call of a later snapshot (TTL expired, eviction) is not warned (Q-60), and is visible in the trace's per-call usage. Below the 512-token minimum, nothing is cached and no error comes back. The real prefixes are about 1,500+ tokens (ADR-0016); the test prefixes never reach the API.
- **X5** · The hash covers system, tools and format. Thinking, effort and model are per-agent constants from Settings, unchanged within a run. The monitor compares within one run only; across runs, the trace shows the hash (013).
- **X6** · Changing a prompt, a tool description or the schema invalidates the cache until the first new write (24 h grammar cache, 5 min prompt cache). This is expected, and the first run after such a change logs no drift.
- **X7** · Existing resume coverage replaces the skeleton's T6: 009 E20 (`test_multi_agent_runner.py:273`), 007 E21 (`test_agent_runner.py:272`), 008 E22 (`test_judgment_runner.py:333`), 003 E30 (`test_registry_runner.py:157`, `:172`).

## Acceptance
- [ ] E1–E15 pass, one layer each; CI makes no network call (NFR-07). Every new test cites its spec id (`Risk:` tests too).
- [ ] Specs 003–010 tests pass. Only these expectations change, and no test is deleted:
  - 007 E11 (`test_anthropic_model.py:183-192`): the param key set gains `cache_control`.
  - Setup only, no expectation:
    - `make_coordinator` gains `max_notes`, `output_schema` and `prefix_monitor`;
    - `FakeTools` gains `criteria` (default `CRIT`) and `suffix` (default `""`);
    - `SETTINGS_ENV_NAMES` gains `INVESTIGATOR_OUTPUT_CORRECTIONS`;
    - `multi_agent_builders.run_full` returns the `RunSummary` (it returned None);
    - `s010_rig` gains optional `corrections` and `max_turns`;
    - the `EndReview.exhausted` and `ProposalReview` docstrings describe the note budget (`max_notes`).
- [ ] Batch API decision recorded (ADR-0017, written by the main session).
- [ ] Docs in this PR: `docs/STRUCTURE.md` (`agents/output.py`, `agents/prefix.py`, changed rows), `docs/agent-capabilities.md` (strict tools, investigator output format, corrections setting, cached prefix), roadmap row 011, `docs/requirements.md` (Q-56–Q-63; Q-44, Q-52 amended: done with this spec).
- [ ] Manual, after merge: the user's paid days 1–7 run shows `cache_read_tokens` > 0 from the second call of each agent's session, and "S034 skipped: already processed" in the log; numbers in the roadmap (T7). T7 must pass before the held-out run starts.
- [ ] `ruff`, `mypy --strict`, `pytest --cov` pass.

## Size
About 27 KB, over the 20 KB budget. The format, strict tools and cache markers meet in one request shape (E3, E4) and one prefix hash (E9–E11). Splitting validation from caching would change `to_params` twice and invalidate the cache between the two specs.
