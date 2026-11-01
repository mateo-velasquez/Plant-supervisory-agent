# 015 · Analytics dashboard (stretch) — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Decide the medium (static HTML with charts vs small app) and record it in `plan.md`.
- [ ] T2 · Query tests: eval metrics per run, noise per report, cost and cache reads per snapshot, alerts per day → `analytics/queries.py`.
- [ ] T3 · Render the dashboard from the queries → `analytics/render.py`, with a smoke test.
- [ ] T4 · CLI entry to build the dashboard for a run.
- [ ] T5 · Render the full real run; README link; set status to Implemented.
