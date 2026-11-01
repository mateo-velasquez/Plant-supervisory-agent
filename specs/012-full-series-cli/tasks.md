# 012 · Full-series CLI — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · CLI test: `plant-monitor run` on a synthetic series processes every arrival in order and writes one report per shift → `runner/cli.py`, `[project.scripts]`.
- [ ] T2 · Threshold-only mode test: the run makes no model calls.
- [ ] T3 · Summary test: tokens (input, output, cache read), USD, duration, arrivals, reports and alerts, printed and written under `output_dir` → `runner/summary.py`.
- [ ] T4 · Resume test (US-11): a failure at the third snapshot, then a rerun continues there.
- [ ] T5 · `--until` and `--speed` tests (speed uses an injectable sleep).
- [ ] T6 · Prompt-budget report test: an oversized step is reported in the summary (US-11, third scenario).
- [ ] T7 · Full real run of the 61 arrivals; record cost and time in the README and roadmap.
- [ ] T8 · README "How to run" and `docs/STRUCTURE.md` updated; status set to Implemented.
