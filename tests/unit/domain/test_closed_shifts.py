"""006 T3: shift closure by calendar order (R1, E1, E2)."""

from datetime import datetime, timedelta
from pathlib import Path
from random import Random

import pytest

from plant_monitor.domain.calendar import closed_shifts
from plant_monitor.domain.models import Shift
from plant_monitor.ingestion.plant import load_shifts

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"


def ids(shifts: tuple[Shift, ...]) -> tuple[str, ...]:
    """Shift ids in order."""
    return tuple(shift.turno_id for shift in shifts)


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ("S001", ()),
        ("S002", ("T01",)),
        ("S003", ("T01",)),
        ("S004", ("T01", "T02")),
        ("S005", ("T01", "T02")),
        ("S006", ("T01", "T02", "T03")),
    ],
)
def test_e1_closed_shifts_over_the_fixture_timeline(snapshot: str, expected: tuple[str, ...]) -> None:
    """E1: a shift is closed once its closing snapshot is reached."""
    shifts = load_shifts(FIXTURES / "turnos.csv")
    assert ids(closed_shifts(shifts, snapshot)) == expected


def test_e1_unknown_snapshot_raises_value_error() -> None:
    """E1: S007 is not in the calendar."""
    with pytest.raises(ValueError, match="S007"):
        closed_shifts(load_shifts(FIXTURES / "turnos.csv"), "S007")


@pytest.mark.parametrize(
    ("shift_id", "before", "at"),
    [("T07", "S013", "S014"), ("T10", "S019", "S020")],
)
def test_e2_synthetic_calendar_with_shuffled_rows(shift_id: str, before: str, at: str) -> None:
    """E2: order comes from 'inicio', not from row order."""
    start = datetime(2026, 3, 1, 6, 0)
    shifts = [
        Shift(
            turno_id=f"T{n:02d}",
            inicio=start + timedelta(hours=16 * (n - 1)),
            fin=start + timedelta(hours=16 * n),
            snapshot_medio=f"S{2 * n - 1:03d}",
            snapshot_cierre=f"S{2 * n:03d}",
        )
        for n in range(1, 11)
    ]
    Random(7).shuffle(shifts)
    assert shift_id not in ids(closed_shifts(shifts, before))
    assert shift_id in ids(closed_shifts(shifts, at))
