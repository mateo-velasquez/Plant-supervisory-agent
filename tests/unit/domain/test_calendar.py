"""002 T1: snapshot position in the shift calendar, moved from metrics.plan (E20, FR-04)."""

from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.calendar import future_snapshots, scheduled_time, snapshot_position
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Shift
from plant_monitor.ingestion.plant import load_shifts

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"


@pytest.fixture
def shifts() -> list[Shift]:
    """Fixture turnos.csv (T01 to T03)."""
    return load_shifts(FIXTURES / "turnos.csv")


def shift_row(shifts: list[Shift], shift_id: str) -> Shift:
    """The fixture row of 'shift_id'."""
    return next(shift for shift in shifts if shift.turno_id == shift_id)


def test_e20_s001_is_t01_mid(shifts: list[Shift]) -> None:
    assert snapshot_position(shifts, "S001") == (shift_row(shifts, "T01"), ShiftPosition.MID)


def test_e20_s002_is_t01_closing(shifts: list[Shift]) -> None:
    assert snapshot_position(shifts, "S002") == (shift_row(shifts, "T01"), ShiftPosition.CLOSING)


def test_e20_s003_is_t02_mid(shifts: list[Shift]) -> None:
    assert snapshot_position(shifts, "S003") == (shift_row(shifts, "T02"), ShiftPosition.MID)


@pytest.mark.parametrize(
    ("snapshot_id", "shift_id", "position"),
    [
        ("S001", "T01", ShiftPosition.MID),
        ("S002", "T01", ShiftPosition.CLOSING),
        ("S003", "T02", ShiftPosition.MID),
        ("S004", "T02", ShiftPosition.CLOSING),
        ("S005", "T03", ShiftPosition.MID),
        ("S006", "T03", ShiftPosition.CLOSING),
    ],
)
def test_snapshot_position_for_every_fixture_snapshot(
    shifts: list[Shift], snapshot_id: str, shift_id: str, position: ShiftPosition
) -> None:
    shift, found = snapshot_position(shifts, snapshot_id)
    assert shift == shift_row(shifts, shift_id)
    assert found is position


def test_snapshot_position_returns_the_full_shift_row(shifts: list[Shift]) -> None:
    shift, _ = snapshot_position(shifts, "S004")
    assert shift.turno_id == "T02"
    assert shift.snapshot_medio == "S003"
    assert shift.snapshot_cierre == "S004"


def test_e20_unknown_snapshot_raises_naming_it(shifts: list[Shift]) -> None:
    with pytest.raises(ValueError, match="S999"):
        snapshot_position(shifts, "S999")


def test_snapshot_position_accepts_a_one_shot_iterator(shifts: list[Shift]) -> None:
    assert snapshot_position(iter(shifts), "S006") == (shift_row(shifts, "T03"), ShiftPosition.CLOSING)


@pytest.mark.parametrize(
    ("position", "expected"),
    [(ShiftPosition.MID, datetime(2026, 3, 2, 10, 0)), (ShiftPosition.CLOSING, datetime(2026, 3, 2, 14, 0))],
)
def test_r4_scheduled_time_is_the_middle_or_the_end_of_the_shift(
    shifts: list[Shift], position: ShiftPosition, expected: datetime
) -> None:
    """016 T1 (R4; E1): mid is 'inicio' plus half the shift, closing is 'fin'."""
    assert scheduled_time(shift_row(shifts, "T01"), position) == expected


@pytest.mark.parametrize(
    ("snapshot_id", "horizon", "expected"),
    [
        pytest.param("S002", 3, ["S003", "S004", "S005"], id="full_horizon"),
        pytest.param("S001", 1, ["S002"], id="closing_follows_mid"),
        pytest.param("S005", 3, ["S006"], id="truncated_at_the_end"),
        pytest.param("S006", 3, [], id="none_remain"),
    ],
)
def test_r4_future_snapshots_follow_calendar_order_and_truncate(
    shifts: list[Shift], snapshot_id: str, horizon: int, expected: list[str]
) -> None:
    """016 T1 (R4; E1, E9): the next 'horizon' snapshots in calendar order, whatever the input order."""
    found = future_snapshots(reversed(shifts), snapshot_id, horizon)
    assert [snapshot for _, _, snapshot in found] == expected


def test_r4_future_snapshots_carry_shift_and_position(shifts: list[Shift]) -> None:
    """016 T1 (R4): each entry is '(shift, position, snapshot_id)'."""
    assert future_snapshots(shifts, "S002", 2) == (
        (shift_row(shifts, "T02"), ShiftPosition.MID, "S003"),
        (shift_row(shifts, "T02"), ShiftPosition.CLOSING, "S004"),
    )


def test_r4_future_snapshots_unknown_snapshot_raises_naming_it(shifts: list[Shift]) -> None:
    """016 T1 (R4): as 'snapshot_position', an unknown id is a 'ValueError' naming it."""
    with pytest.raises(ValueError, match="S999"):
        future_snapshots(shifts, "S999", 3)
