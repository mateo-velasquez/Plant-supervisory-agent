"""Pure case lifecycle of criterio.md §3: transitions, clean streak and max severity since report."""

from dataclasses import dataclass
from typing import Any

from plant_monitor.domain.cases import (
    Case,
    CaseEvent,
    CaseHistoryRow,
    CaseState,
    case_id_for,
    effective_severity,
)
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.models import CombinationMetrics
from plant_monitor.metrics.thresholds import ResolutionThresholds


@dataclass(frozen=True)
class Observation:
    """One combination at one snapshot, as the lifecycle sees it."""

    snapshot_id: str
    metrics: CombinationMetrics
    raised: bool


@dataclass(frozen=True)
class Step:
    """Result of evaluating one case at one snapshot."""

    case: Case
    history: CaseHistoryRow
    events: tuple[CaseEvent, ...]


def next_state(current: CaseState | None, *, critical: bool, resolvable: bool) -> CaseState:
    """§3 transition table; None means opening (Q-08); ValueError from RESOLVED."""
    match current:
        case CaseState.RESOLVED:
            raise ValueError("a resolved case is final and cannot transition")
        case _ if resolvable:
            return CaseState.RESOLVED
        case CaseState.ESCALATED:
            return CaseState.ESCALATED
        case _ if critical:
            return CaseState.ESCALATED
        case None:
            return CaseState.OPEN
        case _:
            return CaseState.FOLLOW_UP


def _history_row(case: Case, obs: Observation) -> CaseHistoryRow:
    metrics = obs.metrics
    return CaseHistoryRow(
        case_id=case.case_id,
        snapshot_id=obs.snapshot_id,
        state=case.state,
        minimum_severity=case.minimum_severity,
        raised=case.raised,
        gap_units=metrics.gap_units,
        gap_pct=metrics.gap_pct,
        delay_days=metrics.delay_days,
        bottleneck=metrics.bottleneck,
        clean_streak=case.clean_streak,
    )


def _open(obs: Observation) -> Step | None:
    if not obs.metrics.has_deviation:
        return None
    minimum = obs.metrics.minimum_severity
    eff = effective_severity(minimum, obs.raised)
    state = next_state(None, critical=eff is Severity.CRITICAL, resolvable=False)
    case = Case(
        case_id=case_id_for(obs.snapshot_id, obs.metrics.combination),
        combination=obs.metrics.combination,
        opened_at=obs.snapshot_id,
        state=state,
        minimum_severity=minimum,
        raised=obs.raised,
        max_severity_since_report=eff,
        clean_streak=0,
        last_snapshot_id=obs.snapshot_id,
    )
    events = (CaseEvent.OPENED, CaseEvent.ESCALATED) if state is CaseState.ESCALATED else (CaseEvent.OPENED,)
    return Step(case=case, history=_history_row(case, obs), events=events)


def step(case: Case | None, obs: Observation, resolution: ResolutionThresholds) -> Step | None:
    """Open, advance an active case, or None; ValueError on a resolved or already-evaluated case."""
    if case is None:
        return _open(obs)
    if case.state is CaseState.RESOLVED:
        raise ValueError(f"{case.case_id} is resolved and cannot be stepped")
    if case.last_snapshot_id == obs.snapshot_id:
        raise ValueError(f"{case.case_id} was already evaluated at {obs.snapshot_id}")

    minimum = obs.metrics.minimum_severity
    eff = effective_severity(minimum, obs.raised)
    streak = 0 if obs.metrics.has_deviation else case.clean_streak + 1
    resolvable = streak >= resolution.snapshots_sin_desvio and not obs.raised
    new_state = next_state(case.state, critical=eff is Severity.CRITICAL, resolvable=resolvable)

    events: list[CaseEvent] = []
    if new_state is CaseState.ESCALATED and case.state is not CaseState.ESCALATED:
        events.append(CaseEvent.ESCALATED)
    if eff != case.current_severity:
        events.append(CaseEvent.SEVERITY_CHANGED)
    if new_state is CaseState.RESOLVED:
        events.append(CaseEvent.RESOLVED)

    peak = eff if case.max_severity_since_report is None else max(case.max_severity_since_report, eff)
    updated = _validated_copy(
        case,
        state=new_state,
        minimum_severity=minimum,
        raised=obs.raised,
        max_severity_since_report=peak,
        clean_streak=streak,
        last_snapshot_id=obs.snapshot_id,
        resolved_at=obs.snapshot_id if new_state is CaseState.RESOLVED else None,
    )
    return Step(case=updated, history=_history_row(updated, obs), events=tuple(events))


def _validated_copy(case: Case, **update: Any) -> Case:
    """A copy of 'case' that goes through the Case validators (model_copy skips them)."""
    fields = {name: getattr(case, name) for name in Case.model_fields}
    return Case.model_validate({**fields, **update})


def mark_reported(case: Case, snapshot_id: str) -> Case:
    """Store state and current severity as last reported, and empty the max (Q-28)."""
    return _validated_copy(
        case,
        last_reported_at=snapshot_id,
        last_reported_state=case.state,
        last_reported_severity=case.current_severity,
        max_severity_since_report=None,
    )
