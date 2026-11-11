"""Shift logbook texts ('<turno_id>.txt'), loaded through the held-out guard (FR-40, Q-37)."""

from collections.abc import Iterable
from pathlib import Path

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.ingestion.errors import DataLoadError
from plant_monitor.ingestion.held_out import check_ids


class LogbookFileMissing(DataLoadError):
    """The shift is known and allowed but its '<turno_id>.txt' does not exist."""


def read_logbook_texts(directory: Path, turno_ids: Iterable[str], policy: HeldOutPolicy) -> dict[str, str]:
    """Texts of '<turno_id>.txt' ('utf-8-sig'); unknown or refused ids fail before any file opens."""
    ids = list(turno_ids)
    for turno_id in ids:
        if turno_id not in policy.known_shifts:
            raise DataLoadError(f"{directory}: {turno_id!r} is not a known shift")
    check_ids(policy, shifts=ids, snapshots=[], where=str(directory))
    texts: dict[str, str] = {}
    for turno_id in ids:
        path = directory / f"{turno_id}.txt"
        if not path.is_file():
            raise LogbookFileMissing(f"{path}: logbook not found")
        with path.open(encoding="utf-8-sig") as handle:
            texts[turno_id] = handle.read()
    return texts
