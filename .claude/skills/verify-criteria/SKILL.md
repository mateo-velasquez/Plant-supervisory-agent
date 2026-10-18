---
name: verify-criteria
description: Cross-check a module or spec against the domain criteria (criterio.md, umbrales.yaml) and list rules that are missing, misimplemented or untested. Use after implementing domain logic or when a rule is in doubt.
argument-hint: "[module path or spec folder]"
context: fork
agent: reviewer
background: false
---

Verify domain fidelity of: $ARGUMENTS

1. Read `data/reglas/criterio.md`, `data/reglas/umbrales.yaml` and the open questions in `docs/requirements.md` §5.
2. Build a checklist of every rule in the sections relevant to the target (§1 metrics, §2 severity, §3 lifecycle, §4 notices, §5 escalation, §6 cause).
3. For each rule, locate the implementing code and the test(s) that cover it (search `src/` and `tests/`).
4. Report a table with these columns: rule (§n, short quote) | implemented at (file:line or "missing") | tested by (test name or "none") | verdict (ok / missing / mismatch / untested), with notes on boundaries (`>` vs `≥`), exclusions and tie-breaks.
5. Flag any implemented behavior that is **not** in the criteria and not covered by an open question.

Do not modify files. Never read days 8–10 (T22–T30, S043–S060).
