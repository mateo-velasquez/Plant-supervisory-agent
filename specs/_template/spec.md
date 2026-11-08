# NNN · Feature name — Spec

- **Status:** Draft | Ready | Implemented
- **Requirements:** FR-xx, NFR-xx
- **Stories:** US-xx
- **Week:** Wn

<!-- Budget: about 20 KB. Over it, split the feature or add a "## Size" section saying why. -->

## Goal
One paragraph: what problem this feature solves and for whom.

## Scope
- In:
- Out (and where it goes instead):

## Behavior
Each rule is its own heading, traceable to a requirement or a criteria section (§n).

### R1 · Rule title
Rule stated precisely (FR-xx, §n).

## Worked examples
Concrete inputs → expected outputs. Each example becomes one test; variants go in one row.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | … (R1) | … |

## Edge cases and assumptions
Only cases that protect a real risk. Link to open questions (Q-xx) where applicable.

- **X1** · …

## Acceptance
- [ ] Every rule above has a passing test.
- [ ] `ruff`, `mypy --strict` and `pytest` pass.
- [ ] Docs updated (`STRUCTURE.md`, ADR if a decision was made).
