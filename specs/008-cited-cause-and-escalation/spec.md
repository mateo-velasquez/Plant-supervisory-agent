# 008 · Cited cause and logbook escalation — Spec

- **Status:** Draft
- **Requirements:** FR-15, FR-16, FR-17, FR-18, FR-19
- **Stories:** US-06, US-07
- **Week:** W2

## Goal
Let the coordinator attach a cause to each case, quoted verbatim from a logbook, and raise a case to critical when a logbook says its cause is ongoing with no resolution date. Code validates every citation and keeps the raise in force until a later logbook reports the resolution.

## Scope
- In: cause catalog; `set_cause`, `raise_severity` and `lift_severity_raise` write tools; the active-cause (raise) entity and its scope; propagation to the lifecycle (spec 003) and notices (spec 004); prompt v2; goldens for the three known incidents.
- Out: analysts (spec 009); hooks (spec 010).

## Behavior
- A cause has a `categoria` from the catalog (`parada_de_linea`, `faltante_de_piezas`, `retrabajo`, `retencion_de_calidad`, `ausentismo`, `no_declarada`) and an `etapa` (FR-16, §6).
- Every cause except `no_declarada` cites `{bitacora, fragmento}`, verified verbatim; a failed check is a tool error (FR-17, Q-12).
- With no logbook naming the cause, it is `no_declarada`, the stage is the bottleneck, and evidence is empty (FR-18, §6).
- `raise_severity` needs a citation saying the cause is ongoing with no resolution date. It records an **active cause** with its scope (model and stage, Q-02) and raises every active case in that scope to `critica`, with `origen=agente` and `motivo=bitacora` (FR-19, §5).
- Cases that open while an active cause is in force are raised too (§5).
- `lift_severity_raise` needs a citation from a later logbook reporting the resolution. From that snapshot the minimum severity applies again and resolution is no longer blocked (Q-11, §5).
- A concrete resolution date or an already resolved problem does not raise severity. This is model judgment, guided by the prompt and measured by evals.

## Worked examples
To be written when the spec moves to Ready. Seeds from days 1–7 (verified quotes in `docs/roadmap.md`):
- T02 Sedán assembly stop that resumed the same shift: cause cited, no raise.
- T07 → T10 Europe audit: `retencion_de_calidad` in `calidad`; the escalation comes from the threshold (EUR-0305 missed, 7 days).
- T17 → T19 Pickup assembly stop with no date: raise at T17 for every Pickup case in `montaje`, lifted at T19.

## Edge cases and assumptions
- **Q-02:** the scope is model + stage.
- **Q-11:** a dedicated lift tool.
- **Q-12:** the citation is checked inside each write tool.

## Acceptance
- [ ] Every code rule above has a passing test.
- [ ] Evals on the three incidents pass for category, stage, citation and escalation timing.
- [ ] `ruff`, `mypy --strict` and `pytest` pass; `docs/STRUCTURE.md` and the components diagram updated.
