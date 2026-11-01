# 003 · Case registry and lifecycle — Spec

- **Status:** Draft
- **Requirements:** FR-12, FR-13, FR-14, FR-15, FR-23 (max severity), NFR-04, NFR-10
- **Stories:** US-03
- **Week:** W1

## Goal
Keep, outside the model, one case per deviation with its state, severities and history, and apply the threshold-driven lifecycle of `criterio.md` §3 in code before any agent runs.

## Scope
- In: case states and transitions; effective severity and the floor; max severity since the last report; history per snapshot; SQLite repository (cases, history, processed snapshots with hash, released units); atomic writes per snapshot.
- Out: agent raises and causes (spec 008, which feeds a "raise in force" flag into this lifecycle); which cases are news (spec 004).

## Behavior
- A case opens when a combination without an active case has a deviation (FR-12, §3). At most one active case per combination.
- State is `abierto` in the opening snapshot and `en_seguimiento` from the next one (§3).
- **Effective severity** = max(minimum severity, agent raise in force). It is never below the minimum (FR-15, §2).
- The case becomes `escalado` when the effective severity reaches `critica`, and stays `escalado` even if severity drops (§3). A case that opens already critical opens and escalates in the same snapshot (Q-08).
- The case is `resuelto` after `resolucion.snapshots_sin_desvio` (2) consecutive snapshots without deviation and with no raise in force (§3). A later deviation opens a new case with a new ID.
- Each case keeps: state, current severity, max severity since the last report, last reported state and severity, the clean-snapshot streak and one history row per snapshot (FR-14, FR-23).
- Released unit IDs are persisted so actual progress counts distinct units across snapshots and runs (FR-05).
- All writes for one snapshot and its "processed" mark commit in one transaction (ADR-0003, NFR-10).

## Worked examples
To be written when the spec moves to Ready. Seeds: the seven US-03 scenarios, Q-08 (opens critical), a streak broken by a deviation, and a raise in force blocking resolution.

## Edge cases and assumptions
- **Q-08:** opening and escalating in the same snapshot.
- **Q-15:** a case cannot open and resolve within one shift, so no special handling is needed.

## Acceptance
- [ ] Every rule above has a passing test.
- [ ] The state-machine diagram matches the implementation.
- [ ] `ruff`, `mypy --strict` and `pytest` pass; `docs/STRUCTURE.md` updated.
