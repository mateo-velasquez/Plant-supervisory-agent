"""003 T2-T11: the pure case lifecycle of criterio.md §3 and the max severity since the last report (§4)."""

from pathlib import Path

import pytest

from plant_monitor.cases.lifecycle import Observation, Step, mark_reported, next_state, step
from plant_monitor.domain.cases import Case, CaseEvent, CaseState
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.metrics.thresholds import ResolutionThresholds, load_thresholds

from builders import PICKUP_BRAZIL, metrics_with

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
PB_CASE = "S010-Pickup-Brasil"

OPEN = CaseState.OPEN
FOLLOW_UP = CaseState.FOLLOW_UP
ESCALATED = CaseState.ESCALATED
RESOLVED = CaseState.RESOLVED


@pytest.fixture
def resolution() -> ResolutionThresholds:
    return load_thresholds(FIXTURES / "umbrales.yaml").resolucion


def obs(snapshot_id: str, minimum: Severity, *, raised: bool = False) -> Observation:
    """Pickup-Brasil observed at one snapshot."""
    return Observation(snapshot_id=snapshot_id, metrics=metrics_with(minimum), raised=raised)


def advance(case: Case | None, observation: Observation, resolution: ResolutionThresholds) -> Step:
    """A step that must yield a case."""
    result = step(case, observation, resolution)
    assert result is not None
    return result


def walk(resolution: ResolutionThresholds, *observations: Observation) -> list[Step]:
    """Step one case through 'observations', starting with no case."""
    steps: list[Step] = []
    case: Case | None = None
    for observation in observations:
        result = advance(case, observation, resolution)
        steps.append(result)
        case = result.case
    return steps


# --- T2 · Transition table ---


@pytest.mark.parametrize(
    ("current", "resolvable", "critical", "expected"),
    [
        *[
            pytest.param(state, True, critical, RESOLVED, id=f"{state}-resolvable-critical={critical}")
            for state in (OPEN, FOLLOW_UP, ESCALATED)
            for critical in (False, True)
        ],
        pytest.param(ESCALATED, False, False, ESCALATED, id="escalado-sticky-not-critical"),
        pytest.param(ESCALATED, False, True, ESCALATED, id="escalado-sticky-critical"),
        pytest.param(None, False, True, ESCALATED, id="opening-critical"),
        pytest.param(OPEN, False, True, ESCALATED, id="abierto-critical"),
        pytest.param(FOLLOW_UP, False, True, ESCALATED, id="en_seguimiento-critical"),
        pytest.param(None, False, False, OPEN, id="opening"),
        pytest.param(OPEN, False, False, FOLLOW_UP, id="abierto-to-en_seguimiento"),
        pytest.param(FOLLOW_UP, False, False, FOLLOW_UP, id="en_seguimiento-stays"),
    ],
)
def test_next_state_follows_the_transition_table(
    current: CaseState | None, resolvable: bool, critical: bool, expected: CaseState
) -> None:
    assert next_state(current, critical=critical, resolvable=resolvable) is expected


@pytest.mark.parametrize("critical", [False, True])
@pytest.mark.parametrize("resolvable", [False, True])
def test_next_state_from_resuelto_raises(critical: bool, resolvable: bool) -> None:
    with pytest.raises(ValueError):
        next_state(RESOLVED, critical=critical, resolvable=resolvable)


# --- T3 · Opening ---


def test_e1_deviation_without_case_opens_in_abierto(resolution: ResolutionThresholds) -> None:
    metrics = metrics_with(
        Severity.MEDIUM, gap_units=-4.0, gap_pct=-13.3, delay_days=0.0, bottleneck=Stage.ASSEMBLY
    )
    result = advance(None, Observation(snapshot_id="S010", metrics=metrics, raised=False), resolution)
    case = result.case
    assert case.case_id == PB_CASE
    assert case.combination == PICKUP_BRAZIL
    assert (case.state, case.opened_at, case.last_snapshot_id) == (OPEN, "S010", "S010")
    assert case.current_severity is Severity.MEDIUM
    assert case.max_severity_since_report is Severity.MEDIUM
    assert (case.clean_streak, case.raised, case.resolved_at) == (0, False, None)
    assert (case.last_reported_at, case.last_reported_state, case.last_reported_severity) == (
        None,
        None,
        None,
    )
    assert result.events == (CaseEvent.OPENED,)
    row = result.history
    assert (row.case_id, row.snapshot_id, row.state, row.clean_streak) == (PB_CASE, "S010", OPEN, 0)
    assert (row.minimum_severity, row.raised, row.effective_severity) == (
        Severity.MEDIUM,
        False,
        Severity.MEDIUM,
    )
    assert (row.gap_units, row.gap_pct, row.delay_days, row.bottleneck) == (-4.0, -13.3, 0.0, Stage.ASSEMBLY)


