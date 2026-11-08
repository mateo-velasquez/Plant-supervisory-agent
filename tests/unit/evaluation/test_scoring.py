"""005 T8, T9 and T11: alert and news scoring with gating by capability (E11-E23, E32, E39)."""

from collections.abc import Sequence

import pytest

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import ActiveCaseRow, Notice, Reason, ShiftReport
from plant_monitor.evaluation.golden import Capability, GoldenSet
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.evaluation.results import ALERT_ERRORS, NEWS_ERRORS, Result, errors, tally
from plant_monitor.evaluation.scoring import score_alerts, score_news
from plant_monitor.evaluation.summary import evaluate

from eval_builders import (
    PB1,
    PB3,
    PB4,
    PL,
    SE3,
    SEL,
    SL2,
    SL5,
    alert,
    fixture_shifts,
    golden_alert,
    golden_news,
    golden_set,
    news,
    report,
    row,
    run_output,
)

COVERS = ("T01", "T02", "T03")
NO_CAPS: frozenset[Capability] = frozenset()
AGENT: frozenset[Capability] = frozenset({Capability.AGENT})
FU, OPEN, ESC, RES = CaseState.FOLLOW_UP, CaseState.OPEN, CaseState.ESCALATED, CaseState.RESOLVED
NONE, MED, HIGH, CRIT = Severity.NONE, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL


def _alerts(run: RunOutput, golden: GoldenSet, caps: frozenset[Capability] = NO_CAPS) -> tuple[Result, ...]:
    return score_alerts(run, golden, fixture_shifts(), caps)


def _news(run: RunOutput, golden: GoldenSet, caps: frozenset[Capability] = NO_CAPS) -> tuple[Result, ...]:
    return score_news(run, golden, caps)


def _alert_errors(results: Sequence[Result]) -> int:
    return errors(tally(results, gated=True), ALERT_ERRORS)


def _news_errors(results: Sequence[Result]) -> int:
    return errors(tally(results, gated=True), NEWS_ERRORS)


def _n(snapshot: str, case_id: str, estado: CaseState, sev: Severity, maxi: Severity | None = None) -> Notice:
    return news(snapshot, case_id, estado, sev, maxi)


def _report(turno: str, snapshot: str, items: Sequence[Notice] = ()) -> ShiftReport:
    rows: list[ActiveCaseRow] = [row(n.case_id, n.estado, n.severidad) for n in items if n.estado.is_active]
    return report(turno, snapshot, items, rows)


# --- alerts (T8) ---


def test_e11_alert_at_the_expected_snapshot_is_a_hit() -> None:
    results = _alerts(
        run_output([alert("S003", SEL)]), golden_set(COVERS, alerts=[golden_alert(SEL, "S003")])
    )
    assert tally(results, gated=True) == {"hit": 1}
    assert _alert_errors(results) == 0
    assert (results[0].label, results[0].case_id, results[0].where) == ("g.yaml#alerts[0]", SEL, "S003")


def test_e12_no_alert_for_an_expected_case_is_missing() -> None:
    results = _alerts(run_output(), golden_set(COVERS, alerts=[golden_alert(SEL, "S003")]))
    assert tally(results) == {"missing": 1}
    assert _alert_errors(results) == 1


def test_e13_alert_at_another_snapshot_is_one_wrong_snapshot_error() -> None:
    results = _alerts(
        run_output([alert("S004", SEL)]), golden_set(COVERS, alerts=[golden_alert(SEL, "S003")])
    )
    assert tally(results) == {"wrong_snapshot": 1}
    assert _alert_errors(results) == 1


@pytest.mark.parametrize(
    ("snapshots", "extra_alerts"), [(("S003", "S005"), 1), (("S003", "S004", "S005"), 2)]
)
def test_e14_further_alerts_for_the_case_are_duplicates(
    snapshots: tuple[str, ...], extra_alerts: int
) -> None:
    run = run_output([alert(s, SEL) for s in snapshots])
    results = _alerts(run, golden_set(COVERS, alerts=[golden_alert(SEL, "S003")]))
    assert tally(results) == {"duplicates": extra_alerts}
    assert _alert_errors(results) == extra_alerts


