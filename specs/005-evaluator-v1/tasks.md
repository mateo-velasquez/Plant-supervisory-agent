# 005 · Evaluator v1 — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · Golden-case models (alerts, news per shift, causes, `justification`, `depends_on`) with loader tests → `evaluation/golden.py`.
- [ ] T2 · Alert scoring test (US-12): hit only with exactly one alert at the expected snapshot; missing and extra counted → `evaluation/scoring.py`.
- [ ] T3 · News scoring test: missing and extra news are both errors.
- [ ] T4 · Cause scoring test: `categoria` and `etapa` match, and the fragment exists verbatim in the cited logbook.
- [ ] T5 · Noise test: news repeated unchanged from the previous report is counted, with no golden data.
- [ ] T6 · Held-out guard test: T22–T30 and S043–S060 are refused unless the held-out setting is on (new `Settings` field, `.env.example`, settings test) → `evaluation/held_out.py`.
- [ ] T7 · **A3:** smoke run of the threshold-only pipeline over real days 1–7; list which cases open, escalate and resolve (on demand, not CI) → `evals/smoke_days_1_7.py`.
- [ ] T8 · **A1 (user + `eval-curator`):** incident catalog for T01–T21 (shift, category, stage, resolution date, distractors, injection attempts) → `evals/golden/incidents.md`.
- [ ] T9 · **A4:** explain the anomalies (12 units in `despacho` after their departure; logbook "Producción" line vs `liberadas`); record findings in the roadmap and add Q-xx if needed.
- [ ] T10 · `eval-curator`: golden cases for day 1 (T01–T03), verified by hand.
- [ ] T11 · `eval-curator`: golden cases for the Europe audit (T07–T10, EUR-0305 missed, `retencion_de_calidad`).
- [ ] T12 · Eval CLI: prints the metrics table, writes a summary under `output_dir`, exits non-zero on errors → `evals/run_eval.py`.
- [ ] T13 · Update `docs/STRUCTURE.md` (`evaluation/` module), README "How to run evals", and set status to Implemented.
