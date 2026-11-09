"""Cause scoring against the golden set: category, stage and run evidence of each target notice (008, R19)."""

from collections import Counter
from collections.abc import Mapping, Sequence

from plant_monitor.domain.calendar import calendar_order, closed_shifts
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.models import Shift
from plant_monitor.domain.notices import Notice, NoticeType
from plant_monitor.domain.verbatim import contains_verbatim
from plant_monitor.evaluation.golden import Capability, ExpectedCause, GoldenSet, Labeled
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.evaluation.results import Result, Section
from plant_monitor.evaluation.scoring import is_gated


def score_causes(
    run: RunOutput,
    golden: GoldenSet,
    shifts: Sequence[Shift],
    logbooks: Mapping[str, str],
    capabilities: frozenset[Capability],
) -> tuple[Result, ...]:
    """One result per golden cause: 'target_missing', or the mismatch and evidence errors, or 'hit'."""
    closings = {shift.turno_id: shift.snapshot_cierre for shift in calendar_order(shifts)}
    results: list[Result] = []
    for labeled in golden.causes:
        item = labeled.item
        where = _where(labeled, golden, closings)
        target = _target(labeled, run, golden)
        results.append(
            Result(
                Section.CAUSES,
                labeled.label,
                item.case.case_id,
                where,
                _contributions(item, target, shifts, logbooks),
                item.depends_on,
                gated=is_gated(item, capabilities),
            )
        )
    return tuple(results)


def cited_logbooks(run: RunOutput, golden: GoldenSet) -> frozenset[str]:
    """Logbook ids cited by the target notices of the golden causes."""
    return frozenset(
        evidence.bitacora
        for labeled in golden.causes
        if (target := _target(labeled, run, golden)) is not None
        for evidence in target.evidencia
    )


def _expected_snapshot(labeled: Labeled[ExpectedCause], golden: GoldenSet) -> str | None:
    """Snapshot of the golden alert of the cause's case, or None when there is none."""
    case_id = labeled.item.case.case_id
    return next((a.item.snapshot_id for a in golden.alerts if a.item.case.case_id == case_id), None)


def _where(labeled: Labeled[ExpectedCause], golden: GoldenSet, closings: Mapping[str, str]) -> str:
    """Target snapshot: the golden alert's, or the closing snapshot of the news shift."""
    item = labeled.item
    if item.turno_id is not None:
        return closings[item.turno_id]
    return _expected_snapshot(labeled, golden) or ""


def _target(labeled: Labeled[ExpectedCause], run: RunOutput, golden: GoldenSet) -> Notice | None:
    """The run alert (at the expected snapshot if several) or the news item the cause is scored on."""
    item = labeled.item
    case_id = item.case.case_id
    if item.notice is NoticeType.SHIFT_REPORT:
        report = next((r for r in run.reports if r.turno_id == item.turno_id), None)
        if report is None:
            return None
        return next((n for n in report.novedades if n.case_id == case_id), None)
    alerts = [alert for alert in run.alerts if alert.case_id == case_id]
    expected = _expected_snapshot(labeled, golden)
    at_snapshot = [alert for alert in alerts if alert.snapshot_id == expected]
    chosen = at_snapshot or alerts
    return chosen[0] if chosen else None


def _contributions(
    item: ExpectedCause,
    target: Notice | None,
    shifts: Sequence[Shift],
    logbooks: Mapping[str, str],
) -> dict[str, int]:
    """Error counts of one cause against its target, or '{hit: 1}'."""
    if target is None:
        return {"target_missing": 1}
    errors: Counter[str] = Counter()
    if target.causa.categoria is not item.categoria:
        errors["categoria_mismatch"] += 1
    if target.causa.etapa is not item.etapa:
        errors["etapa_mismatch"] += 1
    if target.causa.categoria is not CauseCategory.UNDECLARED and not target.evidencia:
        errors["evidence_missing"] += 1
    available = {shift.turno_id for shift in closed_shifts(shifts, target.snapshot_id)}
    for evidence in target.evidencia:
        text = logbooks.get(evidence.bitacora)
        if text is None:
            errors["evidence_not_loaded"] += 1
        elif evidence.bitacora not in available:
            errors["evidence_not_available"] += 1
        elif not contains_verbatim(text, evidence.fragmento):
            errors["evidence_not_verbatim"] += 1
    return dict(errors) or {"hit": 1}