def test_e15a_alert_of_an_unexpected_case_in_scope_is_extra() -> None:
    other = alert("S004", SL2)
    run = run_output([alert("S003", SEL), other])
    results = _alerts(run, golden_set(COVERS, alerts=[golden_alert(SEL, "S003")]))
    assert tally(results) == {"hit": 1, "extra": 1}
    extra = next(r for r in results if "extra" in r.contributions)
    assert (extra.label, extra.case_id, extra.ref) == (None, SL2, "S004-alerta_inmediata-S002-SUV-Local")
    assert _alert_errors(results) == 1


def test_e15b_alert_outside_the_covered_shifts_is_unscored_not_an_error() -> None:
    run = run_output([alert("S003", SEL), alert("S005", SL2)])
    results = _alerts(run, golden_set(("T01", "T02"), alerts=[golden_alert(SEL, "S003")]))
    assert tally(results) == {"hit": 1, "unscored": 1}
    assert _alert_errors(results) == 0


def test_e16_case_opened_at_another_snapshot_is_missing_plus_extra() -> None:
    run = run_output([alert("S003", "S002-Sedán-Local")])
    results = _alerts(run, golden_set(COVERS, alerts=[golden_alert(SEL, "S003")]))
    assert tally(results) == {"missing": 1, "extra": 1}
    assert {r.case_id for r in results} == {SEL, "S002-Sedán-Local"}
    assert _alert_errors(results) == 2


def test_e17a_a_different_motivo_list_is_a_non_gating_mismatch() -> None:
    hit = alert("S003", SEL).model_copy(update={"motivo": (Reason.GAP, Reason.DELAY)})
    golden = golden_set(COVERS, alerts=[golden_alert(SEL, "S003", motivo=["gap"])])
    results = _alerts(run_output([hit]), golden)
    assert tally(results, gated=True) == {"hit": 1, "motivo_mismatch": 1}
    assert _alert_errors(results) == 0


def test_e17b_without_a_golden_motivo_nothing_is_compared() -> None:
    hit = alert("S003", SEL).model_copy(update={"motivo": (Reason.GAP, Reason.DELAY)})
    results = _alerts(run_output([hit]), golden_set(COVERS, alerts=[golden_alert(SEL, "S003")]))
    assert tally(results) == {"hit": 1}


# --- news (T9) ---

ESCALATED_NEWS = golden_news("T02", SEL, "escalado", "critica", "critica")


def test_e18a_escalation_at_close_hits_as_alert_and_as_news() -> None:
    golden = golden_set(("T02",), alerts=[golden_alert(SEL, "S004")], news=[ESCALATED_NEWS])
    run = run_output([alert("S004", SEL)], [_report("T02", "S004", [_n("S004", SEL, ESC, CRIT, CRIT)])])
    assert tally(_alerts(run, golden)) == {"hit": 1}
    assert tally(_news(run, golden)) == {"hit": 1}


def test_e18b_alert_without_the_news_item_misses_only_the_news() -> None:
    golden = golden_set(("T02",), alerts=[golden_alert(SEL, "S004")], news=[ESCALATED_NEWS])
    run = run_output([alert("S004", SEL)], [report("T02", "S004", [], [row(SEL, ESC, CRIT)])])
    assert tally(_alerts(run, golden)) == {"hit": 1}
    assert tally(_news(run, golden)) == {"missing": 1}


def test_e18c_news_item_without_the_alert_misses_only_the_alert() -> None:
    golden = golden_set(("T02",), alerts=[golden_alert(SEL, "S004")], news=[ESCALATED_NEWS])
    run = run_output([], [_report("T02", "S004", [_n("S004", SEL, ESC, CRIT, CRIT)])])
    assert tally(_alerts(run, golden)) == {"missing": 1}
    assert tally(_news(run, golden)) == {"hit": 1}


def test_e19_news_scoring_finds_hit_missing_and_extra() -> None:
    golden = golden_set(
        ("T01",),
        news=[
            golden_news("T01", SEL, "en_seguimiento", "alta", "alta"),
            golden_news("T01", PL, "en_seguimiento", "media", "media"),
        ],
    )
    run = run_output(
        [], [_report("T01", "S002", [_n("S002", SEL, FU, HIGH, HIGH), _n("S002", SL2, OPEN, HIGH, HIGH)])]
    )
    results = _news(run, golden)
    assert tally(results) == {"hit": 1, "missing": 1, "extra": 1}
    assert next(r for r in results if "missing" in r.contributions).case_id == PL
    extra = next(r for r in results if "extra" in r.contributions)
    assert (extra.case_id, extra.label, extra.where) == (SL2, None, "T01")
    assert _news_errors(results) == 2


