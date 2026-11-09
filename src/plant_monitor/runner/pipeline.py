"""Threshold-only snapshot pipeline: metrics, lifecycle and notice decisions inside the unit of work."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from plant_monitor.cases.causes import Candidate
from plant_monitor.cases.ledger import CauseLedger
from plant_monitor.cases.notice_builder import ShiftClose, SnapshotNotices, build_snapshot_notices
from plant_monitor.cases.registry import CaseRepository, SqliteRegistry
from plant_monitor.cases.tracker import CaseDelta, CaseTracker
from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.causes import ActiveCause
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Combination, CombinationMetrics, ReleasedUnit, Shift, Snapshot
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.metrics.engine import PlantContext, compute_metrics


class ReleaseLog(Protocol):
    """Units released so far, and the recording of a snapshot's releases."""

    def released_so_far(self) -> tuple[ReleasedUnit, ...]: ...

    def record_releases(self, snapshot: Snapshot) -> None: ...


class NoticeSink(Protocol):
    """Where a snapshot's notice decisions are saved."""

    def save(self, snapshot_id: str, decisions: Sequence[Notice], report: ShiftReport | None) -> None: ...


class NoticeCaseReader(Protocol):
    """Case reads the notice step needs beyond the tracker's port; SqliteCaseRepository satisfies it."""

    def resolved_unreported(self) -> tuple[Case, ...]: ...

    def last_deviation_row(self, case_id: str) -> CaseHistoryRow | None: ...


def shift_close(shift: Shift, position: ShiftPosition, reader: NoticeCaseReader) -> ShiftClose | None:
    """At a closing snapshot, the shift and its raw resolved-unreported cases; None at a mid snapshot."""
    if position is not ShiftPosition.CLOSING:
        return None
    return ShiftClose(shift.turno_id, reader.resolved_unreported())


def deviation_rows(case_ids: Iterable[str], reader: NoticeCaseReader) -> dict[str, CaseHistoryRow]:
    """Last history row with a deviation per case (Q-32); ValueError naming a case that has none."""
    rows: dict[str, CaseHistoryRow] = {}
    for case_id in case_ids:
        if case_id in rows:
            continue
        row = reader.last_deviation_row(case_id)
        if row is None:
            raise ValueError(f"case {case_id} has no history row with a deviation")
        rows[case_id] = row
    return rows


@dataclass(frozen=True)
class SnapshotDecision:
    """What 'decide' settled for one snapshot, ready for 'finish'."""

    snapshot: Snapshot
    shift: Shift
    position: ShiftPosition
    metrics: Mapping[Combination, CombinationMetrics]
    notices: SnapshotNotices
    delta: CaseDelta | None = None
    candidates: tuple[Candidate, ...] = ()
    in_force: tuple[tuple[ActiveCause, tuple[str, ...]], ...] = ()


class ThresholdPipeline:
    """Threshold-only SnapshotPipeline: metrics, lifecycle and notice decisions inside the unit of work."""

    def __init__(
        self,
        ctx: PlantContext,
        releases: ReleaseLog,
        cases: CaseRepository,
        reader: NoticeCaseReader,
        notices: NoticeSink,
        ledger: CauseLedger | None = None,
    ) -> None:
        self._ctx = ctx
        self._releases = releases
        self._cases = cases
        self._reader = reader
        self._notices = notices
        self._ledger = ledger
        self._tracker = CaseTracker(cases, ctx.thresholds.resolucion)

    @classmethod
    def from_registry(
        cls, registry: SqliteRegistry, ctx: PlantContext, ledger: CauseLedger | None = None
    ) -> ThresholdPipeline:
        """Wire the pipeline on the registry's shared collaborators."""
        return cls(ctx, registry.releases, registry.cases, registry.cases, registry.notices, ledger)

    def _lifecycle(
        self,
        snapshot_id: str,
        metrics: Mapping[Combination, CombinationMetrics],
        cases: Sequence[Case],
    ) -> tuple[CaseDelta, tuple[Candidate, ...]]:
        """Track with the raises in force, link what enters a scope, and track again if a link was added."""
        ledger = self._ledger
        raises = frozenset[Combination]() if ledger is None else ledger.raised(cases)
        delta = self._tracker.track(snapshot_id, metrics, raises)
        candidates = self._candidates(delta)
        if ledger is not None and ledger.recheck(snapshot_id, candidates):
            delta = self._tracker.track(snapshot_id, metrics, ledger.raised(delta.cases))
            candidates = self._candidates(delta)
        return delta, candidates

    def _candidates(self, delta: CaseDelta) -> tuple[Candidate, ...]:
        rows = deviation_rows([case.case_id for case in delta.cases], self._reader)
        return tuple(Candidate(case, rows[case.case_id].bottleneck) for case in delta.cases)

    def _notices_for(
        self,
        decision: SnapshotDecision,
        delta: CaseDelta,
        candidates: tuple[Candidate, ...],
    ) -> SnapshotDecision:
        """Closing glue, cited causes and notices for a settled delta."""
        close = shift_close(decision.shift, decision.position, self._reader)
        ids = [case.case_id for case in delta.cases]
        if close is not None:
            ids += [case.case_id for case in close.resolved_unreported]
        rows = deviation_rows(ids, self._reader)
        ledger = self._ledger
        cited = {} if ledger is None else ledger.cited(ids)
        built = build_snapshot_notices(delta, decision.metrics, rows, close, cited)
        in_force = () if ledger is None else ledger.in_force_view()
        return replace(decision, notices=built, delta=delta, candidates=candidates, in_force=in_force)

    def decide(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> SnapshotDecision:
        """Metrics, lifecycle and notices.

        Writes releases and lifecycle rows to the open unit of work; an abort relies on its rollback.
        """
        sid = snapshot.snapshot_id
        metrics = compute_metrics(snapshot, self._releases.released_so_far(), self._ctx)
        self._releases.record_releases(snapshot)
        delta, candidates = self._lifecycle(sid, metrics, self._cases.active_cases())
        empty = SnapshotDecision(snapshot, shift, position, metrics, SnapshotNotices((), None, ()))
        return self._notices_for(empty, delta, candidates)

    def redecide(self, decision: SnapshotDecision) -> SnapshotDecision:
        """Re-run the lifecycle and notices after a judgment write; same metrics, no save, no mark."""
        if decision.delta is None:
            raise ValueError("redecide needs a decision from 'decide'")
        sid = decision.snapshot.snapshot_id
        delta, candidates = self._lifecycle(sid, decision.metrics, decision.delta.cases)
        return self._notices_for(decision, delta, candidates)

    def finish(self, decision: SnapshotDecision) -> None:
        """Save the notices once, then mark the reported cases."""
        sid = decision.snapshot.snapshot_id
        built = decision.notices
        self._notices.save(sid, built.decisions, built.report)
        for case_id in built.to_mark:
            self._tracker.mark_reported(case_id, sid)

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        """Database writes only; delivery is the post-commit dispatcher's job (ADR-0010)."""
        self.finish(self.decide(snapshot, shift, position))
