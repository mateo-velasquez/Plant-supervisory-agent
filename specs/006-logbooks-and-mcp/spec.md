# 006 · Logbook store and MCP server — Spec

- **Status:** Draft
- **Requirements:** FR-17 (verification), FR-20 (delimiting), FR-27, NFR-03
- **Stories:** US-06 (verbatim check), US-08 (delimited logbooks)
- **Week:** W1–W2

## Goal
Give the agents one door to the data: our own MCP server, exposing compact read-only views over metrics, cases and logbooks. Logbooks become available only when their shift closes, and every citation can be checked verbatim.

## Scope
- In: logbook store (loading, availability, verbatim check, delimiting); MCP server skeleton; read tools; tool output size budget; settle the transport (ADR-0007 follow-up).
- Out: write tools (`emit_alert` and `emit_shift_report` in spec 007; `set_cause`, `raise_severity` and `lift_severity_raise` in spec 008); the criteria prompt (spec 010).

## Behavior
- A logbook `Txx` becomes available at its shift's closing snapshot. A mid snapshot sees only earlier shifts (Q-01). Requesting a shift not yet closed returns a tool error.
- **Verbatim check:** a fragment is valid only if it appears in the cited logbook, compared after normalizing whitespace and line breaks (Q-12). It is used by every write tool that carries evidence.
- A logbook returned by a tool is wrapped as quoted data with its ID and never mixed with instructions (FR-20, US-08).
- **Read tools:** `get_deviations(snapshot_id)`, `get_active_cases()`, `get_case(case_id)` (history plus last reported state and severity), `list_available_logbooks()`, `get_logbook(turno_id)`, `get_delayed_units(modelo, mercado)`.
- Tools return compact, filtered views, never full datasets (FR-27, NFR-03), and each view stays under a size budget from settings.

## Worked examples
To be written when the spec moves to Ready. Seeds: the S001–S005 availability timeline from `z_helps/flujo_de_carga.md` §5, the US-06 rejection "fragment not found in T07", and a real T07 fragment that passes.

## Edge cases and assumptions
- **Q-01:** availability at shift close.
- **Q-12:** citation checked inside the write tools, through this store.
- ADR-0007: stdio transport in real runs and in-process in tests, pending confirmation here.

## Acceptance
- [ ] Every rule above has a passing test, using an in-process MCP client.
- [ ] ADR-0007 updated with the transport decision (Accepted or revised).
- [ ] `ruff`, `mypy --strict` and `pytest` pass; `docs/STRUCTURE.md` updated.