def test_e20_attribute_differences_are_exact_and_never_errors() -> None:
    golden = golden_set(("T01",), news=[golden_news("T01", SEL, "en_seguimiento", "alta", "alta")])
    run = run_output([], [_report("T01", "S002", [_n("S002", SEL, OPEN, MED, HIGH)])])
    results = _news(run, golden)
    assert tally(results) == {"hit": 1, "estado_mismatch": 1, "severidad_mismatch": 1}
    assert _news_errors(results) == 0


PB_GOLDEN = [
    golden_news("T02", PB1, "resuelto", "ninguna", "ninguna"),
    golden_news("T02", PB4, "abierto", "media", "media"),
]


def test_e21a_two_cases_of_one_combination_both_hit() -> None:
    items = [_n("S004", PB1, RES, NONE, NONE), _n("S004", PB4, OPEN, MED, MED)]
    results = _news(run_output([], [_report("T02", "S004", items)]), golden_set(("T02",), news=PB_GOLDEN))
    assert tally(results) == {"hit": 2}


def test_e21b_only_the_new_case_leaves_the_resolved_one_missing() -> None:
    items = [_n("S004", PB4, OPEN, MED, MED)]
    results = _news(run_output([], [_report("T02", "S004", items)]), golden_set(("T02",), news=PB_GOLDEN))
    assert tally(results) == {"hit": 1, "missing": 1}
    assert next(r for r in results if "missing" in r.contributions).case_id == PB1


def test_e21c_the_wrong_case_of_the_combination_is_told_apart_by_abre_en() -> None:
    items = [_n("S004", PB1, OPEN, MED, MED), _n("S004", PB3, OPEN, MED, MED)]
    results = _news(run_output([], [_report("T02", "S004", items)]), golden_set(("T02",), news=PB_GOLDEN))
    counts = tally(results)
    assert (counts["hit"], counts["missing"], counts["extra"]) == (1, 1, 1)
    assert next(r for r in results if "missing" in r.contributions).case_id == PB4
    assert next(r for r in results if "extra" in r.contributions).case_id == PB3


T01_ITEM = golden_news("T01", SEL, "en_seguimiento", "alta", "alta")


def _t01_report() -> ShiftReport:
    return _report("T01", "S002", [_n("S002", SEL, FU, HIGH, HIGH)])


def test_e22a_covered_shift_without_a_report_is_a_missing_report() -> None:
    results = _news(run_output([], [_t01_report()]), golden_set(("T01", "T02"), news=[T01_ITEM]))
    assert tally(results) == {"hit": 1, "missing_report": 1}
    missing = next(r for r in results if "missing_report" in r.contributions)
    assert (missing.where, missing.label, missing.case_id) == ("T02", None, None)
    assert _news_errors(results) == 1


def test_e22b_covered_shift_with_an_empty_report_expecting_nothing_is_clean() -> None:
    run = run_output([], [_t01_report(), report("T02", "S004")])
    assert _news_errors(_news(run, golden_set(("T01", "T02"), news=[T01_ITEM]))) == 0


def test_e22c_unexpected_news_in_a_covered_shift_is_extra() -> None:
    reports = [_t01_report(), _report("T02", "S004", [_n("S004", SL2, FU, HIGH, HIGH)])]
    results = _news(run_output([], reports), golden_set(("T01", "T02"), news=[T01_ITEM]))
    assert tally(results) == {"hit": 1, "extra": 1}
    assert _news_errors(results) == 1


def test_e22d_no_reports_at_all_counts_every_covered_shift_and_item() -> None:
    results = _news(run_output(), golden_set(("T01", "T02"), news=[T01_ITEM]))
    assert tally(results) == {"missing_report": 2, "missing": 1}
    assert _news_errors(results) == 3


def test_e23_report_of_an_uncovered_shift_is_unscored_and_its_alerts_too() -> None:
    other = [_n("S004", SEL, FU, HIGH, HIGH), _n("S004", SL2, FU, HIGH, HIGH), _n("S004", PL, FU, MED, MED)]
    run = run_output([alert("S003", SEL)], [_t01_report(), _report("T02", "S004", other)])
    golden = golden_set(("T01",), news=[T01_ITEM])
    news_results = _news(run, golden)
    assert tally(news_results) == {"hit": 1, "unscored_report": 1}
    unscored = next(r for r in news_results if "unscored_report" in r.contributions)
    assert (unscored.where, unscored.case_id) == ("T02", None)
    assert _news_errors(news_results) == 0
    assert tally(_alerts(run, golden)) == {"unscored": 1}


