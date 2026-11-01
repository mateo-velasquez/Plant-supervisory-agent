"""Gap, delay and minimum severity from `umbrales.yaml` (FR-11, §2, Q-04, Q-07, Q-16)."""

from collections.abc import Iterable

from plant_monitor.domain.enums import Market, Severity
from plant_monitor.metrics.thresholds import DelayLevels, GapThresholds, Thresholds

type Levels = Iterable[tuple[Severity, float | None]]


def _highest_reached(value: float, levels: Levels) -> Severity:
    """Highest level whose threshold is `<= value` (inclusive, Q-07); absent levels are skipped."""
    reached = [severity for severity, threshold in levels if threshold is not None and threshold <= value]
    return max(reached, default=Severity.NONE)


def _gap_levels(gap: GapThresholds) -> Levels:
    return ((Severity.MEDIUM, gap.media), (Severity.HIGH, gap.alta), (Severity.CRITICAL, gap.critica))


def _delay_levels(delay: DelayLevels) -> Levels:
    return ((Severity.MEDIUM, delay.media), (Severity.HIGH, delay.alta), (Severity.CRITICAL, delay.critica))


def gap_severity(gap_units: float, gap_pct: float | None, thresholds: Thresholds) -> Severity:
    """None if `gap_pct` is None (Q-16), not behind, or behind fewer than `minimo_unidades`."""
    behind_units = -gap_units
    if gap_pct is None or behind_units <= 0 or behind_units < thresholds.gap.minimo_unidades:
        return Severity.NONE
    return _highest_reached(-gap_pct, _gap_levels(thresholds.gap))


def delay_severity(
    market: Market, delay_days: float | None, beyond_horizon: bool, thresholds: Thresholds
) -> Severity:
    """Per-market delay level; `critica` beyond the horizon (Q-04); `delay_days` is None iff beyond it."""
    if beyond_horizon:
        if delay_days is not None:
            raise ValueError(f"delay_days is {delay_days} but delay_beyond_horizon is True")
        return Severity.CRITICAL
    if delay_days is None:
        raise ValueError("delay_days is None but delay_beyond_horizon is False")
    return _highest_reached(delay_days, _delay_levels(thresholds.retraso_dias[market]))


def minimum_severity(gap: Severity, delay: Severity) -> Severity:
    """§2: the max of the gap and delay severities."""
    return max(gap, delay)
