# 010 · Guardrails and unattended run — Spec

- **Status:** Draft
- **Requirements:** FR-15, FR-30, FR-31, FR-32, FR-33
- **Stories:** US-09, US-11 (first scenario)
- **Week:** W4

## Goal
Make the rules hold even when the model gets them wrong: hooks before and after each tool and on stop, per-agent allowlists enforced in code, and the criteria served as an MCP prompt. The series then advances and closes shifts with no one touching it.

## Scope
- In: hook chain; allowlist, floor and novelty hooks; on-stop report-completeness hook; criteria as MCP prompt; unattended shift closing; a recorded hook block for the demo.
- Out: structured-output validation (spec 011); the one-command CLI (spec 012).

## Behavior
- Hooks run before each tool, after each tool and on stop. A block returns its reason to the model as a tool error (FR-31).
- **Allowlist:** a tool outside the agent's list is rejected in code before reaching the MCP server (FR-32, US-09).
- **Floor:** a notice with severity below the computed minimum is blocked with "below minimum severity (<level>)" (FR-15, FR-31b).
- **Novelty:** a notice repeating a case with no change since its last report is blocked with "no news since last report" (FR-31a). Expected news comes from `cases/novelty.py` (spec 004).
- **Completeness:** a shift report missing an active case is blocked on stop, naming the missing case (FR-31c).
- The criteria reach the agent as an MCP prompt served by our server (FR-30).
- The series advances and closing snapshots fire reports without manual steps (FR-33).

## Worked examples
To be written when the spec moves to Ready. Seeds: the four US-09 scenarios.

## Edge cases and assumptions
- Hooks reuse the code's decisions (lifecycle, novelty); they never recompute rules differently.

## Acceptance
- [ ] Every rule above has a passing test.
- [ ] One real hook block is captured in the trace for the demo (week-4 deliverable).
- [ ] `ruff`, `mypy --strict` and `pytest` pass; diagrams and `docs/STRUCTURE.md` updated.
