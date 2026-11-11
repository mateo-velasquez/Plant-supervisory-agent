"""009 builders: the notice ids a decision requires, as the coordinator step passes them to perspectives."""

from plant_monitor.domain.notices import NoticeType
from plant_monitor.runner.pipeline import SnapshotDecision


def required_ids(decision: SnapshotDecision) -> list[str]:
    """Alert ids, then the report's news ids, as 'writer.required()' lists them."""
    alerts = [n.notice_id for n in decision.notices.decisions if n.tipo is NoticeType.ALERT]
    report = decision.notices.report
    return alerts + ([] if report is None else [n.notice_id for n in report.novedades])