@pytest.mark.parametrize("raised", [False, True], ids=["no-raise", "raise"])
def test_e2_no_deviation_opens_no_case(resolution: ResolutionThresholds, raised: bool) -> None:
    assert step(None, obs("S010", Severity.NONE, raised=raised), resolution) is None


# --- T4 · Follow-up, one active case, guards ---


def test_e3_follow_up_from_next_snapshot_with_severity_change_event(resolution: ResolutionThresholds) -> None:
    _, s011, s012 = walk(
        resolution, obs("S010", Severity.MEDIUM), obs("S011", Severity.MEDIUM), obs("S012", Severity.HIGH)
    )
    assert (s011.case.state, s011.case.current_severity, s011.case.clean_streak) == (
        FOLLOW_UP,
        Severity.MEDIUM,
        0,
    )
    assert s011.events == ()
    assert (s012.case.state, s012.case.current_severity) == (FOLLOW_UP, Severity.HIGH)
    assert s012.case.max_severity_since_report is Severity.HIGH
    assert s012.events == (CaseEvent.SEVERITY_CHANGED,)


def test_e4_active_case_keeps_its_id_and_never_reopens(resolution: ResolutionThresholds) -> None:
    _, s011 = walk(resolution, obs("S010", Severity.MEDIUM), obs("S011", Severity.MEDIUM))
    assert s011.case.state is FOLLOW_UP
    s012 = advance(s011.case, obs("S012", Severity.HIGH), resolution)
    assert s012.case.case_id == PB_CASE
    assert s012.case.opened_at == "S010"
    assert CaseEvent.OPENED not in s012.events


def test_e18a_stepping_the_same_snapshot_twice_raises_naming_case_and_snapshot(
    resolution: ResolutionThresholds,
) -> None:
    _, s011 = walk(resolution, obs("S010", Severity.MEDIUM), obs("S011", Severity.NONE))
    with pytest.raises(ValueError) as error:
        step(s011.case, obs("S011", Severity.NONE), resolution)
    assert PB_CASE in str(error.value)
    assert "S011" in str(error.value)


def test_e18b_stepping_a_resolved_case_raises_naming_it(resolution: ResolutionThresholds) -> None:
    resolved = Case(
        case_id=PB_CASE,
        combination=PICKUP_BRAZIL,
        opened_at="S010",
        state=RESOLVED,
        minimum_severity=Severity.NONE,
        raised=False,
        max_severity_since_report=Severity.MEDIUM,
        clean_streak=2,
        last_snapshot_id="S012",
        resolved_at="S012",
    )
    with pytest.raises(ValueError, match=PB_CASE):
        step(resolved, obs("S013", Severity.MEDIUM), resolution)


# --- T5 · Escalation ---


def test_e7_threshold_critica_escalates(resolution: ResolutionThresholds) -> None:
    s010, s011 = walk(resolution, obs("S010", Severity.HIGH), obs("S011", Severity.CRITICAL))
    assert s010.case.state is OPEN
    assert s010.events == (CaseEvent.OPENED,)
    assert (s011.case.state, s011.case.current_severity) == (ESCALATED, Severity.CRITICAL)
    assert s011.case.max_severity_since_report is Severity.CRITICAL
    assert s011.events == (CaseEvent.ESCALATED, CaseEvent.SEVERITY_CHANGED)


def test_e8_critica_at_opening_opens_in_escalado_with_one_escalated(resolution: ResolutionThresholds) -> None:
    s010, s011 = walk(resolution, obs("S010", Severity.CRITICAL), obs("S011", Severity.CRITICAL))
    assert s010.case.case_id == PB_CASE
    assert (s010.case.state, s010.case.current_severity) == (ESCALATED, Severity.CRITICAL)
    assert s010.events == (CaseEvent.OPENED, CaseEvent.ESCALATED)
    assert s011.case.state is ESCALATED
    assert s011.events == ()


