"""Builders for the 016 forecast tests: the calendar SYN, plan rows and 'forecast_snapshot' calls."""

import json
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from plant_monitor.domain.calendar import HeldOutPolicy, calendar_order, snapshot_position
from plant_monitor.domain.enums import Market, Model, Severity, ShiftPosition
from plant_monitor.domain.forecast import (
    ForecastBasis,
    ForecastPoint,
    ForecastRow,
    ForecastStatus,
    ForecastWarning,
    Thresholds3,
)
from plant_monitor.domain.models import Combination, CombinationMetrics, PlanRow, Shift, all_combinations
from plant_monitor.ingestion.plant import load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.forecast import ForecastConfig, WindowBase, forecast_snapshot
from plant_monitor.metrics.plan import cumulative_plan, gap_pct, shift_plan
from plant_monitor.metrics.severity import gap_severity
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds

from builders import FIXTURE_PLANT

if TYPE_CHECKING:
    from plant_monitor.dashboard.source import Calendar, RunView
    from plant_monitor.runner.forecast_step import ForecastSink

P = Combination(modelo=Model.PICKUP, mercado=Market.LOCAL)
SB = Combination(modelo=Model.SEDAN, mercado=Market.BRAZIL)
THRESHOLDS = load_thresholds(FIXTURE_PLANT / "umbrales.yaml")
_FIRST_START = datetime(2026, 3, 2, 6, 0)
_SHIFT_LENGTH = timedelta(hours=8)


def _syn() -> list[Shift]:
    """The spec's SYN: T01 to T12, three 8-h shifts a day; S(2k-1) is Tk's mid and S(2k) its closing."""
    return [
        Shift(
            turno_id=f"T{k:02d}",
            inicio=_FIRST_START + _SHIFT_LENGTH * (k - 1),
            fin=_FIRST_START + _SHIFT_LENGTH * k,
            snapshot_medio=f"S{2 * k - 1:03d}",
            snapshot_cierre=f"S{2 * k:03d}",
        )
        for k in range(1, 13)
    ]


SYN = _syn()


def plan_rows(
    units: int, *, combo: Combination = P, overrides: Mapping[str, int] | None = None
) -> list[PlanRow]:
    """'units' per shift for 'combo' in every SYN shift, with per-shift 'overrides'; the rest plan 0."""
    changed = overrides or {}
    return [
        PlanRow(
            turno_id=shift.turno_id,
            modelo=combo.modelo,
            mercado=combo.mercado,
            unidades_plan=changed.get(shift.turno_id, units),
        )
        for shift in SYN
    ]


def closed_calendar(first_shift: str) -> tuple[Shift, ...]:
    """The forecast calendar with the guard closed: SYN shifts before 'first_shift' (R4)."""
    refused = HeldOutPolicy.from_calendar(SYN, first_shift, is_open=False).refused_shifts
    return tuple(shift for shift in calendar_order(SYN) if shift.turno_id not in refused)


def syn_context(plan: list[PlanRow]) -> PlantContext:
    """Plant context over SYN with 'plan' and the fixture standards, shipments and thresholds."""
    return PlantContext(
        plan=plan,
        shifts=SYN,
        standards=StandardsTable.from_rows(load_standards(FIXTURE_PLANT / "tiempos_estandar.csv")),
        shipments=ShipmentsTable.from_rows(load_shipments(FIXTURE_PLANT / "embarques.csv")),
        thresholds=THRESHOLDS,
    )


class _FailingSink:
    """A 'ForecastSink' that stores the first rows of one snapshot and then raises 'ValueError'."""

    def __init__(self, inner: ForecastSink, fail_at: str, rows_before_raise: int) -> None:
        self._inner = inner
        self._fail_at = fail_at
        self._rows_before_raise = rows_before_raise

    def savepoint(self) -> AbstractContextManager[None]:
        return self._inner.savepoint()

    def save(self, snapshot_id: str, rows: Sequence[ForecastRow]) -> None:
        if snapshot_id != self._fail_at:
            self._inner.save(snapshot_id, rows)
            return
        self._inner.save(snapshot_id, rows[: self._rows_before_raise])
        raise ValueError("sink failed")


def failing_sink(inner: ForecastSink, *, fail_at: str, rows_before_raise: int = 4) -> ForecastSink:
    """Wrap 'inner' so 'save' for 'fail_at' inserts 'rows_before_raise' rows and then raises."""
    return _FailingSink(inner, fail_at, rows_before_raise)


