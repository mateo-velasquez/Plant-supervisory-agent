"""Snapshot frame, fixed tool context and read-only case reader for the MCP tools (R7, R14)."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.causes import Cause, CauseCategory, CauseScope, Evidence
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.models import Combination, CombinationMetrics, Unit
from plant_monitor.domain.notices import Notice
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.metrics.engine import PlantContext


class NoticeTextWriter(Protocol):
    """Where the write tools put the agent's notice texts (R8, R9)."""

    def write_alert(self, case_id: str, texto: str) -> str:
        """Store the alert text of 'case_id' and return its notice id."""
        ...

    def write_news(self, texts: Sequence[tuple[str, str]]) -> tuple[str, ...]:
        """Store the whole report's texts atomically and return their notice ids."""
        ...

    def missing(self) -> tuple[str, ...]:
        """Required notice ids still without a text."""
        ...


@dataclass(frozen=True)
class JudgmentResult:
    """What a judgment write changed: cases, cause id, changed notices and pending ids."""

    case_ids: tuple[str, ...]
    active_cause_id: str | None
    lifted_at: str | None
    changed: tuple[Notice, ...]
    pending: tuple[str, ...]


class CauseWriter(Protocol):
    """Where 'set_cause' records a case's cited cause (R3)."""

    def set_cause(self, case_id: str, cause: Cause, evidence: Evidence) -> JudgmentResult:
        """Store the cited cause of 'case_id' and re-decide the snapshot."""
        ...


class RaiseWriter(Protocol):
    """Where the severity raises are opened and lifted (R5, R9)."""

    def raise_severity(
        self, categoria: CauseCategory, scope: CauseScope, evidence: Evidence
    ) -> JudgmentResult:
        """Open an active cause over 'scope' and re-decide the snapshot."""
        ...

    def lift(self, active_cause_id: str, evidence: Evidence) -> JudgmentResult:
        """Lift an active cause and re-decide the snapshot."""
        ...


class FrameWriter(NoticeTextWriter, CauseWriter, RaiseWriter, Protocol):
    """The three writers of one snapshot, held by a single object."""


@dataclass(frozen=True)
class SnapshotFrame:
    """Snapshot being processed: its id, timestamp, metrics, units and writers."""

    snapshot_id: str
    at: datetime
    metrics: Mapping[Combination, CombinationMetrics]
    units: tuple[Unit, ...]
    notices: NoticeTextWriter | None = None
    causes: CauseWriter | None = None
    raises: RaiseWriter | None = None

    @classmethod
    def with_writer(
        cls,
        snapshot_id: str,
        at: datetime,
        metrics: Mapping[Combination, CombinationMetrics],
        units: tuple[Unit, ...],
        writer: FrameWriter,
    ) -> SnapshotFrame:
        """A frame whose notice, cause and raise slots hold the same writer."""
        return cls(snapshot_id, at, metrics, units, writer, writer, writer)


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
