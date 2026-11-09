"""Alert and news scoring against the golden set, gated by capability (005, Q-34, Q-35)."""

from collections.abc import Iterator, Sequence

from plant_monitor.domain.models import Shift
from plant_monitor.domain.notices import Notice
from plant_monitor.evaluation.golden import (
    Capability,
    CaseKey,
    ExpectedAlert,
    ExpectedNews,
    GoldenItem,
    GoldenSet,
    Labeled,
)
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.evaluation.results import Result, Section


def score_alerts(
    run: RunOutput, golden: GoldenSet, shifts: Sequence[Shift], capabilities: frozenset[Capability]
) -> tuple[Result, ...]:
    """Results of the expected alerts, then of the run alerts no expected alert matches."""
    scope = _scope(golden.covered_shifts, shifts)
    unmet = _unmet_cases(golden, capabilities)
    by_case: dict[str, list[Notice]] = {}
    for alert in run.alerts:
        by_case.setdefault(alert.case_id, []).append(alert)
    results = [
        _expected_alert(labeled, by_case.get(labeled.item.case.case_id, []), capabilities)
        for labeled in golden.alerts
    ]
    expected_cases = {labeled.item.case.case_id for labeled in golden.alerts}
    for alert in run.alerts:
        if alert.case_id in expected_cases:
            continue
        key = "extra" if alert.snapshot_id in scope else "unscored"
        results.append(
            Result(
                Section.ALERTS,
                None,
                alert.case_id,
                alert.snapshot_id,
                {key: 1},
                gated=alert.case_id not in unmet,
                ref=alert.notice_id,
            )
        )
    return tuple(results)


def score_news(run: RunOutput, golden: GoldenSet, capabilities: frozenset[Capability]) -> tuple[Result, ...]:
    """News results of every covered shift, then one result per uncovered report."""
    unmet = _unmet_cases(golden, capabilities)
    reports = {report.turno_id: report for report in run.reports}
    results: list[Result] = []
    for turno in golden.covered_shifts:
        expected = [labeled for labeled in golden.news if labeled.item.turno_id == turno]
        report = reports.get(turno)
        if report is None:
            results.append(Result(Section.NEWS, None, None, turno, {"missing_report": 1}))
            results.extend(_expected_news(labeled, None, capabilities) for labeled in expected)
            continue
        actual = {news.case_id: news for news in report.novedades}
        expected_cases = {labeled.item.case.case_id for labeled in expected}
        results.extend(
            _expected_news(labeled, actual.get(labeled.item.case.case_id), capabilities)
            for labeled in expected
        )
        for case_id in actual:
            if case_id not in expected_cases:
                results.append(
                    Result(Section.NEWS, None, case_id, turno, {"extra": 1}, gated=case_id not in unmet)
                )
    covered = set(golden.covered_shifts)
    results.extend(
        Result(Section.NEWS, None, None, report.turno_id, {"unscored_report": 1})
        for report in run.reports
        if report.turno_id not in covered
    )
    return tuple(results)


def _expected_alert(
    labeled: Labeled[ExpectedAlert], found: Sequence[Notice], capabilities: frozenset[Capability]
) -> Result:
    """Hit, missing, wrong snapshot or duplicates for one expected alert; 'found' is its case's alerts."""
    item = labeled.item
    at_snapshot = [alert for alert in found if alert.snapshot_id == item.snapshot_id]
    contributions: dict[str, int]
    if not found:
        contributions = {"missing": 1}
    elif not at_snapshot:
        contributions = {"wrong_snapshot": 1}
    elif len(found) == 1:
        contributions = {"hit": 1}
        if item.motivo is not None and item.motivo != at_snapshot[0].motivo:
            contributions["motivo_mismatch"] = 1
    else:
        contributions = {"duplicates": len(found) - 1}
    return Result(
        Section.ALERTS,
        labeled.label,
        item.case.case_id,
        item.snapshot_id,
        contributions,
        item.depends_on,
        gated=is_gated(item, capabilities),
    )


def _expected_news(
    labeled: Labeled[ExpectedNews], actual: Notice | None, capabilities: frozenset[Capability]
) -> Result:
    """Hit with exact attribute mismatches, or missing when 'actual' is None."""
    item = labeled.item
    contributions: dict[str, int]
    if actual is None:
        contributions = {"missing": 1}
    else:
        contributions = {"hit": 1}
        if actual.estado is not item.estado:
            contributions["estado_mismatch"] = 1
        if actual.severidad is not item.severidad:
            contributions["severidad_mismatch"] = 1
        if actual.severidad_maxima is not item.severidad_maxima:
            contributions["maxima_mismatch"] = 1
    return Result(
        Section.NEWS,
        labeled.label,
        item.case.case_id,
        item.turno_id,
        contributions,
        item.depends_on,
        gated=is_gated(item, capabilities),
    )


def is_gated(item: GoldenItem, capabilities: frozenset[Capability]) -> bool:
    """True when every capability the item requires is available."""
    return frozenset(item.requires) <= capabilities


def _unmet_cases(golden: GoldenSet, capabilities: frozenset[Capability]) -> frozenset[str]:
    """Case ids with any golden item whose 'requires' the capabilities do not meet (E39)."""
    return frozenset(case.case_id for case, item in _keyed_items(golden) if not is_gated(item, capabilities))


def _keyed_items(golden: GoldenSet) -> Iterator[tuple[CaseKey, GoldenItem]]:
    """Every golden item of every section, with its case."""
    for labeled_alert in golden.alerts:
        yield labeled_alert.item.case, labeled_alert.item
    for labeled_news in golden.news:
        yield labeled_news.item.case, labeled_news.item
    for labeled_cause in golden.causes:
        yield labeled_cause.item.case, labeled_cause.item


def _scope(covered: Sequence[str], shifts: Sequence[Shift]) -> frozenset[str]:
    """Mid and closing snapshots of the covered shifts."""
    by_id = {shift.turno_id: shift for shift in shifts}
    return frozenset(
        snapshot
        for turno in covered
        for snapshot in (by_id[turno].snapshot_medio, by_id[turno].snapshot_cierre)
    )
