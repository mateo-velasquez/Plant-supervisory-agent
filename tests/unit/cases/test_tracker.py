"""003 T16-T17: CaseTracker applies the lifecycle per snapshot, re-runs it (Q-27) and marks reports."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.tracker import CaseDelta, CaseTracker, TrackedEvent
from plant_monitor.domain.cases import CaseEvent, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, SnapshotCommit, all_combinations
from plant_monitor.metrics.thresholds import load_thresholds

from builders import PICKUP_BRAZIL, metrics_with

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)
PB_CASE = "S010-Pickup-Brasil"
NO_RAISES: frozenset[Combination] = frozenset()

type Metrics = dict[Combination, CombinationMetrics]


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


@pytest.fixture
def tracker(registry: SqliteRegistry) -> CaseTracker:
    """Tracker on the registry's cases, with fixture resolution thresholds."""
    return CaseTracker(registry.cases, load_thresholds(FIXTURES / "umbrales.yaml").resolucion)


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id and no anomalies or units."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def all_metrics(overrides: dict[Combination, CombinationMetrics] | None = None) -> Metrics:
    """Metrics for all 9 combinations: 'ninguna' unless overridden."""
    metrics = {combo: metrics_with(Severity.NONE, combination=combo) for combo in all_combinations()}
    metrics.update(overrides or {})
    return metrics


def pb(minimum: Severity) -> Metrics:
    """All 9 combinations with PB at 'minimum' and the rest 'ninguna'."""
    return all_metrics({PICKUP_BRAZIL: metrics_with(minimum)})


def tracked(
    registry: SqliteRegistry,
    tracker: CaseTracker,
    snapshot_id: str,
    metrics: Metrics,
    raises: frozenset[Combination] = NO_RAISES,
) -> CaseDelta:
    """Track one snapshot in its own committed unit of work."""
    with registry.processing(commit(snapshot_id)):
        return tracker.track(snapshot_id, metrics, raises)


def events_of(delta: CaseDelta) -> tuple[tuple[str, CaseEvent], ...]:
    """Delta events as '(case_id, event)' pairs."""
    return tuple((e.case_id, e.event) for e in delta.events)


# --- T16 · CaseTracker.track ---


