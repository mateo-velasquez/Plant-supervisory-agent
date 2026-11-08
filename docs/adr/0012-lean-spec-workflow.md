# 0012 · Lean spec workflow: anchored reading, spec size budget, delta re-review and test budget

- **Status:** Accepted
- **Date:** 2026-11-08
- **Requirements:** NFR-07, NFR-08

## Context
The ADR-0006 workflow works, but it burns tokens and keeps adding tests:
- **Specs have grown about 5×.** Spec 001 (the depth reference) is ~14 KB for spec plus plan; 004 is ~90 KB and 005 ~76 KB.
- **Every subagent starts cold.** `/implement-spec` spawns a `test-writer` and a `domain-implementer` per task group, and each read spec, plan and tasks whole. That is ~30–35k tokens before any code is read, and in 005 about a dozen spawns.
- **Re-review repeats work.** Each `reviewer` round (Opus) re-read the whole branch and re-ran every check.
- **Tests outgrow the code.** The 005 branch added ~2,300 test lines for ~1,200 source lines, and coverage reached 98.7%. The user's target is ~85% (80% is the CI minimum), and the prose rule "no speculative extras" was not enough.

## Decision
Agents read only what their task cites, specs have a flexible size budget, re-reviews check only the fix, and every test traces to a spec ID.
- **Anchors and anchored reading.** New specs give each rule an `Rn ·` heading, each example an `En` table row and each edge case an `Xn` item. Each plan interface gets a heading, and each task in `tasks.md` ends with `refs: … · plan: …`. `test-writer` and `domain-implementer` Grep for those anchors and read only those sections. As a mitigation, they always also read "Edge cases" and "Acceptance" and the rules their examples cite. The `reviewer` still reads the spec whole, plus earlier specs that touch the same modules.
- **Spec size budget (flexible).** About 20 KB for `spec.md` and 12 KB for `plan.md`. One example per rule, with variants only for boundaries. The plan holds signatures and design, not code. A spec over budget is split or carries a `## Size` justification, and `/new-spec` measures it.
- **Delta re-review.** After the first full review, re-reviews receive the previous findings and the files the fix changed, and check only those. `/check` on the whole repo at the close still catches regressions elsewhere.
- **Test budget.**
  - Every test names a spec ID; variants share one parametrized test.
  - At most 2 `Risk:` extras per task group.
  - No tests for declared types, enums, trivial properties or private helpers.
  - One layer per rule.
  - If a new module goes above ~90%, `/implement-spec` sends `test-writer` back to remove its untraced extras.
  - Existing tests are never deleted.
- **Short reports.** Subagent reports are capped at about 15 lines.

## Alternatives considered
- **Signature-only plans and larger task groups:** fewer tokens per spawn. But Haiku gets less guidance and more context, which can move the cost into extra Opus review rounds. Deferred until measured on a real spec.
- **A fixed test-to-code ratio or a coverage ceiling:** easy to check, but arbitrary. It would push toward deleting useful tests or skipping real edge cases.
- **Leave the specs as they are and rely on `/clear`:** helps the main session only. Subagents start cold either way.

## Consequences
- Positive: far less repeated context per spawn, cheaper re-reviews, and new tests stay traceable to the spec.
- Negative / risks:
  - An agent may miss a cross-cutting rule outside its anchors; the full-spec reviewer is the safety net.
  - Tighter specs may bring back ambiguity, so a Haiku implementer could guess more.
  - Specs 001–005 have no anchors and keep section-level reading.
- Follow-ups:
  - Measure token use and test-to-code lines on the first spec written under these rules (006), then decide on the deferred alternatives.
  - Coverage stays near today's level, since existing tests are kept.
