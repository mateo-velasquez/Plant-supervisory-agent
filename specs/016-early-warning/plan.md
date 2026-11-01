# 016 · Early warning (stretch) — Plan

## Modules

| File | Responsibility |
|---|---|
| `forecast/model.py` | Trend model over a combination's gap history. |
| `forecast/warning.py` | Crossing-time estimate and anticipatory notice. |
| `domain/notices.py` | New notice type for forecasts (outside the official three). |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
Lives in the deterministic core (code), not in the agent; the agent may only mention the forecast in a notice's text.

## Test strategy
Synthetic series with known slopes and crossing times; backtest script over days 1–7 (on demand).

## Risks
False warnings add noise: the backtest measures them before it is enabled.