def test_e5_two_combinations_follow_all_combinations_order(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    s010 = all_metrics(
        {
            PICKUP_BRAZIL: metrics_with(Severity.MEDIUM),
            SUV_LOCAL: metrics_with(Severity.HIGH, combination=SUV_LOCAL),
        }
    )
    first = tracked(registry, tracker, "S010", s010)
    assert [(c.case_id, c.state, c.current_severity) for c in first.cases] == [
        ("S010-SUV-Local", CaseState.OPEN, Severity.HIGH),
        (PB_CASE, CaseState.OPEN, Severity.MEDIUM),
    ]
    assert events_of(first) == (("S010-SUV-Local", CaseEvent.OPENED), (PB_CASE, CaseEvent.OPENED))

    s011 = all_metrics({SUV_LOCAL: metrics_with(Severity.HIGH, combination=SUV_LOCAL)})
    second = tracked(registry, tracker, "S011", s011)
    assert [(c.case_id, c.state, c.clean_streak, c.current_severity) for c in second.cases] == [
        ("S010-SUV-Local", CaseState.FOLLOW_UP, 0, Severity.HIGH),
        (PB_CASE, CaseState.FOLLOW_UP, 1, Severity.NONE),
    ]
    assert events_of(second) == ((PB_CASE, CaseEvent.SEVERITY_CHANGED),)


def test_e16_new_case_after_resolution_leaves_the_old_one_resolved(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    tracked(registry, tracker, "S010", pb(Severity.MEDIUM))
    tracked(registry, tracker, "S011", pb(Severity.NONE))
    resolution = tracked(registry, tracker, "S012", pb(Severity.NONE))
    assert events_of(resolution) == ((PB_CASE, CaseEvent.RESOLVED),)
    delta = tracked(registry, tracker, "S013", pb(Severity.MEDIUM))
    assert events_of(delta) == (("S013-Pickup-Brasil", CaseEvent.OPENED),)
    assert [(c.case_id, c.state) for c in delta.cases] == [("S013-Pickup-Brasil", CaseState.OPEN)]
    old = registry.cases.get_case(PB_CASE)
    assert old is not None
    assert old.state is CaseState.RESOLVED
    assert registry.cases.active_cases() == delta.cases
    assert [row.snapshot_id for row in registry.cases.history(PB_CASE)] == ["S010", "S011", "S012"]


def test_e29a_track_opens_and_stores_case_with_metric_values(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    pb_metrics = metrics_with(
        Severity.HIGH, gap_units=-6.0, gap_pct=-20.0, delay_days=1.0, bottleneck=Stage.ASSEMBLY
    )
    delta = tracked(registry, tracker, "S010", all_metrics({PICKUP_BRAZIL: pb_metrics}))
    case = registry.cases.get_case(PB_CASE)
    assert case is not None
    assert delta == CaseDelta(
        snapshot_id="S010", events=(TrackedEvent(PB_CASE, CaseEvent.OPENED),), cases=(case,)
    )
    assert (case.state, case.current_severity, case.raised) == (CaseState.OPEN, Severity.HIGH, False)
    assert registry.cases.history(PB_CASE) == (
        CaseHistoryRow(
            case_id=PB_CASE,
            snapshot_id="S010",
            state=CaseState.OPEN,
            minimum_severity=Severity.HIGH,
            raised=False,
            gap_units=-6.0,
            gap_pct=-20.0,
            delay_days=1.0,
            bottleneck=Stage.ASSEMBLY,
            clean_streak=0,
        ),
    )


def test_e29b_raise_at_opening_opens_escalated(registry: SqliteRegistry, tracker: CaseTracker) -> None:
    delta = tracked(registry, tracker, "S010", pb(Severity.MEDIUM), frozenset({PICKUP_BRAZIL}))
    (case,) = delta.cases
    assert (case.case_id, case.state, case.current_severity, case.raised) == (
        PB_CASE,
        CaseState.ESCALATED,
        Severity.CRITICAL,
        True,
    )
    assert events_of(delta) == ((PB_CASE, CaseEvent.OPENED), (PB_CASE, CaseEvent.ESCALATED))
    (row,) = registry.cases.history(PB_CASE)
    assert (row.minimum_severity, row.effective_severity, row.raised) == (
        Severity.MEDIUM,
        Severity.CRITICAL,
        True,
    )


def test_e29c_track_outside_its_processing_raises_even_with_nothing_to_write(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    with pytest.raises(RuntimeError):
        tracker.track("S010", all_metrics(), NO_RAISES)
    with registry.processing(commit("S011")), pytest.raises(RuntimeError):
        tracker.track("S010", all_metrics(), NO_RAISES)


def test_e29d_active_case_missing_from_metrics_raises_naming_it(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    tracked(registry, tracker, "S010", pb(Severity.HIGH))
    without_pb = {combo: m for combo, m in all_metrics().items() if combo != PICKUP_BRAZIL}
    with (
        pytest.raises(ValueError, match=PB_CASE),
        registry.processing(commit("S011")),
    ):
        tracker.track("S011", without_pb, NO_RAISES)


def test_rejected_first_track_does_not_pin_its_metrics_for_the_unit(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    """A first call rejected for missing metrics leaves no memo, so a full retry in the unit runs."""
    tracked(registry, tracker, "S010", pb(Severity.HIGH))
    without_pb = {combo: m for combo, m in all_metrics().items() if combo != PICKUP_BRAZIL}
    with registry.processing(commit("S011")):
        with pytest.raises(ValueError, match=PB_CASE):
            tracker.track("S011", without_pb, NO_RAISES)
        delta = tracker.track("S011", pb(Severity.HIGH), NO_RAISES)
    assert [c.case_id for c in delta.cases] == [PB_CASE]


def test_e31_rerun_in_one_snapshot_recomputes_from_pre_snapshot_state(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    case_id = "S009-Pickup-Brasil"
    opening = tracked(registry, tracker, "S009", pb(Severity.HIGH))
    assert [(c.case_id, c.state, c.current_severity) for c in opening.cases] == [
        (case_id, CaseState.OPEN, Severity.HIGH)
    ]
    metrics = pb(Severity.HIGH)
    with registry.processing(commit("S010")):
        first = tracker.track("S010", metrics, NO_RAISES)
        second = tracker.track("S010", metrics, frozenset({PICKUP_BRAZIL}))
    assert [(c.state, c.current_severity) for c in first.cases] == [(CaseState.FOLLOW_UP, Severity.HIGH)]
    assert first.events == ()
    assert second.snapshot_id == "S010"
    assert [(c.case_id, c.state, c.current_severity, c.raised) for c in second.cases] == [
        (case_id, CaseState.ESCALATED, Severity.CRITICAL, True)
    ]
    assert events_of(second) == ((case_id, CaseEvent.ESCALATED), (case_id, CaseEvent.SEVERITY_CHANGED))

    stored = registry.cases.get_case(case_id)
    assert stored is not None
    assert (stored.state, stored.current_severity) == (CaseState.ESCALATED, Severity.CRITICAL)
    history = registry.cases.history(case_id)
    assert [row.snapshot_id for row in history] == ["S009", "S010"]
    s010 = history[1]
    assert (s010.state, s010.minimum_severity, s010.effective_severity, s010.raised) == (
        CaseState.ESCALATED,
        Severity.HIGH,
        Severity.CRITICAL,
        True,
    )


# --- T17 · CaseTracker.mark_reported ---


def test_e24a_mark_reported_persists_baseline_without_history_row(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    with registry.processing(commit("S010")):
        tracker.track("S010", pb(Severity.MEDIUM), NO_RAISES)
        tracker.mark_reported(PB_CASE, "S010")
    tracked(registry, tracker, "S011", pb(Severity.CRITICAL))
    with registry.processing(commit("S012")):
        tracker.track("S012", pb(Severity.HIGH), NO_RAISES)
        tracker.mark_reported(PB_CASE, "S012")
    case = registry.cases.get_case(PB_CASE)
    assert case is not None
    assert (case.last_reported_at, case.last_reported_state, case.last_reported_severity) == (
        "S012",
        CaseState.ESCALATED,
        Severity.HIGH,
    )
    assert case.max_severity_since_report is None
    assert [row.snapshot_id for row in registry.cases.history(PB_CASE)] == ["S010", "S011", "S012"]


def test_e24b_case_resolved_mid_shift_is_marked_at_closing(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    case_id = "S009-Pickup-Brasil"
    tracked(registry, tracker, "S009", pb(Severity.MEDIUM))
    tracked(registry, tracker, "S010", pb(Severity.NONE))
    tracked(registry, tracker, "S011", pb(Severity.NONE))
    with registry.processing(commit("S012")):
        tracker.mark_reported(case_id, "S012")
    case = registry.cases.get_case(case_id)
    assert case is not None
    assert (case.last_reported_at, case.last_reported_state, case.last_reported_severity) == (
        "S012",
        CaseState.RESOLVED,
        Severity.NONE,
    )
    assert case.last_snapshot_id == "S011"
    assert case.max_severity_since_report is None
    assert [row.snapshot_id for row in registry.cases.history(case_id)] == ["S009", "S010", "S011"]


def test_e24c_mark_reported_outside_processing_or_for_unknown_case_raises(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    tracked(registry, tracker, "S010", pb(Severity.MEDIUM))
    with pytest.raises(RuntimeError):
        tracker.mark_reported(PB_CASE, "S012")
    with registry.processing(commit("S012")), pytest.raises(ValueError, match="S999-Pickup-Brasil"):
        tracker.mark_reported("S999-Pickup-Brasil", "S012")
    case = registry.cases.get_case(PB_CASE)
    assert case is not None
    assert case.last_reported_at is None


# --- Review fixes · Re-run misuse enforced in code (Q-27) ---


def test_q27_rerun_with_different_metrics_raises(registry: SqliteRegistry, tracker: CaseTracker) -> None:
    """An equal but distinct 'metrics' mapping is a valid re-run, so the check must compare by value."""
    with registry.processing(commit("S010")):
        tracker.track("S010", pb(Severity.HIGH), NO_RAISES)
        tracker.track("S010", pb(Severity.HIGH), frozenset({PICKUP_BRAZIL}))
        with pytest.raises(ValueError):
            tracker.track("S010", pb(Severity.MEDIUM), NO_RAISES)


def test_q27_track_after_mark_reported_in_the_same_unit_raises(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    with registry.processing(commit("S010")):
        tracker.track("S010", pb(Severity.MEDIUM), NO_RAISES)
        tracker.mark_reported(PB_CASE, "S010")
        with pytest.raises(RuntimeError):
            tracker.track("S010", pb(Severity.MEDIUM), frozenset({PICKUP_BRAZIL}))


def test_mark_reported_on_active_case_not_yet_tracked_at_snapshot_raises(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    tracked(registry, tracker, "S010", pb(Severity.MEDIUM))
    with pytest.raises(ValueError), registry.processing(commit("S011")):
        tracker.mark_reported(PB_CASE, "S011")
    case = registry.cases.get_case(PB_CASE)
    assert case is not None
    assert (case.last_snapshot_id, case.last_reported_at) == ("S010", None)


def test_q27_retry_after_rollback_starts_a_fresh_memo(registry: SqliteRegistry, tracker: CaseTracker) -> None:
    with pytest.raises(RuntimeError, match="boom"), registry.processing(commit("S010")):
        tracker.track("S010", pb(Severity.MEDIUM), NO_RAISES)
        tracker.mark_reported(PB_CASE, "S010")
        raise RuntimeError("boom")
    assert registry.cases.get_case(PB_CASE) is None
    with registry.processing(commit("S010")):
        delta = tracker.track("S010", pb(Severity.MEDIUM), NO_RAISES)
        tracker.mark_reported(PB_CASE, "S010")
    assert events_of(delta) == ((PB_CASE, CaseEvent.OPENED),)
    case = registry.cases.get_case(PB_CASE)
    assert case is not None
    assert (case.last_reported_at, case.last_reported_state) == ("S010", CaseState.OPEN)


def test_q27_rerun_on_the_opening_snapshot_keeps_one_case_and_one_row(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    metrics = pb(Severity.MEDIUM)
    with registry.processing(commit("S010")):
        first = tracker.track("S010", metrics, NO_RAISES)
        second = tracker.track("S010", metrics, frozenset({PICKUP_BRAZIL}))
    assert [(c.case_id, c.state) for c in first.cases] == [(PB_CASE, CaseState.OPEN)]
    assert events_of(second) == ((PB_CASE, CaseEvent.OPENED), (PB_CASE, CaseEvent.ESCALATED))
    assert [(c.case_id, c.state, c.current_severity) for c in registry.cases.active_cases()] == [
        (PB_CASE, CaseState.ESCALATED, Severity.CRITICAL)
    ]
    (row,) = registry.cases.history(PB_CASE)
    assert (row.snapshot_id, row.state, row.raised) == ("S010", CaseState.ESCALATED, True)


def test_q25_lift_on_rerun_resolves_at_that_snapshot(registry: SqliteRegistry, tracker: CaseTracker) -> None:
    case_id = "S009-Pickup-Brasil"
    raise_pb = frozenset({PICKUP_BRAZIL})
    tracked(registry, tracker, "S009", pb(Severity.MEDIUM), raise_pb)
    tracked(registry, tracker, "S010", pb(Severity.NONE), raise_pb)
    metrics = pb(Severity.NONE)
    with registry.processing(commit("S011")):
        blocked = tracker.track("S011", metrics, raise_pb)
        lifted = tracker.track("S011", metrics, NO_RAISES)
    assert [(c.state, c.clean_streak) for c in blocked.cases] == [(CaseState.ESCALATED, 2)]
    assert events_of(lifted) == ((case_id, CaseEvent.SEVERITY_CHANGED), (case_id, CaseEvent.RESOLVED))
    case = registry.cases.get_case(case_id)
    assert case is not None
    assert (case.state, case.resolved_at, case.clean_streak) == (CaseState.RESOLVED, "S011", 2)
    assert registry.cases.active_cases() == ()
    assert [row.snapshot_id for row in registry.cases.history(case_id)] == ["S009", "S010", "S011"]