def fc(
    seq: int,
    progress: int,
    base: int | None,
    *,
    plan: list[PlanRow],
    raised: frozenset[Combination] = frozenset(),
    delay: Severity = Severity.NONE,
    window: int = 4,
    horizon: int = 3,
    calendar: Sequence[Shift] | None = None,
    combo: Combination = P,
) -> tuple[ForecastRow, ...]:
    """The spec's FC: 'forecast_snapshot' at 'seq'; 'base' is progress at n - W (None = warm-up)."""
    snapshot_id = f"S{seq:03d}"
    shift, position = snapshot_position(SYN, snapshot_id)
    planned = cumulative_plan(plan, SYN, shift.turno_id, position is ShiftPosition.CLOSING)
    in_shift = shift_plan(plan, shift.turno_id)
    metrics: dict[Combination, CombinationMetrics] = {}
    for other in all_combinations():
        done = progress if other == combo else 0
        gap = done - planned[other]
        pct = gap_pct(gap, in_shift[other])
        level = gap_severity(gap, pct, THRESHOLDS)
        delayed = delay if other == combo else Severity.NONE
        metrics[other] = CombinationMetrics(
            combination=other,
            progress=done,
            cumulative_plan=planned[other],
            gap_units=gap,
            gap_pct=pct,
            delay_days=None,
            delay_beyond_horizon=False,
            bottleneck=None,
            gap_severity=level,
            delay_severity=delayed,
            minimum_severity=max(level, delayed),
        )
    window_base = (
        None
        if base is None
        else WindowBase(
            progress={other: base if other == combo else 0 for other in all_combinations()},
            first_snapshot_id=f"S{seq - window + 1:03d}",
        )
    )
    ctx = syn_context(plan)
    return forecast_snapshot(
        snapshot_id=snapshot_id,
        seq=seq,
        metrics=metrics,
        raised=raised,
        base=window_base,
        calendar=calendar_order(SYN) if calendar is None else calendar,
        ctx=ctx,
        config=ForecastConfig(window=window, horizon=horizon),
    )


def of(rows: Sequence[ForecastRow], combo: Combination = P) -> ForecastRow:
    """The row of 'combo' among the nine."""
    return next(row for row in rows if row.combination == combo)


_S001_AT = datetime(2026, 3, 2, 10, 0)
_LINES = Thresholds3(media=7.2, alta=14.4, critica=25.2)
_ABOVE: dict[Severity, Severity | None] = {
    Severity.NONE: Severity.MEDIUM,
    Severity.MEDIUM: Severity.HIGH,
    Severity.HIGH: Severity.CRITICAL,
    Severity.CRITICAL: None,
}


def snapshot_time(seq: int) -> datetime:
    """Scheduled time of snapshot 'seq': S001 is 10:00 on the first day and each one adds 4 h."""
    return _S001_AT + timedelta(hours=4) * (seq - 1)


def fr(
    seq: int,
    status: ForecastStatus,
    *,
    combo: Combination = P,
    gap: Severity = Severity.NONE,
    points: int = 0,
    crossing: int | None = None,
) -> ForecastRow:
    """The spec's FR: a hand-built stored row; 'points' follow 'seq', 'crossing' is a snapshot number."""
    target = _ABOVE[gap]
    stored = tuple(
        ForecastPoint(
            snapshot_id=f"S{n:03d}",
            scheduled_at=snapshot_time(n),
            gap_units=-2.0 * (n - seq),
            thresholds=_LINES,
        )
        for n in range(seq + 1, seq + 1 + points)
    )
    warning = None
    if crossing is not None:
        assert target is not None
        warning = ForecastWarning(
            target_level=target,
            crossing_snapshot_id=f"S{crossing:03d}",
            crossing_at=snapshot_time(crossing),
            hours=4.0 * (crossing - seq),
        )
    warm_up = status == "warm_up"
    return ForecastRow(
        seq=seq,
        snapshot_id=f"S{seq:03d}",
        combination=combo,
        scheduled_at=snapshot_time(seq),
        gap_units=-1.0,
        gap_severity=gap,
        effective_severity=gap,
        status=status,
        target_level=target,
        thresholds=None if warm_up else _LINES,
        points=stored,
        basis=None
        if warm_up
        else ForecastBasis(
            rate=10.0,
            plan_per_snapshot=12.0,
            window_first=f"S{seq - 3:03d}",
            window_last=f"S{seq:03d}",
            points=4,
            horizon=3,
        ),
        warning=warning,
    )


def forecast_view(rows: Sequence[ForecastRow]) -> RunView:
    """A 'RunView' with the guard open, processed snapshots 1 to the last row's 'seq' and 'rows' stored."""
    from dashboard_builders import run_view

    from plant_monitor.cases.registry.run_reader import ProcessedRow, RunRows

    last = max(row.seq for row in rows)
    return run_view(
        RunRows(
            processed=tuple(ProcessedRow(snapshot_id=f"S{n:03d}", seq=n) for n in range(1, last + 1)),
            cases=(),
            history=(),
            notices=(),
            forecasts=tuple(rows),
        )
    )


def forecast_calendar() -> Calendar:
    """The SYN shifts and the nine combinations."""
    from plant_monitor.dashboard.source import Calendar

    return Calendar(shifts=tuple(calendar_order(SYN)), combinations=all_combinations())


def ft(rows: Sequence[ForecastRow], at: int) -> dict[str, Any]:
    """The spec's FT: 'build_forecast' over 'rows' at position 'at', as the client parses it."""
    from plant_monitor.dashboard.forecast import build_forecast

    view = forecast_view(rows)
    payload = build_forecast(view, forecast_calendar(), view.resolve_at(at))
    parsed: dict[str, Any] = json.loads(json.dumps(payload))
    return parsed
