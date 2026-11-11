# Agent capabilities (FR-28)

Spec 009, [ADR-0009](adr/0009-pipeline-read-only-investigator-single-writer.md). One pass per snapshot, driven by code: investigator → control → coordinator → one save. Spec 009 defines these lists; spec 010 enforces them in code.

| Agent | Kind | Raw logbooks | Tools (in order) | Input | Output | Writes |
|---|---|---|---|---|---|---|
| Investigator | LLM, read-only | yes | `list_available_logbooks`, `get_logbook`, `get_case`, `get_delayed_units` | task: unreviewed readable logbooks, cases without a cited cause evaluated at the snapshot, active causes | `{"propuestas": [...]}`: `set_cause`, `raise` or `lift`, each with category, stage, scope, `bitacora`, `fragmento` and `estado_causa`; no numbers | nothing |
| Control | code | — | `LogbookStore.verify_citation` | investigator output + task | accepted proposals (ids `<snapshot>-p<n>`) or errors, one correction round | nothing |
| Perspectives | code | no | — | metrics, case history, units | `perspectivas` (gap, shipment, bottleneck) for the cases of the required notices | nothing |
| Coordinator | LLM, single writer | never | `get_deviations`, `get_active_cases`, `get_case`, `get_delayed_units`, `apply_proposal`, `emit_alert`, `emit_shift_report` | brief v3: required notices, perspectives, validated proposals as data, active causes | applied proposals, notice texts | only through `SnapshotJudgment` |
| Runner | code | — | — | — | lifecycle, review marks, one save per snapshot | unit of work |

## Structural defenses
- The reader cannot write and the writer never reads a raw logbook (quarantine).
- Logbooks travel in delimited `<bitacora>` blocks; proposals reach the coordinator delimited as data.
- `apply_proposal` takes only a validated id; code fills category, stage, scope and citation, re-verifies the citation and calls the ledger.
- The severity floor only rises; no tool closes a case.
- `set_cause`, `raise_severity` and `lift_severity_raise` stay registered but no agent is offered them; spec 010's allowlist excludes them.
- Injection tests (US-08, FR-20) belong to spec 010.