def test_e9_raise_at_opening_opens_in_escalado(resolution: ResolutionThresholds) -> None:
    result = advance(None, obs("S010", Severity.MEDIUM, raised=True), resolution)
    assert result.case.case_id == PB_CASE
    assert (result.case.state, result.case.current_severity, result.case.raised) == (
        ESCALATED,
        Severity.CRITICAL,
        True,
    )
    assert result.events == (CaseEvent.OPENED, CaseEvent.ESCALATED)
    assert result.history.minimum_severity is Severity.MEDIUM
    assert result.history.effective_severity is Severity.CRITICAL


# --- T6 · Sticky escalado ---


def test_e10_escalado_is_sticky_when_severity_drops(resolution: ResolutionThresholds) -> None:
    """Characterization: passes once T4 is in, because next_state already holds the sticky row."""
    _, _, s012, s013 = walk(
        resolution,
        obs("S010", Severity.HIGH),
        obs("S011", Severity.CRITICAL),
        obs("S012", Severity.HIGH),
        obs("S013", Severity.MEDIUM),
    )
    assert (s012.case.state, s012.case.current_severity) == (ESCALATED, Severity.HIGH)
    assert s012.case.max_severity_since_report is Severity.CRITICAL
    assert s012.events == (CaseEvent.SEVERITY_CHANGED,)
    assert (s013.case.state, s013.case.current_severity) == (ESCALATED, Severity.MEDIUM)
    assert s013.case.max_severity_since_report is Severity.CRITICAL
    assert s013.events == (CaseEvent.SEVERITY_CHANGED,)


# --- T7 · Resolution streak and reset ---


def test_e11_two_clean_snapshots_resolve(resolution: ResolutionThresholds) -> None:
    _, s011, s012 = walk(
        resolution, obs("S010", Severity.MEDIUM), obs("S011", Severity.NONE), obs("S012", Severity.NONE)
    )
    assert (s011.case.state, s011.case.clean_streak, s011.case.current_severity) == (
        FOLLOW_UP,
        1,
        Severity.NONE,
    )
    assert s011.events == (CaseEvent.SEVERITY_CHANGED,)
    assert (s012.case.state, s012.case.clean_streak, s012.case.resolved_at) == (RESOLVED, 2, "S012")
    assert s012.case.current_severity is Severity.NONE
    assert s012.events == (CaseEvent.RESOLVED,)
    assert (s012.history.state, s012.history.clean_streak) == (RESOLVED, 2)


def test_e12_deviation_resets_the_streak(resolution: ResolutionThresholds) -> None:
    steps = walk(
        resolution,
        obs("S010", Severity.MEDIUM),
        obs("S011", Severity.NONE),
        obs("S012", Severity.MEDIUM),
        obs("S013", Severity.NONE),
        obs("S014", Severity.NONE),
    )
    assert [s.case.clean_streak for s in steps] == [0, 1, 0, 1, 2]
    assert [s.case.state for s in steps] == [OPEN, FOLLOW_UP, FOLLOW_UP, FOLLOW_UP, RESOLVED]
    assert steps[-1].case.resolved_at == "S014"


# --- T8 · A raise blocks resolution (Q-25) ---


def test_e13_raise_in_force_blocks_resolution(resolution: ResolutionThresholds) -> None:
    s010, *clean = walk(
        resolution,
        obs("S010", Severity.MEDIUM, raised=True),
        obs("S011", Severity.NONE, raised=True),
        obs("S012", Severity.NONE, raised=True),
        obs("S013", Severity.NONE, raised=True),
    )
    assert (s010.case.state, s010.case.current_severity) == (ESCALATED, Severity.CRITICAL)
    assert [s.case.clean_streak for s in clean] == [1, 2, 3]
    for s in clean:
        assert (s.case.state, s.case.current_severity, s.events) == (ESCALATED, Severity.CRITICAL, ())
        assert s.case.resolved_at is None


def test_e14_lifted_raise_resolves_on_the_clean_snapshot(resolution: ResolutionThresholds) -> None:
    _, s011, s012, s013 = walk(
        resolution,
        obs("S010", Severity.MEDIUM, raised=True),
        obs("S011", Severity.NONE, raised=True),
        obs("S012", Severity.NONE, raised=True),
        obs("S013", Severity.NONE),
    )
    assert (s011.case.clean_streak, s011.case.state) == (1, ESCALATED)
    assert (s012.case.clean_streak, s012.case.state) == (2, ESCALATED)
    assert (s013.case.state, s013.case.resolved_at, s013.case.clean_streak) == (RESOLVED, "S013", 3)
    assert s013.case.current_severity is Severity.NONE
    assert s013.events == (CaseEvent.SEVERITY_CHANGED, CaseEvent.RESOLVED)


