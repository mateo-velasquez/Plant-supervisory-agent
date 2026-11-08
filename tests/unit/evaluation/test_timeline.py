"""005 T12: 'CaseTimeline' and 'case_timeline' (E35)."""

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.enums import Severity
from plant_monitor.evaluation.timeline import CaseTimeline, case_timeline

from eval_builders import PB1, SEL, alert, news, report, row, run_output


def test_e35_case_timeline_lists_first_report_alerts_and_resolution() -> None:
    t01 = report(
        "T01",
        "S002",
        (
            news("S002", SEL, CaseState.FOLLOW_UP, Severity.HIGH),
            news("S002", PB1, CaseState.FOLLOW_UP, Severity.NONE, Severity.MEDIUM),
        ),
        (row(SEL, severidad=Severity.HIGH), row(PB1, severidad=Severity.NONE, maxima=Severity.MEDIUM)),
    )
    t02 = report(
        "T02",
        "S004",
        (
            news("S004", SEL, CaseState.ESCALATED, Severity.CRITICAL),
            news("S004", PB1, CaseState.RESOLVED, Severity.NONE),
        ),
        (row(SEL, CaseState.ESCALATED, Severity.CRITICAL),),
    )
    run = run_output([alert("S003", SEL)], [t01, t02])

    assert case_timeline(run) == (
        CaseTimeline(SEL, first_reported_in="T01", alerted_at=("S003",), resolved_in=None),
        CaseTimeline(PB1, first_reported_in="T01", alerted_at=(), resolved_in="T02"),
    )


def test_a_case_that_was_alerted_but_never_reported_has_no_first_report() -> None:
    """Guards the 'None' branch of 'first_reported_in' declared in the plan's dataclass."""
    run = run_output([alert("S003", SEL)], [report("T01", "S002")])
    assert case_timeline(run) == (
        CaseTimeline(SEL, first_reported_in=None, alerted_at=("S003",), resolved_in=None),
    )
