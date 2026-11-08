"""Snapshot frame, fixed tool context and read-only case reader for the MCP tools (R7, R14)."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.models import Combination, CombinationMetrics, Unit
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.metrics.engine import PlantContext


@dataclass(frozen=True)
class SnapshotFrame:
    """Snapshot being processed: its id, timestamp, metrics and units."""

    snapshot_id: str
    at: datetime
    metrics: Mapping[Combination, CombinationMetrics]
    units: tuple[Unit, ...]


class NoCurrentSnapshot(RejectedRequest):
    """A tool was called outside a snapshot frame."""

    def __init__(self) -> None:
        super().__init__("no snapshot is being processed")


class UnknownCase(RejectedRequest):
    """A case id that the registry does not know."""

    def __init__(self, case_id: str) -> None:
        super().__init__(f"unknown case {case_id}")


class FrameHolder:
    """Holds the frame of the snapshot being processed; the model never supplies it (R7)."""

    def __init__(self) -> None:
        self._frame: SnapshotFrame | None = None

    def current(self) -> SnapshotFrame:
        """The entered frame; NoCurrentSnapshot outside one."""
        if self._frame is None:
            raise NoCurrentSnapshot()
        return self._frame

    @contextmanager
    def entered(self, frame: SnapshotFrame) -> Iterator[None]:
        """Enter 'frame' for the duration of the block; nesting is a ValueError to the code."""
        if self._frame is not None:
            raise ValueError("a snapshot frame is already entered")
        self._frame = frame
        try:
            yield
        finally:
            self._frame = None


class CaseReader(Protocol):
    """Read-only view of the case registry (R14)."""

    def active_cases(self) -> tuple[Case, ...]:
        """Cases that are still active in the registry."""
        ...

    def get_case(self, case_id: str) -> Case | None:
        """The case with 'case_id', or None."""
        ...

    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]:
        """Per-snapshot history rows of 'case_id', oldest first."""
        ...


@dataclass(frozen=True)
class ToolContext:
    """Fixed per run: plant data, read-only stores and the output budgets."""

    plant: PlantContext
    cases: CaseReader
    logbooks: LogbookStore
    view_max_chars: int
    logbook_max_chars: int
