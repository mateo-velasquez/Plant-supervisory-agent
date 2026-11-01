# 014 · Visual shift reports (stretch) — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Decide the template engine (standard library vs Jinja2) and record it in `plan.md`.
- [ ] T2 · Shift-report page test: news first, then active cases, severity classes, citations → `notify/html.py`, templates.
- [ ] T3 · Escaping test: a fragment with `<script>` renders as text.
- [ ] T4 · Alert page and run index linking every shift and alert.
- [ ] T5 · Wire the adapter through the notifier port and a CLI flag; the other channels keep working.
- [ ] T6 · Render the full real run; README screenshot or link; set status to Implemented.