def test_e14_variant_deviation_after_the_lift_resets_the_streak(resolution: ResolutionThresholds) -> None:
    *_, s013 = walk(
        resolution,
        obs("S010", Severity.MEDIUM, raised=True),
        obs("S011", Severity.NONE, raised=True),
        obs("S012", Severity.NONE, raised=True),
        obs("S013", Severity.MEDIUM),
    )
    assert (s013.case.clean_streak, s013.case.state, s013.case.current_severity) == (
        0,
        ESCALATED,
        Severity.MEDIUM,
    )
    assert s013.events == (CaseEvent.SEVERITY_CHANGED,)


# --- T9 · New case after resolution ---


def test_e16_deviation_after_resolution_opens_a_new_case(resolution: ResolutionThresholds) -> None:
    """Characterization: passes once T3 and T7 are in; the new case is a plain opening."""
    *_, s012 = walk(
        resolution, obs("S010", Severity.MEDIUM), obs("S011", Severity.NONE), obs("S012", Severity.NONE)
    )
    assert s012.case.state is RESOLVED
    s013 = advance(None, obs("S013", Severity.MEDIUM), resolution)
    assert (s013.case.case_id, s013.case.state) == ("S013-Pickup-Brasil", OPEN)
    assert s013.events == (CaseEvent.OPENED,)


# --- T10 · Current severity on a clean snapshot (Q-26) ---


def test_e15_escalado_drops_to_ninguna_then_resolves(resolution: ResolutionThresholds) -> None:
    """Characterization: passes once T7 is in, because next_state already resolves from escalado."""
    *_, s012, s013 = walk(
        resolution,
        obs("S010", Severity.HIGH),
        obs("S011", Severity.CRITICAL),
        obs("S012", Severity.NONE),
        obs("S013", Severity.NONE),
    )
    assert (s012.case.state, s012.case.current_severity, s012.case.clean_streak) == (
        ESCALATED,
        Severity.NONE,
        1,
    )
    assert s012.case.max_severity_since_report is Severity.CRITICAL
    assert s012.events == (CaseEvent.SEVERITY_CHANGED,)
    assert s013.case.state is RESOLVED
    assert s013.events == (CaseEvent.RESOLVED,)


# --- T11 · Max severity since the last report (Q-28) ---


def test_e17_max_severity_keeps_the_peak_between_reports(resolution: ResolutionThresholds) -> None:
    s010 = advance(None, obs("S010", Severity.MEDIUM), resolution).case
    assert s010.max_severity_since_report is Severity.MEDIUM
    assert (s010.last_reported_at, s010.last_reported_state, s010.last_reported_severity) == (
        None,
        None,
        None,
    )

    marked = mark_reported(s010, "S010")
    assert (marked.last_reported_at, marked.last_reported_state, marked.last_reported_severity) == (
        "S010",
        OPEN,
        Severity.MEDIUM,
    )
    assert marked.max_severity_since_report is None

    s011 = advance(marked, obs("S011", Severity.CRITICAL), resolution).case
    assert (s011.state, s011.max_severity_since_report) == (ESCALATED, Severity.CRITICAL)

    s012 = advance(s011, obs("S012", Severity.HIGH), resolution).case
    assert (s012.current_severity, s012.max_severity_since_report) == (Severity.HIGH, Severity.CRITICAL)

    marked = mark_reported(s012, "S012")
    assert (marked.last_reported_at, marked.last_reported_state, marked.last_reported_severity) == (
        "S012",
        ESCALATED,
        Severity.HIGH,
    )
    assert marked.max_severity_since_report is None

    s013 = advance(marked, obs("S013", Severity.MEDIUM), resolution).case
    assert (s013.current_severity, s013.max_severity_since_report) == (Severity.MEDIUM, Severity.MEDIUM)


def test_e32_a_peak_reported_at_its_snapshot_is_not_in_the_next_max(resolution: ResolutionThresholds) -> None:
    s010 = advance(None, obs("S010", Severity.CRITICAL), resolution).case
    assert s010.state is ESCALATED
    marked = mark_reported(s010, "S010")
    s011 = advance(marked, obs("S011", Severity.HIGH), resolution).case
    assert (s011.current_severity, s011.max_severity_since_report) == (Severity.HIGH, Severity.HIGH)
    s012 = advance(s011, obs("S012", Severity.HIGH), resolution).case
    assert (s012.current_severity, s012.max_severity_since_report) == (Severity.HIGH, Severity.HIGH)
