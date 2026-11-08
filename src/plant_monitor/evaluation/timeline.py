"""Case timeline digest of a run: first report, alerts and resolution per case (005, E35)."""

from collections.abc import Iterator
from dataclasses import dataclass

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.notices import ShiftReport
from plant_monitor.evaluation.output import RunOutput

# (snapshot_id, 0 for alerts or 1 for report entries, position in the run, step): calendar (snapshot) order.
type _Key = tuple[str, int, int, int]


@dataclass(frozen=True)
class CaseTimeline:
    """What one case did in the run: where it was first reported, alerted and resolved."""

    case_id: str
    first_reported_in: str | None
    alerted_at: tuple[str, ...]
    resolved_in: str | None


def case_timeline(run: RunOutput) -> tuple[CaseTimeline, ...]:
    """One entry per case, ordered by first appearance in calendar (snapshot) order, then by 'case_id'."""
    first: dict[str, _Key] = {}
    for key, case_id in _appearances(run):
        if case_id not in first or key < first[case_id]:
            first[case_id] = key
    ordered = sorted(first, key=lambda case_id: (first[case_id], case_id))
    return tuple(
        CaseTimeline(
            case_id=case_id,
            first_reported_in=next((r.turno_id for r in run.reports if case_id in _listed_cases(r)), None),
            alerted_at=tuple(a.snapshot_id for a in run.alerts if a.case_id == case_id),
            resolved_in=next(
                (
                    r.turno_id
                    for r in run.reports
                    if any(n.case_id == case_id and n.estado is CaseState.RESOLVED for n in r.novedades)
                ),
                None,
            ),
        )
        for case_id in ordered
    )


def _appearances(run: RunOutput) -> Iterator[tuple[_Key, str]]:
    """Every case mention keyed by snapshot; alerts first within a snapshot, entries in listed order."""
    for index, alert in enumerate(run.alerts):
        yield (alert.snapshot_id, 0, index, 0), alert.case_id
    for index, report in enumerate(run.reports):
        for step, case_id in enumerate(_listed_cases(report)):
            yield (report.snapshot_id, 1, index, step), case_id


def _listed_cases(report: ShiftReport) -> list[str]:
    """Case ids a report lists, in order: its news first, then its active rows."""
    return [*(news.case_id for news in report.novedades), *(row.case_id for row in report.casos_activos)]
