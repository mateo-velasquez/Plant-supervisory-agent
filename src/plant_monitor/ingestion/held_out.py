"""Held-out guard for loaders: refuses shift and snapshot ids the policy withholds (FR-40, Q-37)."""

from collections.abc import Iterable

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.ingestion.errors import DataLoadError


def check_ids(policy: HeldOutPolicy, *, shifts: Iterable[str], snapshots: Iterable[str], where: str) -> None:
    """Raise DataLoadError naming 'where' and the first refused id in sorted order, if any."""
    refused_shifts = policy.refused_shifts
    refused_snapshots = policy.refused_snapshots
    held = sorted(
        {shift for shift in shifts if shift in refused_shifts}
        | {snapshot for snapshot in snapshots if snapshot in refused_snapshots}
    )
    if held:
        raise DataLoadError(f"{where}: {held[0]} is held out")
