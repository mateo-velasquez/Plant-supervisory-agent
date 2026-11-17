# 0020 · Agent prompts in Spanish

- **Status:** Accepted
- **Date:** 2026-11-17
- **Requirements:** specs 009 and 010 (investigator and coordinator prompts); amends ADR-0005

## Context
The logbooks, the criteria (`criterio.md`), the brief's field names and the notice texts are all Spanish. The two system prompts (`agents/prompts/coordinator.md`, `agents/prompts/investigator.md`) were in English, because ADR-0005 put code and docs in English, but it never said which language the model's instructions should use. The result was a Spanish-speaking plant, read by an agent instructed in English.

## Decision
The system prompts are written in Spanish: investigator v3 and coordinator v5. Tool names, JSON keys, data-contract values and the `<bitacora>`, `<criterios>` and `<propuestas>` tags stay exactly as code expects them. Code, comments and docs stay in English (ADR-0005).

## Alternatives considered
- **Keep the prompts in English:** models follow English instructions over Spanish data well, but the mix of languages is harder to explain and to audit against `criterio.md`.
- **Translate every model-facing string too (task instruction line, tool descriptions, hook errors):** more consistent, but a larger change with more test churn; left as a follow-up.

## Consequences
- Positive: one language from the logbook to the notice, and the prompts read like the criteria they apply.
- Negative / risks: the agent behavior with the new prompts is only checked with the fake model until the next paid run; Spanish uses slightly more tokens, mostly absorbed by prompt caching.
- Follow-ups: translate the remaining model-facing strings if the paid run shows mixed-language output.
