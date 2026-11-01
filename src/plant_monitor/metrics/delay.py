"""Projected yard arrival, reachable shipment and delay in days (FR-08, FR-09, Q-04, Q-09)."""

from collections.abc import Iterable
from datetime import datetime, timedelta

from plant_monitor.domain.enums import PRODUCTION_STAGES, Market
from plant_monitor.domain.models import Shipment, Unit
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable

ONE_DAY = timedelta(days=1)


def projected_yard_arrival(unit: Unit, at: datetime, standards: StandardsTable) -> datetime:
    """`at` + what is left of the current stage standard (floored at 0) + every later standard to calidad.

    Only the current `pintura` stage of a repainting unit uses the rework standard; later stages
    always use their normal standard (literal reading of §1).
    """
    if unit.etapa not in PRODUCTION_STAGES:
        raise ValueError(f"unit {unit.unidad_id} is in {unit.etapa}; only production stages are projected")
    elapsed = at - unit.ingreso_etapa
    remaining = max(timedelta(0), timedelta(minutes=standards.current_stage_minutes(unit)) - elapsed)
    later_stages = PRODUCTION_STAGES[PRODUCTION_STAGES.index(unit.etapa) + 1 :]
    later_minutes = sum(standards.minutes(unit.modelo, stage) for stage in later_stages)
    return at + remaining + timedelta(minutes=later_minutes)


def reachable_shipment(market: Market, projected: datetime, shipments: ShipmentsTable) -> Shipment | None:
    """First shipment of `market` with `corte_en_patio > projected`; None past the last cut-off."""
    return shipments.first_cut_off_after(market, projected)


def unit_delay_days(
    unit: Unit, at: datetime, standards: StandardsTable, shipments: ShipmentsTable
) -> float | None:
    """Days between the reachable and the assigned departures, floored at 0 (Q-09); None beyond horizon."""
    projected = projected_yard_arrival(unit, at, standards)
    try:
        assigned = shipments.by_id(unit.embarque_asignado)
    except KeyError:
        raise ValueError(
            f"unit {unit.unidad_id}: embarque_asignado {unit.embarque_asignado} is not in embarques.csv"
        ) from None
    reachable = reachable_shipment(unit.mercado, projected, shipments)
    if reachable is None:
        return None
    return max(0.0, (reachable.salida - assigned.salida) / ONE_DAY)


def combination_delay(
    units: Iterable[Unit], at: datetime, standards: StandardsTable, shipments: ShipmentsTable
) -> tuple[float | None, bool]:
    """Max unit delay and whether it is beyond the horizon; units in `patio`/`despacho` are excluded.

    Q-04: one unit with no reachable shipment makes the whole combination None (worst unit dominates).
    """
    delays = [
        unit_delay_days(unit, at, standards, shipments) for unit in units if unit.etapa in PRODUCTION_STAGES
    ]
    known = [delay for delay in delays if delay is not None]
    if len(known) < len(delays):
        return None, True
    return max(known, default=0.0), False
