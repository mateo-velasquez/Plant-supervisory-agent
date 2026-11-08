"""Minimal builders for 006 tool tests: a tool context over the fixture plant and logbooks."""

from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.models import Combination, CombinationMetrics, Unit
from plant_monitor.ingestion.logbooks import read_logbook_texts
from plant_monitor.logbooks.store import LogbookLoader, LogbookStore
from plant_monitor.mcp_server.context import CaseReader, FrameHolder, SnapshotFrame, ToolContext

from builders import held_out_policy
from notice_builders import plant_context

LOGBOOKS = Path(__file__).resolve().parent / "fixtures" / "bitacoras"


class EmptyCases:
    """Case reader with no cases."""

    def active_cases(self) -> tuple[Case, ...]:
        """No active cases."""
        return ()

    def get_case(self, case_id: str) -> Case | None:
        """No case."""
        return None

    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]:
        """No history."""
        return ()


class SpyLoader:
    """Loader that records calls and serves the fixture texts."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, directory: Path, turno_ids: Iterable[str], policy: HeldOutPolicy) -> dict[str, str]:
        ids = list(turno_ids)
        self.calls.append(ids)
        return {i: (LOGBOOKS / f"{i}.txt").read_text(encoding="utf-8") for i in ids}


class StaticCases:
    """Case reader over fixed cases and per-case history (oldest first)."""

    def __init__(
        self, cases: Iterable[Case], history: Mapping[str, tuple[CaseHistoryRow, ...]] | None = None
    ) -> None:
        self._cases = {case.case_id: case for case in cases}
        self._history = dict(history or {})

    def active_cases(self) -> tuple[Case, ...]:
        """Cases whose state is not 'resuelto'."""
        return tuple(case for case in self._cases.values() if case.resolved_at is None)

    def get_case(self, case_id: str) -> Case | None:
        """The case with 'case_id', or None."""
        return self._cases.get(case_id)

    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]:
        """History rows of 'case_id', oldest first."""
        return self._history.get(case_id, ())


def frame_at(snapshot_id: str) -> SnapshotFrame:
    """Frame with no metrics or units at 'snapshot_id'."""
    return SnapshotFrame(snapshot_id=snapshot_id, at=datetime(2026, 3, 2, 18, 0), metrics={}, units=())


def frame_with(
    snapshot_id: str,
    metrics: Mapping[Combination, CombinationMetrics],
    units: tuple[Unit, ...] = (),
) -> SnapshotFrame:
    """Frame at 'snapshot_id' (2026-03-02T18:00) with the given metrics and units."""
    return SnapshotFrame(
        snapshot_id=snapshot_id, at=datetime(2026, 3, 2, 18, 0), metrics=metrics, units=units
    )


def tool_context(
    policy: HeldOutPolicy | None = None,
    *,
    directory: Path = LOGBOOKS,
    loader: LogbookLoader = read_logbook_texts,
    logbook_max_chars: int = 100_000,
    cases: CaseReader | None = None,
) -> tuple[ToolContext, FrameHolder]:
    """Tool context over the fixture calendar (open policy by default) and an empty frame holder."""
    plant = plant_context()
    chosen = policy if policy is not None else held_out_policy(is_open=True)
    ctx = ToolContext(
        plant=plant,
        cases=cases if cases is not None else EmptyCases(),
        logbooks=LogbookStore(directory, plant.shifts, chosen, loader),
        view_max_chars=4000,
        logbook_max_chars=logbook_max_chars,
    )
    return ctx, FrameHolder()
