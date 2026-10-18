---
name: new-adr
description: Create the next Architecture Decision Record from the template and add it to the ADR index. Use whenever a significant design decision is made or an earlier one changes.
argument-hint: "[decision title]"
---

Record the decision: $ARGUMENTS

1. List `docs/adr/NNNN-*.md`, take the highest number + 1 (4 digits).
2. Create `docs/adr/NNNN-<kebab-title>.md` from `docs/adr/template.md`: today's date, `Status: Accepted` (or `Proposed` if the user has not decided), and the related FR/NFR IDs.
3. Fill Context, Decision, Alternatives considered and Consequences from the conversation; ask the user for anything you cannot justify. Keep it under one page.
4. If it supersedes an ADR, set the old one to `Superseded by NNNN` and link both ways.
5. Add a row to the table in `docs/adr/README.md`.
6. If the README's "How it works" section or `docs/STRUCTURE.md` is affected, update them in the same change.
