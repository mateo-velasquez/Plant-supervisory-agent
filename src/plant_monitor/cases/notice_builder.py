"""Per-snapshot notice decisions: 'motivo', 'origen', default cause, case notices (FR-21 to FR-25)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from plant_monitor.cases.facts import CaseFacts
from plant_monitor.cases.novelty import active_rows, alerts_for, case_order, news_reasons, report_set
from plant_monitor.cases.templates import alert_text, news_text, silent_text
from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.causes import Cause, CauseCategory, CitedCause
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics
from plant_monitor.domain.notices import (
    Notice,
    NoticeType,
    Origin,
    Reason,
    ShiftReport,
    notice_id_for,
)

if TYPE_CHECKING:
    from plant_monitor.cases.tracker import CaseDelta


def reasons_for(facts: CaseFacts) -> tuple[Reason, ...]:
    """Triggers at the case's effective severity, ordered gap, retraso, bitacora (Q-31)."""
    case = facts.case
    effective = case.current_severity
    if effective is Severity.NONE:
        return ()
    current = facts.current
    if current is None:
        raise ValueError(f"{case.case_id}: current metrics are needed for 'motivo'")
    reasons: list[Reason] = []
    if current.gap_severity == effective:
        reasons.append(Reason.GAP)
    if current.delay_severity == effective:
        reasons.append(Reason.DELAY)
    if case.raised and case.minimum_severity < Severity.CRITICAL:
        reasons.append(Reason.LOGBOOK)
    return tuple(reasons)


def origin_for(motivo: tuple[Reason, ...]) -> Origin:
    """'agente' if and only if the logbook raise was necessary."""
    return Origin.AGENT if Reason.LOGBOOK in motivo else Origin.THRESHOLD


def default_cause(stage: Stage | None) -> Cause:
    """The 'no_declarada' cause (§6, Q-17); the stage is never guessed."""
    return Cause(categoria=CauseCategory.UNDECLARED, etapa=stage)


def case_notice(tipo: NoticeType, facts: CaseFacts, snapshot_id: str) -> Notice:
    """Per-case notice of type 'tipo'; ValueError when the type contradicts the rules."""
    case = facts.case
    reasons = news_reasons(case)
    if tipo is NoticeType.ALERT and facts.current is None:
        raise ValueError(f"{case.case_id}: an alert needs current metrics")
    if tipo is NoticeType.SHIFT_REPORT and not reasons:
        raise ValueError(f"{case.case_id}: not news, it cannot be an informe_de_turno")
    if tipo is NoticeType.NO_NOTICE and reasons:
        raise ValueError(f"{case.case_id}: it is news, it cannot be sin_aviso")
    peak = case.max_severity_since_report
    if peak is None:
        raise ValueError(f"{case.case_id}: a notice needs a max severity")
    motivo = reasons_for(facts)
    cited = facts.cited
    cause = default_cause(facts.cause_stage) if cited is None else cited.cause
    if tipo is NoticeType.ALERT:
        text = alert_text(facts, snapshot_id, motivo, cause)
    elif tipo is NoticeType.SHIFT_REPORT:
        text = news_text(facts, reasons, cause)
    else:
        text = silent_text(case)
    return Notice(
        notice_id=notice_id_for(snapshot_id, tipo, case.case_id),
        snapshot_id=snapshot_id,
        case_id=case.case_id,
        modelo=case.combination.modelo,
        mercado=case.combination.mercado,
        tipo=tipo,
        severidad=case.current_severity,
        severidad_maxima=peak,
        estado=case.state,
        origen=origin_for(motivo),
        motivo=motivo,
        causa=cause,
        evidencia=() if cited is None else (cited.evidence,),
        texto=text,
    )


@dataclass(frozen=True)
class ShiftClose:
    """Closing-snapshot input: the shift and the registry's resolved-unreported cases, unfiltered."""

    turno_id: str
    resolved_unreported: tuple[Case, ...]


@dataclass(frozen=True)
class SnapshotNotices:
    """Everything one snapshot decides."""

    decisions: tuple[Notice, ...]  # alerts first, then one non-alert decision per case in case_order
    report: ShiftReport | None  # only at a closing snapshot
    to_mark: tuple[str, ...]  # the report set, in case_order; empty at a mid snapshot


def _facts(
    case: Case,
    current: CombinationMetrics | None,
    cause_rows: Mapping[str, CaseHistoryRow],
    cited: Mapping[str, CitedCause],
) -> CaseFacts:
    row = cause_rows.get(case.case_id)
    if row is None:
        raise ValueError(f"{case.case_id}: no cause row")
    return CaseFacts(case, current, row, cited=cited.get(case.case_id))


def build_snapshot_notices(
    delta: CaseDelta,
    metrics: Mapping[Combination, CombinationMetrics],
    cause_rows: Mapping[str, CaseHistoryRow],
    close: ShiftClose | None,
    cited: Mapping[str, CitedCause] | None = None,
) -> SnapshotNotices:
    """Decisions of one snapshot from its last delta, and the report at a closing snapshot."""
    sid = delta.snapshot_id
    cited = {} if cited is None else cited
    facts: dict[str, CaseFacts] = {}
    for case in delta.cases:
        current = metrics.get(case.combination)
        if current is None:
            raise ValueError(f"{case.case_id}: no metrics at {sid}")
        facts[case.case_id] = _facts(case, current, cause_rows, cited)
    alerts = alerts_for(delta, metrics)
    alerted = {case.case_id for case in alerts}
    decisions = [case_notice(NoticeType.ALERT, facts[case.case_id], sid) for case in alerts]

    targets = delta.cases if close is None else report_set(delta.cases, close.resolved_unreported)
    news: list[Notice] = []
    for case in sorted(targets, key=case_order):
        if close is None and case.case_id in alerted:
            continue
        target = facts.get(case.case_id) or _facts(case, None, cause_rows, cited)
        tipo = NoticeType.SHIFT_REPORT if news_reasons(case) else NoticeType.NO_NOTICE
        if tipo is NoticeType.NO_NOTICE and case.case_id in alerted:
            raise ValueError(f"{case.case_id}: alerted at {sid}, it cannot be sin_aviso (Q-14)")
        notice = case_notice(tipo, target, sid)
        decisions.append(notice)
        if tipo is NoticeType.SHIFT_REPORT:
            news.append(notice)
    if close is None:
        return SnapshotNotices(tuple(decisions), None, ())
    active = [case for case in delta.cases if case.state.is_active]
    report = ShiftReport(
        turno_id=close.turno_id,
        snapshot_id=sid,
        novedades=tuple(news),
        casos_activos=active_rows(active, metrics),
    )
    return SnapshotNotices(
        tuple(decisions), report, tuple(case.case_id for case in sorted(targets, key=case_order))
    )
