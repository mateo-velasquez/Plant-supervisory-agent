# 016 · Early warning (stretch) — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Forecast tests on synthetic series with known slope and crossing time → `forecast/model.py`.
- [ ] T2 · Crossing-time estimate and anticipatory notice tests; the official severity is unchanged → `forecast/warning.py`.
- [ ] T3 · Backtest over days 1–7 metrics: lead time and false warnings (on demand).
- [ ] T4 · ADR for the model choice, based on the backtest.
- [ ] T5 · Wire it into the pipeline behind a setting (off by default); docs; set status to Implemented.