# --- gating (T11) ---


def test_e32_depends_on_is_tracking_only_and_still_gates() -> None:
    golden = golden_set(
        ("T01", "T02"),
        alerts=[golden_alert(SEL, "S003")],
        news=[golden_news("T01", PB1, "en_seguimiento", "ninguna", "media", depends_on=["Q-26"])],
    )
    run = run_output([alert("S003", SEL)], [report("T01", "S002"), report("T02", "S004")])
    assert tally(_alerts(run, golden), gated=True) == {"hit": 1}
    results = _news(run, golden)
    assert tally(results, gated=True) == {"missing": 1}
    assert tally(results, question="Q-26") == {"missing": 1}
    assert results[0].depends_on == ("Q-26",)


def test_e32_variant_item_with_two_questions_counts_once_in_the_gated_tally() -> None:
    item = golden_news("T01", PB1, "en_seguimiento", "ninguna", "media", depends_on=["Q-17", "Q-26"])
    results = _news(run_output([], [report("T01", "S002")]), golden_set(("T01",), news=[item]))
    assert tally(results, gated=True) == {"missing": 1}
    assert tally(results, question="Q-17") == {"missing": 1}
    assert tally(results, question="Q-26") == {"missing": 1}


E39_GOLDEN = golden_set(
    ("T02", "T03"),
    alerts=[golden_alert(SE3, "S003", requires=["agent"])],
    news=[golden_news("T02", SE3, "escalado", "critica", "critica", requires=["agent"])],
)


def _e39_run() -> RunOutput:
    t02 = _report("T02", "S004", [_n("S004", SE3, FU, HIGH, HIGH)])
    t03 = _report("T03", "S006", [_n("S006", SE3, ESC, CRIT, CRIT), _n("S006", SL5, OPEN, MED, MED)])
    return run_output([alert("S005", SE3)], [t02, t03])


def test_e39a_unmet_requires_releases_the_item_and_extras_of_its_case_only() -> None:
    alerts, news_results = _alerts(_e39_run(), E39_GOLDEN), _news(_e39_run(), E39_GOLDEN)
    assert tally(alerts, gated=False) == {"wrong_snapshot": 1}
    assert tally(alerts, gated=True) == {}
    ungated = tally(news_results, gated=False)
    assert ungated == {
        "hit": 1,
        "estado_mismatch": 1,
        "severidad_mismatch": 1,
        "maxima_mismatch": 1,
        "extra": 1,
    }
    extras = {r.case_id: r.gated for r in news_results if "extra" in r.contributions}
    assert extras == {SE3: False, SL5: True}
    assert tally(news_results, gated=True) == {"extra": 1}


def test_e39b_with_the_capability_every_result_gates() -> None:
    alerts, news_results = _alerts(_e39_run(), E39_GOLDEN, AGENT), _news(_e39_run(), E39_GOLDEN, AGENT)
    assert tally(alerts, gated=False) == {} == tally(news_results, gated=False)
    assert _alert_errors(alerts) == 1
    assert tally(news_results, gated=True)["extra"] == 2


@pytest.mark.parametrize(("caps", "expected"), [(NO_CAPS, 1), (AGENT, 3)])
def test_e39_gating_errors_through_evaluate(caps: frozenset[Capability], expected: int) -> None:
    summary = evaluate(
        _e39_run(), E39_GOLDEN, fixture_shifts(), capabilities=caps, registry="r", golden_dir="g"
    )
    assert summary.gating_errors == expected


def test_extra_alert_of_a_case_with_unmet_news_is_not_gated() -> None:
    """The release covers every golden item type of the case (plan: alert, news and cause items)."""
    golden = golden_set(
        ("T02",), news=[golden_news("T02", SE3, "escalado", "critica", "critica", requires=["agent"])]
    )
    results = _alerts(run_output([alert("S003", SE3)]), golden)
    assert tally(results, gated=False) == {"extra": 1}
    assert tally(results, gated=True) == {}
