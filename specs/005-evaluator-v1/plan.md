# 005 · Evaluator v1 — Plan

## Modules

| File | Responsibility |
|---|---|
| `evaluation/golden.py` | Pydantic models for golden cases plus a loader. |
| `evaluation/scoring.py` | `score_alerts`, `score_news`, `score_causes`, `count_noise`. |
| `evaluation/held_out.py` | Guard that refuses held-out shifts and snapshots before W5. |
| `evals/golden/` | Golden files per day plus `incidents.md` (catalog from A1). |
| `evals/run_eval.py` | Thin CLI: load the run output and golden files, print and write the metrics. |
| `evals/smoke_days_1_7.py` | On-demand smoke run of the threshold-only pipeline over real days 1–7 (A3). |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- **Adaptation to `docs/STRUCTURE.md`:** the scoring logic lives in `src/plant_monitor/evaluation/`, so it is typed, linted and unit-tested in CI. `evals/` keeps only data and thin scripts. Update `STRUCTURE.md` in this PR.
- Golden files are YAML or JSON (decide when Ready); each item carries `justification` and optional `depends_on: Q-xx`.

## Test strategy
Unit tests for scoring with synthetic outputs. The smoke run and the evals over real data run on demand only, never in CI (NFR-07).

## Risks
Golden cases built from the system's own output would be circular: they are verified by hand against `criterio.md`, with the smoke run as a starting point only.
