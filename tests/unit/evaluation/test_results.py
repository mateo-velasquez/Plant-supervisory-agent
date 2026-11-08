"""005 T8: 'Result', 'tally' and 'errors' (Q-34, Q-35)."""

from plant_monitor.evaluation.results import ALERT_ERRORS, NEWS_ERRORS, Result, Section, errors, tally


def _result(contributions: dict[str, int], *, gated: bool = True, depends_on: tuple[str, ...] = ()) -> Result:
    return Result(
        section=Section.NEWS,
        label="g.yaml#news[0]",
        case_id="S001-Sedán-Local",
        where="T01",
        contributions=contributions,
        depends_on=depends_on,
        gated=gated,
    )


def test_tally_sums_contributions_over_every_result_without_filters() -> None:
    results = [_result({"hit": 1, "estado_mismatch": 1}), _result({"missing": 1}), _result({"hit": 1})]
    assert tally(results) == {"hit": 2, "estado_mismatch": 1, "missing": 1}


def test_tally_filters_by_gated_flag() -> None:
    results = [_result({"missing": 1}), _result({"missing": 1, "hit": 1}, gated=False)]
    assert tally(results, gated=True) == {"missing": 1}
    assert tally(results, gated=False) == {"missing": 1, "hit": 1}


def test_tally_filters_by_question_and_counts_a_result_once_per_question() -> None:
    results = [_result({"missing": 1}, depends_on=("Q-17", "Q-26")), _result({"missing": 1})]
    assert tally(results, question="Q-26") == {"missing": 1}
    assert tally(results, question="Q-17") == {"missing": 1}
    assert tally(results, gated=True) == {"missing": 2}


def test_errors_sums_only_the_given_keys() -> None:
    counts = {"hit": 4, "missing": 1, "extra": 2, "motivo_mismatch": 3}
    assert errors(counts, ALERT_ERRORS) == 3
    assert errors({}, NEWS_ERRORS) == 0


def test_error_keys_match_the_spec() -> None:
    assert {"missing", "wrong_snapshot", "duplicates", "extra"} == ALERT_ERRORS
    assert {"missing", "extra", "missing_report"} == NEWS_ERRORS
