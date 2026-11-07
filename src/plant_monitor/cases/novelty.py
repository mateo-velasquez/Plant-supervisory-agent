"""Alerts, news (novelty), the report set and active rows; pure, shared with spec 010's hooks."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from plant_monitor.domain.cases import Case, CaseEvent, CaseState
from plant_monitor.domain.models import Combination, CombinationMetrics, all_combinations
from plant_monitor.domain.notices import ActiveCaseRow

if TYPE_CHECKING:
    from plant_monitor.cases.tracker import CaseDelta


class NewsReason(StrEnum):
    """Why a case is news (§4); declaration order is list order; not part of the contract."""

    NEW = "new"
    RESOLVED = "resolved"
    STATE_CHANGED = "state_changed"
    SEVERITY_CHANGED = "severity_changed"
    PEAK = "peak"


@dataclass(frozen=True)
class NewsItem:
    """A news case with its reasons."""

    case: Case
    reasons: tuple[NewsReason, ...]  # never empty


def case_order(case: Case) -> tuple[int, str]:
    """Sort key: 'all_combinations()' index, then 'opened_at'."""
    return all_combinations().index(case.combination), case.opened_at


def alerted_case_ids(delta: CaseDelta) -> tuple[str, ...]:
    """IDs of the cases with an 'escalated' event, in delta event order."""
    return tuple(e.case_id for e in delta.events if e.event is CaseEvent.ESCALATED)


def alerts_for(delta: CaseDelta, metrics: Mapping[Combination, CombinationMetrics]) -> tuple[Case, ...]:
    """The alerted cases themselves; each must have metrics."""
    by_id = {case.case_id: case for case in delta.cases}
    alerted: list[Case] = []
    for case_id in alerted_case_ids(delta):
        case = by_id.get(case_id)
        if case is None:
            raise ValueError(f"alerted case {case_id} is not in the delta of {delta.snapshot_id}")
        if case.combination not in metrics:
            raise ValueError(f"alerted case {case_id} has no metrics at {delta.snapshot_id}")
        alerted.append(case)
    return tuple(alerted)


def _norm(state: CaseState | None) -> CaseState | None:
    """'abierto' and 'en_seguimiento' count as one state (§4)."""
    return CaseState.FOLLOW_UP if state is CaseState.OPEN else state


def news_reasons(case: Case) -> tuple[NewsReason, ...]:
    """Every §4 reason that makes the case news against its last report, in 'NewsReason' order."""
    reasons: list[NewsReason] = []
    reported = case.last_reported_at is not None
    if not reported:
        reasons.append(NewsReason.NEW)
    if case.state is CaseState.RESOLVED and case.last_reported_state is not CaseState.RESOLVED:
        reasons.append(NewsReason.RESOLVED)
    if reported and case.state.is_active and _norm(case.state) != _norm(case.last_reported_state):
        reasons.append(NewsReason.STATE_CHANGED)
    if reported and case.current_severity != case.last_reported_severity:
        reasons.append(NewsReason.SEVERITY_CHANGED)
    peak = case.max_severity_since_report
    if peak is not None and peak > case.current_severity:
        reasons.append(NewsReason.PEAK)
    return tuple(reasons)


def expected_news(cases: Iterable[Case]) -> tuple[NewsItem, ...]:
    """One 'NewsItem' per news case, in 'case_order'."""
    items = [NewsItem(case, reasons) for case in cases if (reasons := news_reasons(case))]
    return tuple(sorted(items, key=lambda item: case_order(item.case)))


def report_set(evaluated: Iterable[Case], resolved_unreported: Iterable[Case]) -> tuple[Case, ...]:
    """Cases a closing report covers: evaluated plus resolved-unreported, the evaluated version winning."""
    merged: dict[str, Case] = {}
    for case in resolved_unreported:
        if case.state is not CaseState.RESOLVED or case.last_reported_state is CaseState.RESOLVED:
            raise ValueError(f"{case.case_id} is not resolved-unreported")
        merged[case.case_id] = case
    for case in evaluated:
        merged[case.case_id] = case
    return tuple(sorted(merged.values(), key=case_order))


def active_rows(
    cases: Iterable[Case], metrics: Mapping[Combination, CombinationMetrics]
) -> tuple[ActiveCaseRow, ...]:
    """One row per active case, in 'case_order', with the current snapshot's values."""
    rows: list[ActiveCaseRow] = []
    for case in sorted(cases, key=case_order):
        current = metrics.get(case.combination)
        if not case.state.is_active:
            raise ValueError(f"{case.case_id} is resolved and cannot be an active row")
        if current is None:
            raise ValueError(f"active case {case.case_id} has no metrics")
        if case.max_severity_since_report is None:
            raise ValueError(f"active case {case.case_id} has an empty max severity")
        rows.append(
            ActiveCaseRow(
                case_id=case.case_id,
                modelo=case.combination.modelo,
                mercado=case.combination.mercado,
                gap_unidades=current.gap_units,
                gap_pct=current.gap_pct,
                retraso_dias=current.delay_days,
                severidad=case.current_severity,
                severidad_maxima=case.max_severity_since_report,
                estado=case.state,
                etapa_cuello=current.bottleneck,
            )
        )
    return tuple(rows)
