"""Logbook store: availability by shift close, held-out refusals and verbatim citations (R2-R5)."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from plant_monitor.domain.calendar import HeldOutPolicy, closed_shifts
from plant_monitor.domain.models import Shift
from plant_monitor.domain.verbatim import contains_verbatim, normalize_whitespace
from plant_monitor.ingestion.logbooks import read_logbook_texts
from plant_monitor.logbooks.errors import (
    EmptyFragment,
    FragmentNotFound,
    LogbookHeldOut,
    LogbookNotAvailable,
    UnknownLogbook,
)

LogbookLoader = Callable[[Path, Iterable[str], HeldOutPolicy], dict[str, str]]


@dataclass(frozen=True)
class Logbook:
    """Raw logbook text of one shift, read at its closing snapshot 'closed_at'."""

    turno_id: str
    closed_at: str
    text: str


class LogbookStore:
    """Reads logbooks only through 'loader', checking availability before any load."""

    def __init__(
        self,
        directory: Path,
        shifts: Sequence[Shift],
        policy: HeldOutPolicy,
        loader: LogbookLoader = read_logbook_texts,
    ) -> None:
        self._directory = directory
        self._shifts = tuple(shifts)
        calendar_ids = frozenset(shift.turno_id for shift in self._shifts)
        if policy.known_shifts != calendar_ids:
            raise ValueError(
                f"policy and shifts disagree: only in policy {sorted(policy.known_shifts - calendar_ids)}, "
                f"only in shifts {sorted(calendar_ids - policy.known_shifts)}"
            )
        self._by_id = {shift.turno_id: shift for shift in self._shifts}
        self._policy = policy
        self._loader = loader
        self._texts: dict[str, str] = {}

    def available(self, snapshot_id: str) -> tuple[tuple[str, str], ...]:
        """(turno_id, closed_at) of the shifts closed at 'snapshot_id', minus refused ones (R2)."""
        return tuple(
            (shift.turno_id, shift.snapshot_cierre)
            for shift in closed_shifts(self._shifts, snapshot_id)
            if shift.turno_id not in self._policy.refused_shifts
        )

    def get(self, turno_id: str, snapshot_id: str) -> Logbook:
        """Logbook of 'turno_id' readable at 'snapshot_id'; checks run in R3 order, then the loader (R4)."""
        if turno_id not in self._policy.known_shifts:
            raise UnknownLogbook(turno_id)
        if turno_id in self._policy.refused_shifts:
            raise LogbookHeldOut(turno_id)
        closes_at = self._by_id[turno_id].snapshot_cierre
        if turno_id not in {shift.turno_id for shift in closed_shifts(self._shifts, snapshot_id)}:
            raise LogbookNotAvailable(turno_id, snapshot_id, closes_at)
        if turno_id not in self._texts:
            self._texts.update(self._loader(self._directory, [turno_id], self._policy))
        return Logbook(turno_id, closes_at, self._texts[turno_id])

    def verify_citation(self, turno_id: str, fragment: str, snapshot_id: str) -> None:
        """Raise unless 'fragment' is verbatim in the logbook readable at 'snapshot_id' (R5)."""
        logbook = self.get(turno_id, snapshot_id)
        if not normalize_whitespace(fragment):
            raise EmptyFragment(turno_id)
        if not contains_verbatim(logbook.text, fragment):
            raise FragmentNotFound(turno_id)
