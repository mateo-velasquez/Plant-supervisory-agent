"""View models and pure builders of the read tools; Spanish field names (ADR-0005), rounded floats."""

from collections.abc import Sequence
from datetime import datetime
from typing import Final

from plant_monitor.cases.novelty import active_rows
from plant_monitor.domain.cases import Case, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, FrozenModel, Unit, all_combinations
from plant_monitor.domain.notices import ActiveCaseRow
from plant_monitor.mcp_server.context import SnapshotFrame
from plant_monitor.metrics.bottleneck import is_delayed
from plant_monitor.metrics.delay import projected_yard_arrival, reachable_shipment, unit_delay_days
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.tables import is_repainting

DECIMALS: Final = 1
"""Decimal places of every float in a view (R12)."""


class AvailableLogbook(FrozenModel):
    """A logbook readable at the current snapshot and the snapshot it closed at."""

    turno_id: str
    cerrada_en: str


class LogbooksView(FrozenModel):
    """Output of 'list_available_logbooks'."""

    snapshot_id: str
    disponibles: tuple[AvailableLogbook, ...]


class DeviationRow(FrozenModel):
    """Metrics of one combination at the current snapshot (R8)."""

    modelo: Model
    mercado: Market
    case_id: str | None
    avance: int
    plan_acumulado: float
    gap_unidades: float
    gap_pct: float | None
    retraso_dias: float | None
    etapa_cuello: Stage | None
    severidad_gap: Severity
    severidad_retraso: Severity
    severidad_minima: Severity


class DeviationsView(FrozenModel):
    """Output of 'get_deviations'."""

    snapshot_id: str
    combinaciones: tuple[DeviationRow, ...]


class ActiveCasesView(FrozenModel):
    """Output of 'get_active_cases'."""

    snapshot_id: str
    casos: tuple[ActiveCaseRow, ...]


class LastReport(FrozenModel):
    """The state and severity a case had in its last report."""

    snapshot_id: str
    estado: CaseState
    severidad: Severity


class HistoryRow(FrozenModel):
    """A case at one past snapshot (R10)."""

    snapshot_id: str
    estado: CaseState
    severidad: Severity
    severidad_minima: Severity
    gap_unidades: float
    gap_pct: float | None
    retraso_dias: float | None
    etapa_cuello: Stage | None


class CaseView(FrozenModel):
    """Output of 'get_case'; 'historial' is newest first."""

    case_id: str
    modelo: Model
    mercado: Market
    abierto_en: str
    estado: CaseState
    severidad: Severity
    severidad_minima: Severity
    subida_por_agente: bool
    severidad_maxima: Severity | None
    resuelto_en: str | None
    ultimo_informe: LastReport | None
    historial: tuple[HistoryRow, ...]
    historial_omitido: int = 0


class DelayedUnit(FrozenModel):
    """A unit that is delayed at the current snapshot (FR-10, R11)."""

    unidad_id: str
    etapa: Stage
    minutos_en_etapa: int
    minutos_estandar: int
    repintado: bool
    embarque_asignado: str
    embarque_alcanzable: str | None
    retraso_dias: float | None


class DelayedUnitsView(FrozenModel):
    """Output of 'get_delayed_units'."""

    snapshot_id: str
    modelo: Model
    mercado: Market
    etapa_cuello: Stage | None
    unidades: tuple[DelayedUnit, ...]
    omitidas: int = 0


def _round(value: float) -> float:
    """'value' rounded to 'DECIMALS' places."""
    return round(value, DECIMALS)


def _round_optional(value: float | None) -> float | None:
    """'value' rounded to 'DECIMALS' places, or None."""
    return None if value is None else _round(value)


def _keep[T](items: tuple[T, ...], kept: int | None) -> tuple[tuple[T, ...], int]:
    """The first 'kept' items and how many were omitted; all of them when 'kept' is None."""
    if kept is None:
        return items, 0
    return items[:kept], len(items) - kept


def _deviation_row(metrics: CombinationMetrics, case_id: str | None) -> DeviationRow:
    """One R8 row from the code's metrics, floats rounded."""
    return DeviationRow(
        modelo=metrics.combination.modelo,
        mercado=metrics.combination.mercado,
        case_id=case_id,
        avance=metrics.progress,
        plan_acumulado=_round(metrics.cumulative_plan),
        gap_unidades=_round(metrics.gap_units),
        gap_pct=_round_optional(metrics.gap_pct),
        retraso_dias=_round_optional(metrics.delay_days),
        etapa_cuello=metrics.bottleneck,
        severidad_gap=metrics.gap_severity,
        severidad_retraso=metrics.delay_severity,
        severidad_minima=metrics.minimum_severity,
    )


def deviations_view(frame: SnapshotFrame, active: Sequence[Case]) -> DeviationsView:
    """Metric rows of all 9 combinations in 'all_combinations()' order, each with its active case."""
    case_ids = {case.combination: case.case_id for case in active}
    rows = tuple(_deviation_row(frame.metrics[combo], case_ids.get(combo)) for combo in all_combinations())
    return DeviationsView(snapshot_id=frame.snapshot_id, combinaciones=rows)


