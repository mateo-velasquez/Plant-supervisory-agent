"""002 T1: snapshot position in the shift calendar, moved from metrics.plan (E20, FR-04)."""

from pathlib import Path

import pytest

from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Shift
from plant_monitor.ingestion.plant import load_shifts

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"


@pytest.fixture
def shifts() -> list[Shift]:
    """Fixture turnos.csv (T01 to T03)."""
    return load_shifts(FIXTURES / "turnos.csv")


def shift_row(shifts: list[Shift], shift_id: str) -> Shift:
    """The fixture row of `shift_id`."""
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
