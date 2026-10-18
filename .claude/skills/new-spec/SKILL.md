---
name: new-spec
description: Scaffold a new feature spec folder (specs/NNN-feature/) from the template, numbered and linked to its requirements and stories. Use when starting a feature that has no spec yet.
argument-hint: "[feature-name] [FR-ids...]"
---

Create the spec for: $ARGUMENTS

1. Find the next number: list `specs/` folders matching `NNN-*` and take the highest + 1 (zero-padded to 3 digits).
2. Create `specs/NNN-<kebab-feature-name>/` with `spec.md`, `plan.md` and `tasks.md` copied from `specs/_template/`, replacing `NNN · Feature name` in each heading.
3. Fill the header of `spec.md`: `Status: Draft`, the requirement IDs given (verify each exists in `docs/requirements.md`), the stories that reference them (search `specs/stories/`), and the week from the traceability table in `docs/requirements.md` §6.
4. Delegate the content to the `spec-writer` subagent, passing the folder path and the requirement IDs.
5. When it returns, show the user the folder, the covered FR/US and any new open questions.
