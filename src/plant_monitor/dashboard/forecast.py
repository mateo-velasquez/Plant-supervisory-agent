"""The Pronóstico payload: active warnings, combination charts and Anticipación (016 R11-R15); pure."""

from collections.abc import Sequence
from decimal import ROUND_HALF_EVEN, Decimal

from plant_monitor.dashboard.anticipation import format_hours, hours_number, score_episodes
from plant_monitor.dashboard.payloads import (
    AccuracyBlock,
    AccuracyCounts,
    BasisView,
    CellForecast,
    CombinationWarning,
    ForecastCombination,
    ForecastHeldOut,
    ForecastOmitted,
    ForecastPayload,
    HistoryPoint,
    Lines,
    ProjectionPoint,
    WarningView,
)
from plant_monitor.dashboard.source import Calendar, RunView
from plant_monitor.domain.forecast import ForecastRow, Thresholds3
from plant_monitor.domain.models import all_combinations

_TWO = Decimal("0.01")
_ONE = Decimal("0.1")


def _fixed(value: float, step: Decimal) -> str:
    """'value' with the decimals of 'step', half-even (I11)."""
    return format(Decimal(str(value)).quantize(step, rounding=ROUND_HALF_EVEN), "f")


def active_warnings(rows: Sequence[ForecastRow], at: int) -> tuple[ForecastRow, ...]:
    """Rows at position 'at' with a warning, by hours and then canonical combination order."""
    order = {combo: index for index, combo in enumerate(all_combinations())}
    warned = [(row, row.warning) for row in rows if row.seq == at and row.warning is not None]
    warned.sort(key=lambda pair: (pair[1].hours, order[pair[0].combination]))
    return tuple(row for row, _ in warned)


def warning_label(row: ForecastRow) -> str:
    """'<id> · <HH:MM> (en <hours> h)' of the row's warning."""
    warning = row.warning
    assert warning is not None
    return (
        f"{warning.crossing_snapshot_id} · {warning.crossing_at:%H:%M} (en {format_hours(warning.hours)} h)"
    )


def cell_forecast(row: ForecastRow) -> CellForecast:
    """The marker of Planta's cell (R16)."""
    assert row.warning is not None
    return CellForecast(target_level=row.warning.target_level.value, label=warning_label(row))


def _lines(thresholds: Thresholds3 | None) -> Lines | None:
    """Threshold lines as gap values (at most 0); None where the shift plan is 0."""
    if thresholds is None:
        return None
    return Lines(media=-thresholds.media, alta=-thresholds.alta, critica=-thresholds.critica)


def _threshold(row: ForecastRow) -> str | None:
    """The target's units at the crossing snapshot, one decimal."""
    warning = row.warning
    assert warning is not None
    point = next((p for p in row.points if p.snapshot_id == warning.crossing_snapshot_id), None)
    if point is None or point.thresholds is None:
        return None
    return _fixed(getattr(point.thresholds, warning.target_level.value), _ONE)


def _warning_view(row: ForecastRow) -> WarningView:
    warning, basis = row.warning, row.basis
    assert warning is not None
    assert basis is not None
    return WarningView(
        modelo=str(row.combination.modelo),
        mercado=str(row.combination.mercado),
        target_level=warning.target_level.value,
        label=warning_label(row),
        hours=hours_number(warning.hours),
        basis=BasisView(
            rate=_fixed(basis.rate, _TWO),
            plan_per_snapshot=None
            if basis.plan_per_snapshot is None
            else _fixed(basis.plan_per_snapshot, _TWO),
            window=f"{basis.window_first}–{basis.window_last}",  # noqa: RUF001
            threshold=_threshold(row),
        ),
    )


def _combination(modelo: str, mercado: str, rows: Sequence[ForecastRow], at: int) -> ForecastCombination:
    """History of every row up to 'at' and the projection of the row at 'at'."""
    current = next((r for r in rows if r.seq == at), None)
    return ForecastCombination(
        modelo=modelo,
        mercado=mercado,
        status=None if current is None else current.status,
        gap_severity=None if current is None else current.gap_severity.value,
        effective_severity=None if current is None else current.effective_severity.value,
        target_level=None if current is None or current.target_level is None else current.target_level.value,
        history=[
            HistoryPoint(seq=r.seq, snapshot_id=r.snapshot_id, gap=r.gap_units, lines=_lines(r.thresholds))
            for r in rows
        ],
        projection=[
            ProjectionPoint(
                snapshot_id=p.snapshot_id,
                time=f"{p.scheduled_at:%H:%M}",
                gap=p.gap_units,
                lines=_lines(p.thresholds),
            )
            for p in (() if current is None else current.points)
        ],
        warning=None
        if current is None or current.warning is None
        else CombinationWarning(
            target_level=current.warning.target_level.value, label=warning_label(current)
        ),
    )


def build_forecast(view: RunView, calendar: Calendar, at: int) -> ForecastPayload:
    """The forecast payload at position 'at' (already resolved by 'RunView.resolve_at')."""
    stored = view.rows.forecasts
    available = view.registry == "ok" and stored is not None
    rows = [r for r in (stored or ()) if r.seq <= at] if available else []
    omitted = view.omitted
    heldout = ForecastHeldOut(
        open=view.policy_open,
        omitted=ForecastOmitted(
            snapshots=omitted.snapshots,
            notices=omitted.notices,
            trace_lines=omitted.trace_lines,
            forecast_rows=omitted.forecast_rows,
        ),
    )
    accuracy = (
        score_episodes(rows, at)
        if available
        else AccuracyBlock(
            counts=AccuracyCounts(fulfilled=0, not_fulfilled=0, pending=0, missed=0, no_forecast=0),
            mean_lead_hours=None,
            episodes=[],
        )
    )
    return ForecastPayload(
        at=at,
        latest=view.resolve_at(None),
        positions=list(view.positions()),
        registry=view.registry,
        state="ok" if available else "unavailable",
        heldout=heldout,
        warnings=[_warning_view(r) for r in active_warnings(rows, at)],
        combinations=[
            _combination(
                str(combo.modelo), str(combo.mercado), [r for r in rows if r.combination == combo], at
            )
            for combo in calendar.combinations
        ]
        if available
        else [],
        accuracy=accuracy,
    )
