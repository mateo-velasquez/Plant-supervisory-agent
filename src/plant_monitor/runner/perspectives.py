"""Perspectives of the cases behind the notices that still need a text (009 R10)."""

from collections.abc import Sequence

from plant_monitor.cases.perspectives import gap_perspective
from plant_monitor.domain.perspectives import BottleneckPerspective, CasePerspective
from plant_monitor.mcp_server.context import CaseReader
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.shipment import shipment_perspective
from plant_monitor.runner.pipeline import SnapshotDecision


def case_perspectives(
    decision: SnapshotDecision, required: Sequence[str], cases: CaseReader, plant: PlantContext
) -> tuple[CasePerspective, ...]:
    """One item per case of the 'required' notice ids, in their order, each case once."""
    notices = list(decision.notices.decisions)
    if decision.notices.report is not None:
        notices.extend(decision.notices.report.novedades)
    case_of = {notice.notice_id: notice.case_id for notice in notices}
    case_ids = dict.fromkeys(case_of[notice_id] for notice_id in required)
    items: list[CasePerspective] = []
    for case_id in case_ids:
        case = cases.get_case(case_id)
        if case is None:
            raise ValueError(f"case {case_id} is not in the registry")
        metrics = decision.metrics[case.combination]
        items.append(
            CasePerspective(
                case_id=case_id,
                gap=gap_perspective(case, metrics, cases.history(case_id)),
                embarque=shipment_perspective(
                    decision.snapshot.unidades,
                    case.combination,
                    decision.snapshot.timestamp,
                    metrics,
                    plant,
                ),
                cuello=BottleneckPerspective(etapa=metrics.bottleneck),
            )
        )
    return tuple(items)
