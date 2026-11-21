"""Pure gap forecast: a linear progress trend against the known plan (016 R2-R7)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from plant_monitor.domain.calendar import future_snapshots, scheduled_time, snapshot_position
from plant_monitor.domain.cases import effective_severity
from plant_monitor.domain.enums import Severity, ShiftPosition
from plant_monitor.domain.forecast import (
    ForecastBasis,
    ForecastPoint,
    ForecastRow,
    ForecastStatus,
    ForecastWarning,
    Thresholds3,
)
from plant_monitor.domain.models import Combination, CombinationMetrics, Shift, all_combinations
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.plan import PERCENT, SHIFTS_PER_DAY, cumulative_plan, gap_pct, shift_plan
from plant_monitor.metrics.severity import gap_severity
from plant_monitor.metrics.thresholds import Thresholds

SECONDS_PER_HOUR = 3600
MIN_WINDOW = 2
MIN_HORIZON = 1


@dataclass(frozen=True)
class ForecastConfig:
    """Trend window and look-ahead, both in snapshots."""

    window: int
    horizon: int

    def __post_init__(self) -> None:
        if self.window < MIN_WINDOW:
            raise ValueError(f"window must be >= {MIN_WINDOW}, got {self.window}")
        if self.horizon < MIN_HORIZON:
            raise ValueError(f"horizon must be >= {MIN_HORIZON}, got {self.horizon}")


@dataclass(frozen=True)
class WindowBase:
    """Progress at the start of the trend window."""

    progress: Mapping[Combination, int]  # progress after seq n - W
    first_snapshot_id: str  # seq n - W + 1


def threshold_units(shift_plan: int, thresholds: Thresholds) -> Thresholds3 | None:
    """Units behind that reach each gap level for a shift plan; None when the plan is 0 (Q-16)."""
    if shift_plan == 0:
        return None
    gap = thresholds.gap
    daily = shift_plan * SHIFTS_PER_DAY

    def level(percent: float) -> float:
        return max(float(gap.minimo_unidades), percent / PERCENT * daily)

    return Thresholds3(media=level(gap.media), alta=level(gap.alta), critica=level(gap.critica))


@dataclass(frozen=True)
class _Slot:
    """One future snapshot: its time, hours ahead, in-shift plan and cumulative plan."""

    snapshot_id: str
    at: datetime
    hours: float
    in_shift: Mapping[Combination, int]
    planned: Mapping[Combination, float]


def _target(level: Severity) -> Severity | None:
    """The level above 'level'; None when it is already 'critica'."""
    ordered = list(Severity)
    index = ordered.index(level)
    return None if index == len(ordered) - 1 else ordered[index + 1]


def forecast_snapshot(
    snapshot_id: str,
    seq: int,
    metrics: Mapping[Combination, CombinationMetrics],
    raised: frozenset[Combination],
    base: WindowBase | None,
    calendar: Sequence[Shift],
    ctx: PlantContext,
    config: ForecastConfig,
) -> tuple[ForecastRow, ...]:
    """One forecast row per combination at snapshot N, in canonical order."""
    shift, position = snapshot_position(ctx.shifts, snapshot_id)
    now = scheduled_time(shift, position)
    now_plan = shift_plan(ctx.plan, shift.turno_id)
    future = future_snapshots(calendar, snapshot_id, config.horizon) if base is not None else ()
    future_plans: list[_Slot] = []
    for fshift, fposition, snap in future:
        at = scheduled_time(fshift, fposition)
        future_plans.append(
            _Slot(
                snapshot_id=snap,
                at=at,
                hours=(at - now).total_seconds() / SECONDS_PER_HOUR,
                in_shift=shift_plan(ctx.plan, fshift.turno_id),
                planned=cumulative_plan(
                    ctx.plan, ctx.shifts, fshift.turno_id, fposition is ShiftPosition.CLOSING
                ),
            )
        )
    rows: list[ForecastRow] = []
    for combo in all_combinations():
        current = metrics[combo]
        target = _target(current.gap_severity)
        effective = effective_severity(current.minimum_severity, combo in raised)
        points: tuple[ForecastPoint, ...] = ()
        basis: ForecastBasis | None = None
        warning: ForecastWarning | None = None
        status: ForecastStatus = "warm_up"
        if base is not None:
            rate = (current.progress - base.progress[combo]) / config.window
            crossing: ForecastWarning | None = None
            built: list[ForecastPoint] = []
            for step, slot in enumerate(future_plans, start=1):
                projected = current.progress + rate * step - slot.planned[combo]
                built.append(
                    ForecastPoint(
                        snapshot_id=slot.snapshot_id,
                        scheduled_at=slot.at,
                        gap_units=projected,
                        thresholds=threshold_units(slot.in_shift[combo], ctx.thresholds),
                    )
                )
                hit = gap_severity(projected, gap_pct(projected, slot.in_shift[combo]), ctx.thresholds)
                if crossing is None and target is not None and hit >= target:
                    crossing = ForecastWarning(
                        target_level=target,
                        crossing_snapshot_id=slot.snapshot_id,
                        crossing_at=slot.at,
                        hours=slot.hours,
                    )
            points = tuple(built)
            per_snapshot = (
                (future_plans[-1].planned[combo] - current.cumulative_plan) / len(future_plans)
                if future_plans
                else None
            )
            basis = ForecastBasis(
                rate=rate,
                plan_per_snapshot=per_snapshot,
                window_first=base.first_snapshot_id,
                window_last=snapshot_id,
                points=config.window,
                horizon=config.horizon,
            )
            if target is None:
                status = "no_target"
            elif effective >= target:
                status = "suppressed"
            elif crossing is not None:
                status, warning = "warning", crossing
            else:
                status = "no_crossing"
        rows.append(
            ForecastRow(
                seq=seq,
                snapshot_id=snapshot_id,
                combination=combo,
                scheduled_at=now,
                gap_units=current.gap_units,
                gap_severity=current.gap_severity,
                effective_severity=effective,
                status=status,
                target_level=target,
                thresholds=threshold_units(now_plan[combo], ctx.thresholds),
                points=points,
                basis=basis,
                warning=warning,
            )
        )
    return tuple(rows)
