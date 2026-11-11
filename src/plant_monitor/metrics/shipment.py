"""Shipment perspective of a combination: delayed units and the shipments of the worst unit (009 R10)."""

from collections.abc import Sequence
from datetime import datetime

from plant_monitor.domain.enums import PRODUCTION_STAGES
from plant_monitor.domain.models import Combination, CombinationMetrics, Unit
from plant_monitor.domain.numbers import round_optional
from plant_monitor.domain.perspectives import ShipmentPerspective
from plant_monitor.metrics.bottleneck import is_delayed
from plant_monitor.metrics.delay import projected_yard_arrival, reachable_shipment, unit_delay_days
from plant_monitor.metrics.engine import PlantContext


def shipment_perspective(
    units: Sequence[Unit],
    combination: Combination,
    at: datetime,
    metrics: CombinationMetrics,
    plant: PlantContext,
) -> ShipmentPerspective:
    """Delayed count, combination delay, and the shipments of the unit that sets that delay."""
    own = [u for u in units if Combination(modelo=u.modelo, mercado=u.mercado) == combination]
    tolerance = plant.thresholds.demora.tolerancia_minutos
    delayed = sum(is_delayed(u, at, plant.standards, tolerance) for u in own)
    measured = [
        (u, unit_delay_days(u, at, plant.standards, plant.shipments))
        for u in own
        if u.etapa in PRODUCTION_STAGES
    ]
    measured.sort(key=lambda item: (item[1] is not None, -(item[1] or 0.0), item[0].unidad_id))
    assigned: str | None = None
    reachable: str | None = None
    if measured:
        worst = measured[0][0]
        assigned = worst.embarque_asignado
        shipment = reachable_shipment(
            worst.mercado, projected_yard_arrival(worst, at, plant.standards), plant.shipments
        )
        reachable = None if shipment is None else shipment.embarque_id
    return ShipmentPerspective(
        unidades_demoradas=delayed,
        retraso_dias=round_optional(metrics.delay_days),
        embarque_asignado=assigned,
        embarque_alcanzable=reachable,
    )
