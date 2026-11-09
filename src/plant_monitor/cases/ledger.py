"""'CauseLedger': set_cause, raise and lift rules over the cause store; checks come before writes."""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from plant_monitor.cases.causes import Candidate, link_targets, same_cause
from plant_monitor.cases.registry import CauseStore
from plant_monitor.domain.calendar import calendar_order
from plant_monitor.domain.cases import Case
from plant_monitor.domain.causes import (
    ActiveCause,
    Cause,
    CauseCategory,
    CauseScope,
    CitedCause,
    Evidence,
    active_cause_id_for,
)
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.models import Combination, Shift


class CaseLookup(Protocol):
    """What the ledger needs to find a case."""

    def get_case(self, case_id: str) -> Case | None: ...


class CaseNotFound(RejectedRequest):
    def __init__(self, case_id: str) -> None:
        super().__init__(f"unknown case {case_id}")


class CaseNotEvaluated(RejectedRequest):
    def __init__(self, case_id: str, snapshot_id: str) -> None:
        super().__init__(f"{case_id} is not evaluated at {snapshot_id}")


class CauseAlreadySet(RejectedRequest):
    def __init__(self, case_id: str, set_at: str) -> None:
        super().__init__(f"cause of {case_id} was set at {set_at}; it stays until the case resolves")


class CauseFromRaise(RejectedRequest):
    def __init__(self, case_id: str, active_cause_id: str) -> None:
        super().__init__(f"cause of {case_id} comes from active cause {active_cause_id}")


class CauseLinkedToRaise(RejectedRequest):
    def __init__(self, case_id: str, active: ActiveCause) -> None:
        super().__init__(
            f"{case_id} is linked to active cause {active.active_cause_id} "
            f"({active.categoria.value} in {active.scope.etapa.value}); "
            "its cause cannot change while the raise is in force"
        )


class DuplicateRaise(RejectedRequest):
    def __init__(self, active_cause_id: str, scope: CauseScope) -> None:
        super().__init__(f"active cause {active_cause_id} already covers {scope.describe()}")


class UnknownActiveCause(RejectedRequest):
    def __init__(self, active_cause_id: str) -> None:
        super().__init__(f"unknown active cause {active_cause_id}")


class RaiseAlreadyLifted(RejectedRequest):
    def __init__(self, active_cause_id: str, lifted_at: str | None) -> None:
        super().__init__(f"active cause {active_cause_id} was lifted at {lifted_at}")


class LiftNotLater(RejectedRequest):
    def __init__(self, bitacora: str, opening: str, active_cause_id: str) -> None:
        super().__init__(
            f"{bitacora} is not later than {opening}, which opened active cause {active_cause_id}"
        )


@dataclass(frozen=True)
class RaiseOutcome:
    """Result of a raise: the new active cause and the cases it linked, in candidate order."""

    active_cause_id: str
    linked: tuple[str, ...]


def _stripped(evidence: Evidence) -> Evidence:
    return Evidence(bitacora=evidence.bitacora, fragmento=evidence.fragmento.strip())


