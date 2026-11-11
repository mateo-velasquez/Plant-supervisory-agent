"""009 T12: 'case_perspectives' over the case registry (R10, E15e)."""

from incident_builders import incident_context
from incident_runs import incident_run
from perspective_builders import required_ids

from plant_monitor.domain.enums import Stage
from plant_monitor.domain.perspectives import (
    BottleneckPerspective,
    CasePerspective,
    GapPerspective,
    ShipmentPerspective,
)
from plant_monitor.runner.perspectives import case_perspectives


def test_e15e_se_at_s005_has_its_gap_shipment_and_quality_bottleneck() -> None:
    """E15e: one item for SE's notice id, with the stage of the combination's bottleneck."""
    with incident_run() as run:
        run.through(4)
        decision = run.step(5)
        se_ids = [n.notice_id for n in decision.notices.decisions if n.case_id == "S005-SUV-Europa"]
        assert required_ids(decision) == []
        result = case_perspectives(decision, se_ids, run.registry.cases, incident_context())
    assert result == (
        CasePerspective(
            case_id="S005-SUV-Europa",
            gap=GapPerspective(unidades=-4.0, pct_plan_diario=-13.3, en_ultimo_informe=None),
            embarque=ShipmentPerspective(
                unidades_demoradas=1,
                retraso_dias=0.0,
                embarque_asignado="EUR-0305",
                embarque_alcanzable="EUR-0305",
            ),
            cuello=BottleneckPerspective(etapa=Stage.QUALITY),
        ),
    )
