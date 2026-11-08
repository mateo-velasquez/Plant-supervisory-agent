"""005 T2: 'HeldOutPolicy' derives held-out ids from the calendar (E4, FR-40, Q-37)."""

from pathlib import Path

import pytest

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.models import Shift
from plant_monitor.ingestion.plant import load_shifts

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"


def shift_row(shifts: list[Shift], shift_id: str) -> Shift:
    """The fixture row of 'shift_id'."""
    return next(shift for shift in shifts if shift.turno_id == shift_id)


@pytest.fixture
def shifts() -> list[Shift]:
    """Fixture turnos.csv (T01 to T03)."""
    return load_shifts(FIXTURES / "turnos.csv")


@pytest.fixture
def unordered(shifts: list[Shift]) -> list[Shift]:
    """Fixture shifts listed as T03, T01, T02: order must come from 'inicio'."""
    return [shift_row(shifts, "T03"), shift_row(shifts, "T01"), shift_row(shifts, "T02")]


def test_e4_a_closed_policy_from_t03(unordered: list[Shift]) -> None:
    policy = HeldOutPolicy.from_calendar(unordered, "T03", is_open=False)
    assert policy.held_out_shifts == {"T03"}
    assert policy.held_out_snapshots == {"S005", "S006"}
    assert policy.allowed_snapshots == {"S001", "S002", "S003", "S004"}
    assert policy.refused_shifts == {"T03"}
    assert policy.refused_snapshots == {"S005", "S006"}
    assert policy.is_open is False


def test_e4_b_closed_policy_from_t02_includes_later_shifts(unordered: list[Shift]) -> None:
    policy = HeldOutPolicy.from_calendar(unordered, "T02", is_open=False)
    assert policy.held_out_shifts == {"T02", "T03"}
    assert policy.held_out_snapshots == {"S003", "S004", "S005", "S006"}
    assert policy.allowed_snapshots == {"S001", "S002"}


def test_e4_c_open_policy_keeps_sets_but_refuses_nothing(unordered: list[Shift]) -> None:
    policy = HeldOutPolicy.from_calendar(unordered, "T03", is_open=True)
    assert policy.held_out_shifts == {"T03"}
    assert policy.held_out_snapshots == {"S005", "S006"}
    assert policy.allowed_snapshots == {"S001", "S002", "S003", "S004"}
    assert policy.refused_shifts == frozenset()
    assert policy.refused_snapshots == frozenset()


def test_e4_d_unknown_first_shift_raises_naming_it(unordered: list[Shift]) -> None:
    with pytest.raises(ValueError, match="T09"):
        HeldOutPolicy.from_calendar(unordered, "T09", is_open=False)