class CauseLedger:
    """Cited causes and active causes (R3 to R11) over a 'CauseStore'."""

    def __init__(self, store: CauseStore, cases: CaseLookup, shifts: Sequence[Shift]) -> None:
        self._store = store
        self._cases = cases
        self._position = {shift.turno_id: i for i, shift in enumerate(calendar_order(shifts))}

    def raised(self, cases: Sequence[Case]) -> frozenset[Combination]:
        """Combinations of the given cases linked to a cause in force (R10)."""
        in_force = [cause.active_cause_id for cause in self._store.in_force()]
        linked = {case_id for ids in self._store.links(in_force).values() for case_id in ids}
        return frozenset(case.combination for case in cases if case.case_id in linked)

    def recheck(self, snapshot_id: str, candidates: Sequence[Candidate]) -> bool:
        """Link candidates that enter the scope of a cause in force (R7); whether any link was added."""
        added = False
        for cause in self._store.in_force():
            if self._link(snapshot_id, cause, candidates):
                added = True
        return added

    def set_cause(
        self,
        snapshot_id: str,
        case_id: str,
        cause: Cause,
        evidence: Evidence,
        candidates: Sequence[Candidate],
    ) -> None:
        """Store the cited cause of a case (R3 checks 3 to 7); a second call in the snapshot replaces it."""
        if self._cases.get_case(case_id) is None:
            raise CaseNotFound(case_id)
        if case_id not in {candidate.case.case_id for candidate in candidates}:
            raise CaseNotEvaluated(case_id, snapshot_id)
        current = self._store.cited([case_id]).get(case_id)
        if current is not None:
            if current.set_at != snapshot_id:
                raise CauseAlreadySet(case_id, current.set_at)
            if current.active_cause_id is not None:
                raise CauseFromRaise(case_id, current.active_cause_id)
        if cause.etapa is None or cause.categoria is CauseCategory.UNDECLARED:
            raise ValueError(f"{case_id}: a cited cause needs a declared category and a stage")
        for active, linked in self.in_force_view():
            if case_id in linked and (active.categoria, active.scope.etapa) != (cause.categoria, cause.etapa):
                raise CauseLinkedToRaise(case_id, active)
        self._store.set_cited(
            case_id,
            CitedCause(
                categoria=cause.categoria, etapa=cause.etapa, evidence=_stripped(evidence), set_at=snapshot_id
            ),
        )

    def raise_severity(
        self,
        snapshot_id: str,
        categoria: CauseCategory,
        scope: CauseScope,
        evidence: Evidence,
        candidates: Sequence[Candidate],
    ) -> RaiseOutcome:
        """Open an active cause, link the matching cases and attach its cause (R5, R6, R8)."""
        for existing in self._store.in_force():
            if existing.scope == scope:
                raise DuplicateRaise(existing.active_cause_id, scope)
        cause = ActiveCause(
            active_cause_id=active_cause_id_for(snapshot_id, self._store.opened_count(snapshot_id) + 1),
            categoria=categoria,
            scope=scope,
            opened_at=snapshot_id,
            opened_by=_stripped(evidence),
        )
        self._store.open(cause)
        linked = self._link(snapshot_id, cause, candidates)
        return RaiseOutcome(cause.active_cause_id, linked)

    def lift(self, snapshot_id: str, active_cause_id: str, evidence: Evidence) -> None:
        """Lift a cause in force with a logbook later than the one that opened it (R9 checks 1, 2, 4)."""
        cause = self._store.get_active(active_cause_id)
        if cause is None:
            raise UnknownActiveCause(active_cause_id)
        if not cause.in_force:
            raise RaiseAlreadyLifted(active_cause_id, cause.lifted_at)
        opening = cause.opened_by.bitacora
        if self._order(evidence.bitacora) <= self._order(opening):
            raise LiftNotLater(evidence.bitacora, opening, active_cause_id)
        self._store.lift(active_cause_id, snapshot_id, _stripped(evidence))

    def in_force_view(self) -> tuple[tuple[ActiveCause, tuple[str, ...]], ...]:
        """Causes in force with the cases linked to each."""
        in_force = self._store.in_force()
        links = self._store.links([cause.active_cause_id for cause in in_force])
        return tuple((cause, links.get(cause.active_cause_id, ())) for cause in in_force)

    def cited(self, case_ids: Collection[str]) -> Mapping[str, CitedCause]:
        return self._store.cited(case_ids)

    def _order(self, logbook_id: str) -> int:
        if logbook_id not in self._position:
            raise ValueError(f"logbook {logbook_id} is not in the shift calendar")
        return self._position[logbook_id]

    def _link(self, snapshot_id: str, cause: ActiveCause, candidates: Sequence[Candidate]) -> tuple[str, ...]:
        """Link the targets of 'cause' and attach its cause to those without one (R8)."""
        ids = [candidate.case.case_id for candidate in candidates]
        cited = self._store.cited(ids)
        already = self._store.links([cause.active_cause_id]).get(cause.active_cause_id, ())
        targets = link_targets(cause, candidates, cited, already)
        for case_id in targets:
            self._store.link(cause.active_cause_id, case_id, snapshot_id)
            current = cited.get(case_id)
            if current is None or not same_cause(current, cause.categoria, cause.scope.etapa):
                self._store.set_cited(
                    case_id,
                    CitedCause(
                        categoria=cause.categoria,
                        etapa=cause.scope.etapa,
                        evidence=cause.opened_by,
                        set_at=snapshot_id,
                        active_cause_id=cause.active_cause_id,
                    ),
                )
        return targets
