# 0023 · Early warning as a code-only gap forecast shown in the dashboard

- **Status:** Accepted
- **Date:** 2026-11-21
- **Requirements:** FR-41, FR-40, NFR-04, NFR-07 (spec 016, Q-119–Q-136)

## Context
FR-41 (a stretch item in the brief) asks to project the trend and warn before a threshold is crossed, with an estimated time. Several constraints shape how:
- `criterio.md` defines only two notices (`alerta_inmediata`, the shift report), and §4 treats repeating what was already said as noise. Nothing in it lets a forecast change a severity, a case or the news.
- ADR-0002: code computes, the model judges. A projection is a number, like the gap.
- The brief lets notices reach people through any channel, a dashboard ("tablero") included, as long as each one stores its snapshot, reason and evidence.
- The dashboard only shows what the run stored and never computes a plant metric (ADR-0021).
- The gap % is taken against the current shift's plan × 3 (Q-06), and it is `None` when that plan is 0 (Q-16). A straight line over the gap % or over gap units goes wrong whenever the plan changes between shifts. The plan itself is static plant data known in advance; it is not a future observation.
- Only combinations with a case have a stored gap history (`case_history`). Combinations with no case, where an early warning helps most, have none.
- The held-out run happens once, so a forecast must never stop it or change what the agents see.

## Decision
- **Code only, never a decision.** The forecast is computed by deterministic code. It is never a notice, a severity, a case event, news, an outbox row, an evaluator input or part of an agent brief. The `tendencia` extension point of spec 009 (ADR-0009 follow-up) is dropped.
- **Model.** At snapshot N, for each combination with a full window of W processed snapshots: rate = released units per snapshot over the window. The projected gap at N+h is the current progress plus rate × h, minus the known cumulative plan at N+h, for h ≤ H. The warning names the first projected snapshot that reaches the next gap level under the `gap_severity` rule, with its scheduled time. W = 12 and H = 3 are settings (`early_warning_window_snapshots`, `early_warning_horizon_snapshots`). They are not client rules, so they do not go in `umbrales.yaml`. No warning is issued when the effective severity already reaches the target level.
- **Storage.** Registry schema v5 adds a `gap_forecasts` table: one row per combination per snapshot, holding the gap, thresholds in units, projected points, the warning and its basis (including W and H). The single writer saves it in `finish`, inside the snapshot's unit (ADR-0003), and a repeated snapshot writes nothing. `ForecastRow` is a persisted JSON contract, so any field added later needs a default.
- **Failure policy.** Forecast rows are computed and saved inside a savepoint. If that fails, the code logs a WARNING, writes no row and the snapshot still commits. A forecast bug never stalls the monitor.
- **Held-out policy.** While the guard is closed, the forecast treats the calendar as ending before `heldout_first_shift`, so no refused id is ever written. The dashboard omits whole rows, as in 014.
- **Channel.** The dashboard gets a fourth window, **Pronóstico** (`/pronostico`, `/api/forecast`), plus a ⚠ marker on Planta cells. The window shows active warnings, a model × market grid with gap, projection and thresholds, and an **Anticipación** panel. Anticipación groups consecutive warnings into episodes and scores them in the viewer from stored rows only. That differs from ADR-0022's "accuracy is read, never computed", because the scoring needs no golden set and no plant metric. A v4 registry reads as "no forecasts".

## Alternatives considered
- **A new `aviso_temprano` notice in the outbox, or a section in the shift report:** a contract that `criterio.md` does not define. It would touch `Notice`, the 011 schemas, the evaluator and the noise metric, and it risks the repeated-notice noise the brief penalizes.
- **`tendencia` in the coordinator brief:** the model needs it for nothing it decides. It would change the held-out run's input, and severity words in the text can trip the 010 text hook.
- **A straight line (least squares) over the gap, or Holt:** wrong when the plan changes between shifts or a shift has plan 0. With about 42 points per combination in days 1–7, a richer model has no data to justify it.
- **Compute the forecast in the dashboard:** it breaks the 014 rule, and the dashboard has no plant context.
- **Hide held-out ids at display time:** the hidden warnings corrupt the Anticipación scoring at the end of day 7.
- **A separate backtest command:** Anticipación in the dashboard measures the same thing, during any replay, including the held-out run.

## Consequences
- Positive:
  - Every warning can be traced: its snapshot, basis and numbers are stored, and the replay shows it as of N.
  - Combinations with no case get a gap history and a warning before a case opens.
  - Severity, cases, notices, the evaluator and agent cost do not change.
- Negative / risks:
  - Schema v5: tests that pin version 4 change their expectation, and v4 files cannot gain forecasts read-only.
  - The first W snapshots of a series have no forecast (two days with W = 12).
  - Rows near the held-out boundary depend on the guard state when they were written.
  - A forecast failure is silent apart from a WARNING, so a missing row reads as "no warning".
  - Suppression uses the raise of an existing case only: a combination under an active cause in force but with no case yet can get a gap warning, though its case would open at `critica` (§5, Q-134).
- Follow-ups:
  - Spec 016 implements it.
  - Real-run review of lead time and false warnings with the user's permission (016 T12).
  - ADR-0009's `tendencia` follow-up is superseded by this ADR.
