# 014 · Visual shift reports (stretch) — Spec

- **Status:** Draft
- **Requirements:** FR-26
- **Stories:** US-05
- **Week:** Stretch · **Priority:** Could (only if everything else is green)

## Goal
Render each shift report and alert as a readable HTML page, from the validated JSON the system already produces, so the plant manager reads signal at a glance.

## Scope
- In: an HTML notifier adapter; a page per shift; a run index linking shifts and alerts.
- Out: any change to what the reports contain (spec 004).

## Behavior
- HTML is rendered only from the validated report JSON; it adds no data (FR-26).
- Each page shows the news first, then the active-cases table, with severity colors and each cause's citation.
- The adapter plugs into the notifier port; the console and file channels keep working.

## Worked examples
To be written when the spec moves to Ready.

## Edge cases and assumptions
- Dependency choice (standard-library templates or Jinja2) decided when Ready; prefer no new dependency.

## Acceptance
- [ ] Rendering tests on synthetic reports pass.
- [ ] The full real run produces a browsable report set.