def _rounded_active_row(row: ActiveCaseRow) -> ActiveCaseRow:
    """'row' with its floats rounded to 'DECIMALS' places."""
    return ActiveCaseRow(
        case_id=row.case_id,
        modelo=row.modelo,
        mercado=row.mercado,
        gap_unidades=_round(row.gap_unidades),
        gap_pct=_round_optional(row.gap_pct),
        retraso_dias=_round_optional(row.retraso_dias),
        severidad=row.severidad,
        severidad_maxima=row.severidad_maxima,
        estado=row.estado,
        etapa_cuello=row.etapa_cuello,
    )


def active_cases_view(frame: SnapshotFrame, active: Sequence[Case]) -> ActiveCasesView:
    """Active cases as report rows with the current snapshot's values (R9)."""
    rows = tuple(_rounded_active_row(row) for row in active_rows(active, frame.metrics))
    return ActiveCasesView(snapshot_id=frame.snapshot_id, casos=rows)


def _history_row(row: CaseHistoryRow) -> HistoryRow:
    """One R10 history row, effective severity and floats rounded."""
    return HistoryRow(
        snapshot_id=row.snapshot_id,
        estado=row.state,
        severidad=row.effective_severity,
        severidad_minima=row.minimum_severity,
        gap_unidades=_round(row.gap_units),
        gap_pct=_round_optional(row.gap_pct),
        retraso_dias=_round_optional(row.delay_days),
        etapa_cuello=row.bottleneck,
    )


def _last_report(case: Case) -> LastReport | None:
    """The case's last report, or None if it was never reported."""
    if (
        case.last_reported_at is None
        or case.last_reported_state is None
        or case.last_reported_severity is None
    ):
        return None
    return LastReport(
        snapshot_id=case.last_reported_at,
        estado=case.last_reported_state,
        severidad=case.last_reported_severity,
    )


def case_view(case: Case, history: Sequence[CaseHistoryRow], kept: int | None = None) -> CaseView:
    """One case with its last report and its history, newest first, keeping 'kept' rows (R10)."""
    newest_first = tuple(_history_row(row) for row in reversed(history))
    rows, omitted = _keep(newest_first, kept)
    return CaseView(
        case_id=case.case_id,
        modelo=case.combination.modelo,
        mercado=case.combination.mercado,
        abierto_en=case.opened_at,
        estado=case.state,
        severidad=case.current_severity,
        severidad_minima=case.minimum_severity,
        subida_por_agente=case.raised,
        severidad_maxima=case.max_severity_since_report,
        resuelto_en=case.resolved_at,
        ultimo_informe=_last_report(case),
        historial=rows,
        historial_omitido=omitted,
    )


def _minutes_in_stage(unit: Unit, at: datetime) -> int:
    """Whole minutes since the unit entered its stage, floored at 0 (Q-19)."""
    return max(0, int((at - unit.ingreso_etapa).total_seconds() // 60))


def _delayed_unit(unit: Unit, delay: float | None, frame_at: datetime, plant: PlantContext) -> DelayedUnit:
    """One R11 unit; the shipment and the delay come from the metrics functions."""
    reachable = reachable_shipment(
        unit.mercado, projected_yard_arrival(unit, frame_at, plant.standards), plant.shipments
    )
    return DelayedUnit(
        unidad_id=unit.unidad_id,
        etapa=unit.etapa,
        minutos_en_etapa=_minutes_in_stage(unit, frame_at),
        minutos_estandar=plant.standards.current_stage_minutes(unit),
        repintado=is_repainting(unit),
        embarque_asignado=unit.embarque_asignado,
        embarque_alcanzable=None if reachable is None else reachable.embarque_id,
        retraso_dias=_round_optional(delay),
    )


def delayed_units_view(
    frame: SnapshotFrame, combination: Combination, plant: PlantContext, kept: int | None = None
) -> DelayedUnitsView:
    """FR-10 delayed units of 'combination' with their bottleneck, in R11 order, keeping 'kept' units."""
    at = frame.at
    tolerance = plant.thresholds.demora.tolerancia_minutos
    units = [
        unit for unit in frame.units if Combination(modelo=unit.modelo, mercado=unit.mercado) == combination
    ]
    delayed = [unit for unit in units if is_delayed(unit, at, plant.standards, tolerance)]
    measured = [(unit, unit_delay_days(unit, at, plant.standards, plant.shipments)) for unit in delayed]

    def order(item: tuple[Unit, float | None]) -> tuple[bool, float, int, str]:
        """Null delay first, then delay descending, minutes over standard descending, unit id."""
        unit, delay = item
        over = _minutes_in_stage(unit, at) - plant.standards.current_stage_minutes(unit)
        return (delay is not None, -(delay or 0.0), -over, unit.unidad_id)

    measured.sort(key=order)
    rows, omitted = _keep(tuple(_delayed_unit(unit, delay, at, plant) for unit, delay in measured), kept)
    return DelayedUnitsView(
        snapshot_id=frame.snapshot_id,
        modelo=combination.modelo,
        mercado=combination.mercado,
        etapa_cuello=frame.metrics[combination].bottleneck,
        unidades=rows,
        omitidas=omitted,
    )
