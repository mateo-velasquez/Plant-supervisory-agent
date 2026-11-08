"""005 T10: 'count_noise', repeated news and duplicate alerts without golden data (E24-E26)."""

import pytest

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.evaluation.noise import NoiseScore, RepeatedNews, count_noise

from eval_builders import PB1, PL, SE3, SEL, SL2, alert, news, report, row, run_output

OPEN, FU, ESC, RES = CaseState.OPEN, CaseState.FOLLOW_UP, CaseState.ESCALATED, CaseState.RESOLVED
NONE, MED, HIGH, CRIT = Severity.NONE, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL


def test_e24_repeat_treats_abierto_and_en_seguimiento_as_one_state() -> None:
    r1 = report("T01", "S002", [], [row(SL2, OPEN, HIGH)])
    r2 = report("T02", "S004", [news("S004", SL2, FU, HIGH, HIGH)], [row(SL2, FU, HIGH)])
    score = count_noise(run_output([], [r1, r2]))
    assert score.repeats == (RepeatedNews("T02", SL2, "T01"),)
    assert score.errors == 1


def _r1() -> ShiftReport:
    return report("T01", "S002", [], [row(SEL, FU, HIGH), row(PL, FU, MED), row(PB1, FU, NONE)])


@pytest.mark.parametrize(
    "variant",
    [
        pytest.param(news("S004", SEL, ESC, CRIT, CRIT), id="a-state-change"),
        pytest.param(news("S004", PL, FU, HIGH, HIGH), id="b-severity-change"),
        pytest.param(news("S004", PL, FU, MED, HIGH), id="c-peak"),
        pytest.param(news("S004", "S003-SUV-Local", OPEN, MED, MED), id="d-new-case"),
        pytest.param(news("S004", PB1, RES, NONE, NONE), id="e-resolved"),
    ],
)
def test_e25_each_change_makes_the_news_a_non_repeat(variant: Notice) -> None:
    r2 = report("T02", "S004", [variant])
    assert count_noise(run_output([], [_r1(), r2])).repeats == ()


def test_e25f_the_first_report_is_never_compared() -> None:
    r1 = report("T01", "S002", [news("S002", SEL, FU, HIGH, HIGH)], [row(SEL, FU, HIGH)])
    assert count_noise(run_output([], [r1])).repeats == ()


def test_e25g_each_report_is_compared_only_with_the_one_before() -> None:
    r1 = report("T01", "S002", [], [row(SL2, FU, HIGH)])
    r2 = report("T02", "S004", [news("S004", SL2, FU, MED, MED)], [row(SL2, FU, MED)])
    r3 = report("T03", "S006", [news("S006", SL2, FU, HIGH, HIGH)], [row(SL2, FU, HIGH)])
    assert count_noise(run_output([], [r1, r2, r3])).repeats == ()


def test_e26_duplicate_alerts_are_reported_but_are_not_noise_errors() -> None:
    run = run_output([alert("S003", SEL), alert("S005", SEL), alert("S004", PL)])
    assert count_noise(run) == NoiseScore(repeats=(), duplicate_alerts=((SEL, 2),))
    assert count_noise(run).errors == 0


def test_alerts_of_other_cases_do_not_count_as_duplicates() -> None:
    """Guards the grouping key: one alert per case, even for one combination at two snapshots."""
    run = run_output([alert("S003", SEL), alert("S004", SE3)])
    assert count_noise(run).duplicate_alerts == ()
