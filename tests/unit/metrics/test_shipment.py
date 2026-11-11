"""009 T12: the shipment perspective of a combination (R10, E15c-d)."""

import pytest
from incident_builders import incident_context, incident_snapshot

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import Combination, Snapshot
from plant_monitor.domain.perspectives import ShipmentPerspective
from plant_monitor.metrics.engine import compute_metrics
from plant_monitor.metrics.shipment import shipment_perspective

SE = Combination(modelo=Model.SUV, mercado=Market.EUROPE)


@pytest.mark.parametrize(
    ("snapshot_id", "expected"),
    [
        pytest.param(
            "S005",
            ShipmentPerspective(
                unidades_demoradas=1,
                retraso_dias=0.0,
                embarque_asignado="EUR-0305",
                embarque_alcanzable="EUR-0305",
            ),
            id="c-one-delayed-unit",
        ),
        pytest.param(
            "S004",
            ShipmentPerspective(
                unidades_demoradas=0, retraso_dias=0.0, embarque_asignado=None, embarque_alcanzable=None
            ),
            id="d-no-unit",
        ),
    ],
)
def test_e15cd_shipment_of_se_at_the_incident_fixture(
    snapshot_id: str, expected: ShipmentPerspective
) -> None:
    """E15c-d: the delayed count, the combination delay and the worst unit's shipments, or nulls."""
    plant = incident_context()
    snapshot = Snapshot.model_validate(incident_snapshot(snapshot_id))
    metrics = compute_metrics(snapshot, (), plant)[SE]
    result = shipment_perspective(snapshot.unidades, SE, snapshot.timestamp, metrics, plant)
    assert result == expected
