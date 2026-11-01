# 005 · Evaluator v1 — Spec

- **Status:** Draft
- **Requirements:** FR-39, FR-40
- **Stories:** US-12
- **Week:** W1 (grows weekly)

## Goal
Measure whether a change improved or broke the system by comparing its output against hand-verified golden cases, plus a noise metric that needs no golden data. Also close the research items A1, A3 and A4 of the roadmap, which produce those golden cases.

## Scope
- In: golden-case format; scoring for alerts, news, causes and noise; the held-out guard; an on-demand smoke run of the threshold-only system over days 1–7; incident catalog; first golden cases; eval CLI.
- Out: model-in-the-loop evaluation runs (they reuse this evaluator from spec 007 on); the analytics dashboard (spec 015).

## Behavior
- **Alerts:** a hit only if exactly one alert for the expected case fired in the expected snapshot; missing and extra alerts both count as errors (FR-39).
- **News:** per shift report, missing news and extra news are both errors.
- **Causes:** `categoria` and `etapa` must match, and the fragment must exist verbatim in the cited logbook.
- **Noise:** news repeated unchanged from the previous report, counted by comparing consecutive reports (no golden data).
- **Held out:** before W5 the evaluator refuses to load T22–T30 and S043–S060 (FR-40).
- Every golden item records its justification (§n plus numbers or quote) and the open question it depends on, if any.

## Worked examples
To be written when the spec moves to Ready. Seeds: the US-12 scenarios, and golden cases for day 1 (T01–T03) and for the Europe audit (T07–T10, EUR-0305).

## Edge cases and assumptions
- Golden items that depend on an open question are scored separately, so a decision change is visible.

## Acceptance
- [ ] Scoring rules have passing tests on synthetic outputs.
- [ ] Golden cases for day 1 and for the T07–T10 incident exist and are verified by hand.
- [ ] The eval CLI prints a metrics table and writes a summary under `output_dir`.
- [ ] `ruff`, `mypy --strict` and `pytest` pass; README explains how to run evals.
