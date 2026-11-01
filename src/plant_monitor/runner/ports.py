"""Ports the series runner depends on; implementations live outside `runner`."""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Protocol

from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Anomaly, Combination, Shift, Snapshot, SnapshotCommit


class ProcessedStore(Protocol):
    """Idempotency marks, unit identity and anomalies of the processed snapshots."""

    def get_hash(self, snapshot_id: str) -> str | None: ...

    def known_units(self) -> Mapping[str, Combination]:
        """First-seen combination per unit; empty when fresh."""
        ...

    def record_anomaly(self, anomaly: Anomaly) -> None:
        """Record an anomaly on the skip path (Q-10, different hash)."""
        ...

    def processing(self, commit: SnapshotCommit) -> AbstractContextManager[None]:
        """Unit of work: a clean exit records hash, anomalies and new units atomically; an exception, nothing.

        Every registry write for this snapshot must use the same connection inside this block; the
        composition root passes one store instance to the runner and the pipeline. Raises ValueError
        on entry if `commit.snapshot_id` is already marked.
        """
        ...


class SnapshotPipeline(Protocol):
    """Processes one snapshot inside the store's unit of work."""

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        """Side effects outside the database (notifier delivery) must happen only after the commit."""
        ...
