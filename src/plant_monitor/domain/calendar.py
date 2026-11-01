"""Shift calendar lookups from `turnos.csv`."""

from collections.abc import Iterable

from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Shift


def snapshot_position(shifts: Iterable[Shift], snapshot_id: str) -> tuple[Shift, ShiftPosition]:
    """Shift row and position of `snapshot_id`; ValueError naming it if it is neither mid nor closing."""
    for shift in shifts:
        if shift.snapshot_medio == snapshot_id:
            return shift, ShiftPosition.MID
        if shift.snapshot_cierre == snapshot_id:
            return shift, ShiftPosition.CLOSING
    raise ValueError(f"snapshot {snapshot_id} is neither a mid nor a closing snapshot in turnos.csv")
