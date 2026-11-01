# 015 · Analytics dashboard (stretch) — Spec

- **Status:** Draft
- **Requirements:** FR-37, FR-39
- **Stories:** —
- **Week:** Stretch · **Priority:** Later (after Demo Day)

## Goal
Show, for a run or across runs, how well the system did and what it cost: alert and news accuracy, noise, cause accuracy, tokens, cache reads and USD per snapshot.

## Scope
- In: queries over the SQLite registry, usage and eval results; one dashboard view.
- Out: new metrics (they come from specs 005, 007 and 011).

## Behavior
- Reads only stored data: registry, usage table, eval summaries.
- Shows per run: eval metrics (spec 005), noise, cost and cache reads over the series, and alerts per day.

## Worked examples
To be written when the spec moves to Ready.

## Edge cases and assumptions
- Medium to decide when Ready (static HTML with charts vs a small app); prefer static HTML.

## Acceptance
- [ ] Query functions have passing tests on a synthetic registry.
- [ ] The dashboard renders the full real run.
