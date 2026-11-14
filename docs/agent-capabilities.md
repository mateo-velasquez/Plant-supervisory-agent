# Agent capabilities (FR-28)

Specs 009, 010 and 011, [ADR-0009](adr/0009-pipeline-read-only-investigator-single-writer.md), [ADR-0016](adr/0016-guardrail-hook-chain-code-allowlists-criteria-prompt.md), [ADR-0017](adr/0017-structured-output-cached-prefix-batch-rejected.md). One pass per snapshot, driven by code: investigator → control → coordinator → one save. Spec 009 defines these lists; spec 010 enforces them in code.

| Agent | Kind | Raw logbooks | Tools (in order) | Hooks (010) | Input | Output | Writes |
|---|---|---|---|---|---|---|---|
| Investigator | LLM, read-only | yes | `list_available_logbooks`, `get_logbook`, `get_case`, `get_delayed_units` | allowlist | system: role + `<criterios>`; task: unreviewed readable logbooks, cases without a cited cause evaluated at the snapshot, active causes | `{"propuestas": [...]}`: `set_cause`, `raise` or `lift`, each with category, stage, scope, `bitacora`, `fragmento` and `estado_causa`; no numbers | nothing |
| Control | code | — | `LogbookStore.verify_citation` | — | investigator output + task | accepted proposals (ids `<snapshot>-p<n>`) or errors, one correction round | nothing |
| Perspectives | code | no | — | — | metrics, case history, units | `perspectivas` (gap, shipment, bottleneck) for the cases of the required notices | nothing |
| Coordinator | LLM, single writer | never | `get_deviations`, `get_active_cases`, `get_case`, `get_delayed_units`, `apply_proposal`, `emit_alert`, `emit_shift_report` | pre: allowlist, novelty, text floor, cause; post: floor check; stop: completeness | system: role + `<criterios>`; brief v3: required notices, perspectives, validated proposals as data, active causes | applied proposals, notice texts | only through `SnapshotJudgment` |
| Runner | code | — | — | — | — | lifecycle, review marks, one save per snapshot | unit of work |

## Allowlists in code (010)
The lists live in one place, `agents/allowlists.py`, built from the tool-name constants in `mcp_server/types.py`. Three barriers keep them honest:
1. A test checks each list, and that no list offers an excluded tool (`set_cause`, `raise_severity`, `lift_severity_raise`).
2. The allowlist hook runs first in every agent's chain and blocks any other tool with `tool <name> is not allowed for the <agent>`. The block returns to the model as a tool error and is recorded in the trace's `hooks`.
3. `build_agent_pipeline` calls `check_allowlists` before building anything, and refuses to start (`ValueError`) if a list offers an excluded tool.

## Hooks (010)
- **Pre-tool** hooks may block a call. The reason returns as a tool error, and the call never reaches the MCP server.
- **Post-tool** hooks only verify. A violation, such as a notice below its floor after `apply_proposal`, is a code bug that aborts the snapshot, which can be resumed.
- **On-stop** hooks wrap the end of turn. A block returns as a note: for the coordinator, the notices still missing a text.
- Hooks reuse the code's decision for the snapshot (alerts, news, floors). They never recompute a rule.

## Structured output and cached prefix (011)
- Every offered tool goes out with `strict: true` and a schema sanitized to the API's strict subset (`agents/output.py`), for both agents.
- The investigator's request also carries `output_config.format` with the `InvestigatorOutput` schema. `check_output` still runs as the second barrier (size, scope, states, citations, `no_declarada`).
- The investigator gets `INVESTIGATOR_OUTPUT_CORRECTIONS` correction notes (default 1). When they run out, the outcome is `fallback:invalid_output` (or `fallback:turn_cap`), with a WARNING; causes stay `no_declarada` and the logbook is retried under Q-52.
- Each agent's prefix (tools + system + output schema) is byte-stable and cached: one 5-minute breakpoint on the system block plus automatic caching for the snapshot's conversation tail. `PrefixMonitor` logs a changed `prefix_hash` between snapshots or a zero cache read from a session's second call on.
- The coordinator gets no new review; its texts still go through the tool schemas, the hooks and the draft validators.

## Structural defenses
- The reader cannot write, and the writer never reads a raw logbook (quarantine).
- Logbooks travel in delimited `<bitacora>` blocks. Proposals reach the coordinator delimited as data.
- `apply_proposal` takes only a validated id. Code fills category, stage, scope and citation, re-verifies the citation and calls the ledger.
- The severity floor only rises, and no tool closes a case.
- A text may not state a severity below its notice's, nor name a cause other than the notice's `causa` (Q-55).
- Injection tests (US-08, FR-20): `tests/integration/test_guardrails_runner.py` (010 E20, E21).
