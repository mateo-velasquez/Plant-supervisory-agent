"""016 T2: the pure gap forecast through 'forecast_snapshot' (R2-R7, E1-E9, X2, X6)."""

import pytest
from forecast_builders import SB, P, closed_calendar, fc, of, plan_rows

from plant_monitor.domain.enums import Severity
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import all_combinations

E1_PROGRESS = (92, 52)
"""prog(8) and prog(4) of the spec's E1."""


def gaps(row: ForecastRow) -> list[float]:
    """Projected gaps of the row's points."""
    return [point.gap_units for point in row.points]


def test_e1_constant_plan_crossing() -> None:
    rows = fc(8, *E1_PROGRESS, plan=plan_rows(24))
    assert [row.combination for row in rows] == list(all_combinations())
    row = of(rows)
    assert (row.gap_units, row.gap_severity, row.status, row.target_level) == (
        -4.0,
        Severity.NONE,
        "warning",
        Severity.MEDIUM,
    )
    assert row.thresholds is not None
    assert (row.thresholds.media, row.thresholds.alta, row.thresholds.critica) == pytest.approx(
        (7.2, 14.4, 25.2)
    )
    assert row.basis is not None
    assert (row.basis.rate, row.basis.window_first, row.basis.window_last) == (10.0, "S005", "S008")
    assert (row.basis.points, row.basis.horizon, row.basis.plan_per_snapshot) == (4, 3, 12.0)
    assert [point.snapshot_id for point in row.points] == ["S009", "S010", "S011"]
    assert [point.scheduled_at.strftime("%H:%M") for point in row.points] == ["18:00", "22:00", "02:00"]
    assert gaps(row) == [-6.0, -8.0, -10.0]
    assert row.warning is not None
    assert (row.warning.target_level, row.warning.crossing_snapshot_id, row.warning.hours) == (
        Severity.MEDIUM,
        "S010",
        8.0,
    )
    for other in rows:
        if other.combination != P:
            assert (other.status, other.thresholds) == ("no_crossing", None)


def test_e2_plan_change_is_read_from_the_plan_not_the_gap_line() -> None:
    row = of(fc(8, *E1_PROGRESS, plan=plan_rows(24, overrides={"T05": 12})))
    assert gaps(row) == [0.0, 4.0, 2.0]
    assert row.status == "no_crossing"
    assert row.basis is not None
    assert row.basis.plan_per_snapshot == 8.0


def test_e3_shift_with_plan_zero_has_no_gap_pct_and_no_crossing_inside_it() -> None:
    row = of(fc(9, 86, 78, plan=plan_rows(24, overrides={"T05": 0})))
    assert (row.gap_units, row.gap_severity, row.thresholds, row.target_level) == (
        -10.0,
        Severity.NONE,
        None,
        Severity.MEDIUM,
    )
    assert row.basis is not None
    assert row.basis.rate == 2.0
    assert gaps(row) == [-8.0, -18.0, -28.0]
    assert row.points[0].thresholds is None
    assert row.points[1].thresholds is not None
    assert row.warning is not None
    assert (row.warning.crossing_snapshot_id, row.warning.hours, row.warning.target_level) == (
        "S011",
        8.0,
        Severity.MEDIUM,
    )


def test_e4_minimum_units_block_a_crossing() -> None:
    row = of(fc(8, 15, 9, plan=plan_rows(4, combo=SB), combo=SB), SB)
    assert row.gap_units == -1.0
    assert row.basis is not None
    assert row.basis.rate == 1.5
    assert gaps(row) == [-1.5, -2.0, -2.5]
    assert row.status == "no_crossing"
    assert row.thresholds is not None
    assert (row.thresholds.media, row.thresholds.alta, row.thresholds.critica) == pytest.approx(
        (3.0, 3.0, 4.2)
    )


def test_e5_recovering_trend_has_no_crossing() -> None:
    row = of(fc(8, 91, 39, plan=plan_rows(24)))
    assert row.gap_units == -5.0
    assert row.basis is not None
    assert row.basis.rate == 13.0
    assert gaps(row) == [-4.0, -3.0, -2.0]
    assert row.status == "no_crossing"


def test_e6_the_window_must_be_full() -> None:
    plan = plan_rows(24)
    warm = fc(11, 132, None, plan=plan, window=12)
    assert len(warm) == 9
    assert all(row.status == "warm_up" and row.points == () and row.basis is None for row in warm)
    row = of(fc(12, 144, 0, plan=plan, window=12))
    assert row.status == "no_crossing"
    assert row.basis is not None
    assert (row.basis.rate, row.basis.window_first, row.basis.window_last, row.basis.points) == (
        12.0,
        "S001",
        "S012",
        12,
    )


@pytest.mark.parametrize(
    ("progress", "raised", "delay", "status", "effective", "expected_gaps"),
    [
        pytest.param(
            (86, 50), False, Severity.NONE, "warning", Severity.MEDIUM, [-13.0, -16.0, -19.0], id="a"
        ),
        pytest.param(
            (86, 50), True, Severity.NONE, "suppressed", Severity.CRITICAL, [-13.0, -16.0, -19.0], id="b"
        ),
        pytest.param(
            E1_PROGRESS, False, Severity.HIGH, "suppressed", Severity.HIGH, [-6.0, -8.0, -10.0], id="c_x2"
        ),
    ],
)
def test_e7_effective_severity_suppresses_the_warning(
    progress: tuple[int, int],
    raised: bool,
    delay: Severity,
    status: str,
    effective: Severity,
    expected_gaps: list[float],
) -> None:
    rows = fc(8, *progress, plan=plan_rows(24), raised=frozenset({P}) if raised else frozenset(), delay=delay)
    row = of(rows)
    assert (row.status, row.effective_severity, gaps(row)) == (status, effective, expected_gaps)
    if status == "warning":
        assert (row.gap_units, row.gap_severity, row.target_level) == (-10.0, Severity.MEDIUM, Severity.HIGH)
        assert row.warning is not None
        assert (row.warning.target_level, row.warning.crossing_snapshot_id) == (Severity.HIGH, "S010")
    else:
        assert row.warning is None


def test_e8_gap_already_critical_has_no_target() -> None:
    row = of(fc(8, 69, 41, plan=plan_rows(24)))
    assert (row.gap_units, row.gap_severity, row.status, row.target_level) == (
        -27.0,
        Severity.CRITICAL,
        "no_target",
        None,
    )
    assert row.basis is not None
    assert row.basis.rate == 7.0
    assert len(row.points) == 3


def test_e9_held_out_boundary_truncates_the_horizon_at_write_time() -> None:
    closed = closed_calendar("T06")
    near = of(fc(8, *E1_PROGRESS, plan=plan_rows(24), calendar=closed))
    assert [point.snapshot_id for point in near.points] == ["S009", "S010"]
    assert near.warning is not None
    assert near.warning.crossing_snapshot_id == "S010"
    edge = of(fc(10, 112, 88, plan=plan_rows(24), calendar=closed))
    assert (edge.points, edge.status) == ((), "no_crossing")
    named = {point.snapshot_id for row in (near, edge) for point in row.points}
    assert not named & {"S011", "S012"}
    assert len(of(fc(8, *E1_PROGRESS, plan=plan_rows(24))).points) == 3


def test_x6_a_projected_gap_exactly_on_a_threshold_is_a_crossing() -> None:
    row = of(fc(8, 80, 64, plan=plan_rows(20)))
    assert gaps(row)[0] == -6.0
    assert row.warning is not None
    assert (row.warning.crossing_snapshot_id, row.warning.target_level) == ("S009", Severity.MEDIUM)
