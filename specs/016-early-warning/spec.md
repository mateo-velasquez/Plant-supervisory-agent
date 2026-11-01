# 016 · Early warning (stretch) — Spec

- **Status:** Draft
- **Requirements:** FR-41
- **Stories:** —
- **Week:** Stretch · **Priority:** Later (after Demo Day)

## Goal
Project each combination's gap trend and warn before a threshold is crossed, with an estimated time, as a separate forecast that never changes the official severity.

## Scope
- In: a forecasting model over the stored metric history; a separate anticipatory notice; a backtest on days 1–7.
- Out: any change to minimum severity, the case lifecycle or official alerts (ADR-0002).

## Behavior
- The forecast uses only past metrics of the series (no future data) and estimates when the gap will cross the next severity threshold (FR-41).
- An anticipatory notice is a different type from `alerta_inmediata`, clearly marked as a forecast, with its estimated time and confidence.
- It never raises or lowers the computed severity.

## Worked examples
To be written when the spec moves to Ready.

## Edge cases and assumptions
- Model choice (linear trend, Holt, or another) decided in an ADR after a backtest; with about 42 points per combination in days 1–7, simple models are preferred.
- The backtest uses days 1–7 only; days 8–10 are not used for tuning.

## Acceptance
- [ ] The forecast has passing tests on synthetic series with a known crossing time.
- [ ] A backtest on days 1–7 reports lead time and false warnings.
