"""Deterministic metrics of every combination at one snapshot, composing the metrics functions."""

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import chain

from plant_monitor.domain.models import (
    Combination,
    CombinationMetrics,
    PlanRow,
    ReleasedUnit,
    Shift,
    Snapshot,
    Unit,
    all_combinations,
)
from plant_monitor.metrics.bottleneck import bottleneck_stage
from plant_monitor.metrics.delay import combination_delay
from plant_monitor.metrics.plan import cumulative_plan, gap_pct, snapshot_position
from plant_monitor.metrics.progress import count_progress
from plant_monitor.metrics.severity import delay_severity, gap_severity, minimum_severity
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import Thresholds


@dataclass(frozen=True)
class PlantContext:
    """Static plant data for the whole series, loaded once."""

    plan: list[PlanRow]
    shifts: list[Shift]
    standards: StandardsTable
    shipments: ShipmentsTable
    thresholds: Thresholds


def _shift_plan(plan: Iterable[PlanRow], shift_id: str) -> dict[Combination, int]:
    """Plan units of `shift_id` per combination; all 9 combinations present."""
    totals = dict.fromkeys(all_combinations(), 0)
    for row in plan:
        if row.turno_id == shift_id:
            totals[Combination(modelo=row.modelo, mercado=row.mercado)] += row.unidades_plan
    return totals


def _units_by_combination(units: Iterable[Unit]) -> dict[Combination, list[Unit]]:
    """Snapshot units grouped per combination; all 9 combinations present."""
    groups: dict[Combination, list[Unit]] = {combo: [] for combo in all_combinations()}
    for unit in units:
        groups[Combination(modelo=unit.modelo, mercado=unit.mercado)].append(unit)
    return groups


def compute_metrics(
    snapshot: Snapshot, released_so_far: Iterable[ReleasedUnit], ctx: PlantContext
) -> dict[Combination, CombinationMetrics]:
    """Metrics of all 9 combinations; progress counts distinct ids of earlier plus current releases."""
    shift_id, is_closing = snapshot_position(ctx.shifts, snapshot.snapshot_id)
    progress = count_progress(chain(released_so_far, snapshot.liberadas))
    planned = cumulative_plan(ctx.plan, ctx.shifts, shift_id, is_closing)
    shift_plan = _shift_plan(ctx.plan, shift_id)
    units = _units_by_combination(snapshot.unidades)
    at = snapshot.timestamp
    tolerance = ctx.thresholds.demora.tolerancia_minutos

    result: dict[Combination, CombinationMetrics] = {}
    for combo in all_combinations():
        gap_units = progress[combo] - planned[combo]
        pct = gap_pct(gap_units, shift_plan[combo])
        delay_days, beyond_horizon = combination_delay(units[combo], at, ctx.standards, ctx.shipments)
        gap_level = gap_severity(gap_units, pct, ctx.thresholds)
        delay_level = delay_severity(combo.mercado, delay_days, beyond_horizon, ctx.thresholds)
        result[combo] = CombinationMetrics(
            combination=combo,
            progress=progress[combo],
            cumulative_plan=planned[combo],
            gap_units=gap_units,
            gap_pct=pct,
            delay_days=delay_days,
            delay_beyond_horizon=beyond_horizon,
            bottleneck=bottleneck_stage(units[combo], at, ctx.standards, tolerance),
            gap_severity=gap_level,
            delay_severity=delay_level,
            minimum_severity=minimum_severity(gap_level, delay_level),
        )
    return result
