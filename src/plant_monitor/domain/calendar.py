"""Shift calendar lookups from 'turnos.csv'."""

from collections.abc import Iterable
from dataclasses import dataclass

from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Shift


def snapshot_position(shifts: Iterable[Shift], snapshot_id: str) -> tuple[Shift, ShiftPosition]:
    """Shift row and position of 'snapshot_id'; ValueError naming it if it is neither mid nor closing."""
    for shift in shifts:
        if shift.snapshot_medio == snapshot_id:
            return shift, ShiftPosition.MID
        if shift.snapshot_cierre == snapshot_id:
            return shift, ShiftPosition.CLOSING
    raise ValueError(f"snapshot {snapshot_id} is neither a mid nor a closing snapshot in turnos.csv")


@dataclass(frozen=True)
class HeldOutPolicy:
    """Held-out ids derived from the calendar (FR-40, Q-37); refusals apply only while closed."""

    held_out_shifts: frozenset[str]
    held_out_snapshots: frozenset[str]
    allowed_snapshots: frozenset[str]
    is_open: bool
    known_shifts: frozenset[str]

    @classmethod
    def from_calendar(cls, shifts: Iterable[Shift], first_shift: str, is_open: bool) -> HeldOutPolicy:
        """Held out: 'first_shift' and later shifts by 'inicio'; ValueError if 'first_shift' is unknown."""
        ordered = sorted(shifts, key=lambda shift: shift.inicio)
        first = next((shift for shift in ordered if shift.turno_id == first_shift), None)
        if first is None:
            raise ValueError(f"first held-out shift {first_shift} is not in turnos.csv")
        held = [shift for shift in ordered if shift.inicio >= first.inicio]
        rest = [shift for shift in ordered if shift.inicio < first.inicio]
        return cls(
            held_out_shifts=frozenset(shift.turno_id for shift in held),
            held_out_snapshots=_snapshots(held),
            allowed_snapshots=_snapshots(rest),
            is_open=is_open,
            known_shifts=frozenset(shift.turno_id for shift in ordered),
        )

    @property
    def refused_shifts(self) -> frozenset[str]:
        """Shifts a loader must refuse: the held-out ones while closed, none while open."""
        return frozenset() if self.is_open else self.held_out_shifts

    @property
    def refused_snapshots(self) -> frozenset[str]:
        """Snapshots a loader must refuse: the held-out ones while closed, none while open."""
        return frozenset() if self.is_open else self.held_out_snapshots


def _snapshots(shifts: Iterable[Shift]) -> frozenset[str]:
    """Mid and closing snapshot ids of 'shifts'."""
    return frozenset(snap for shift in shifts for snap in (shift.snapshot_medio, shift.snapshot_cierre))
