"""Gap perspective of a case: now and at its last report (009 R10)."""

from collections.abc import Sequence

from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.models import CombinationMetrics
from plant_monitor.domain.numbers import round_display, round_optional
from plant_monitor.domain.perspectives import GapAtReport, GapPerspective


def gap_perspective(case: Case, now: CombinationMetrics, history: Sequence[CaseHistoryRow]) -> GapPerspective:
    """The rounded gap at 'now' and in the history row of 'last_reported_at'; 'ValueError' with no row."""
    at_report: GapAtReport | None = None
    if case.last_reported_at is not None:
        rows = [row for row in history if row.snapshot_id == case.last_reported_at]
        if not rows:
            raise ValueError(f"case {case.case_id} has no history row at {case.last_reported_at}")
        at_report = GapAtReport(
            snapshot_id=case.last_reported_at,
            unidades=round_display(rows[0].gap_units),
            pct_plan_diario=round_optional(rows[0].gap_pct),
        )
    return GapPerspective(
        unidades=round_display(now.gap_units),
        pct_plan_diario=round_optional(now.gap_pct),
        en_ultimo_informe=at_report,
    )
