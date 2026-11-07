"""Applies the case lifecycle to one snapshot at a time and records report baselines."""

from collections.abc import Mapping
from dataclasses import dataclass

from plant_monitor.cases import lifecycle
from plant_monitor.cases.registry import CaseRepository
from plant_monitor.domain.cases import Case, CaseEvent
from plant_monitor.domain.models import Combination, CombinationMetrics, all_combinations
from plant_monitor.metrics.thresholds import ResolutionThresholds


@dataclass(frozen=True)
class TrackedEvent:
    """One lifecycle event of one case."""

    case_id: str
    event: CaseEvent


@dataclass(frozen=True)
class CaseDelta:
    """Lifecycle outcome of one snapshot, for spec 004; the last one for a snapshot wins (Q-27)."""

    snapshot_id: str
    events: tuple[TrackedEvent, ...]
    cases: tuple[Case, ...]


@dataclass
class _Memo:
    """Pre-snapshot state of one unit of work, so a re-run does not step cases already at N."""

    unit: int | None
    snapshot_id: str
    metrics: dict[Combination, CombinationMetrics]
    active_before: tuple[Case, ...]
    marked: set[str]


class CaseTracker:
    """Applies the case lifecycle to each snapshot and records report baselines."""

    def __init__(self, repo: CaseRepository, resolution: ResolutionThresholds) -> None:
        self._repo = repo
        self._resolution = resolution
        self._memo: _Memo | None = None

    def track(
        self,
        snapshot_id: str,
        metrics: Mapping[Combination, CombinationMetrics],
        raises: frozenset[Combination],
    ) -> CaseDelta:
        """Evaluate every combination at `snapshot_id`; a re-run restarts from the pre-snapshot state."""
        self._require_open(snapshot_id)
        unit = self._repo.current_unit()
        memo = self._memo
        rerun = memo is not None and memo.unit == unit and memo.snapshot_id == snapshot_id
        if memo is not None and rerun:
            if memo.marked:
                raise RuntimeError(f"track for {snapshot_id} after mark_reported in the same unit of work")
            if memo.metrics != dict(metrics):
                raise ValueError(f"re-run of {snapshot_id} with different metrics")
            active = memo.active_before
        else:
            active = self._repo.active_cases()

        by_combo = {case.combination: case for case in active}
        for combo, case in by_combo.items():
            if combo not in metrics:
                raise ValueError(f"active case {case.case_id} has no metrics at {snapshot_id}")
        if not rerun:
            # Stored only after the input check, so a rejected first call does not pin bad metrics.
            self._memo = _Memo(unit, snapshot_id, dict(metrics), active, set())

        events: list[TrackedEvent] = []
        cases: list[Case] = []
        for combo in all_combinations():
            if combo not in metrics:
                continue
            obs = lifecycle.Observation(snapshot_id, metrics[combo], combo in raises)
            result = lifecycle.step(by_combo.get(combo), obs, self._resolution)
            if result is None:
                continue
            self._repo.save_case(result.case, result.history)
            cases.append(result.case)
            events.extend(TrackedEvent(result.case.case_id, event) for event in result.events)
        return CaseDelta(snapshot_id=snapshot_id, events=tuple(events), cases=tuple(cases))

    def mark_reported(self, case_id: str, snapshot_id: str) -> None:
        """Store the report baseline of a case; allowed on one resolved earlier in the shift.

        A resolved case marked before any `track` is not recorded in `marked`; that is safe only
        while `track` writes nothing but `active_before` cases and new openings (see Q-29).
        """
        self._require_open(snapshot_id)
        case = self._repo.get_case(case_id)
        if case is None:
            raise ValueError(f"unknown case {case_id}")
        if case.state.is_active and case.last_snapshot_id != snapshot_id:
            raise ValueError(f"active case {case_id} was not tracked at {snapshot_id}")
        self._repo.update_case(lifecycle.mark_reported(case, snapshot_id))
        memo = self._memo
        if memo is not None and memo.unit == self._repo.current_unit() and memo.snapshot_id == snapshot_id:
            memo.marked.add(case_id)

    def _require_open(self, snapshot_id: str) -> None:
        if self._repo.current_snapshot() != snapshot_id:
            raise RuntimeError(f"no unit of work open for {snapshot_id}")
