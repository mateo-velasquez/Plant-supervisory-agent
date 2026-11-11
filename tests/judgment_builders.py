"""008 builders: a tool context over the incident fixture and a recording fake judgment writer."""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from incident_builders import INCIDENTS, incident_context
from incident_runs import EV_T05
from mcp_builders import EmptyCases

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.causes import Cause, CauseCategory, CauseScope, Evidence
from plant_monitor.domain.notices import Notice
from plant_monitor.ingestion.logbooks import read_logbook_texts
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.mcp_server.context import FrameHolder, JudgmentResult, SnapshotFrame, ToolContext

PL_CASE = "S010-Pickup-Local"
PB_CASE = "S010-Pickup-Brasil"
AC2 = "S010-causa-1"


def incident_tool_context(directory: Path = INCIDENTS / "bitacoras") -> tuple[ToolContext, FrameHolder]:
    """Tool context over the IF calendar (T01-T06) and the logbooks in 'directory', open policy."""
    plant = incident_context()
    policy = HeldOutPolicy.from_calendar(plant.shifts, "T06", True)
    ctx = ToolContext(
        plant=plant,
        cases=EmptyCases(),
        logbooks=LogbookStore(directory, plant.shifts, policy, read_logbook_texts),
        view_max_chars=4000,
        logbook_max_chars=100_000,
    )
    return ctx, FrameHolder()


class FakeJudgment:
    """Records judgment writes and answers a fixed 'JudgmentResult'; it also fakes the notice writer."""

    def __init__(self, result: JudgmentResult | None = None) -> None:
        self.result = result or JudgmentResult(
            case_ids=(), active_cause_id=None, lifted_at=None, changed=(), pending=()
        )
        self.calls: list[tuple[object, ...]] = []

    def set_cause(self, case_id: str, cause: Cause, evidence: Evidence) -> JudgmentResult:
        """Record the call."""
        self.calls.append(("set_cause", case_id, cause, evidence))
        return self.result

    def raise_severity(
        self, categoria: CauseCategory, scope: CauseScope, evidence: Evidence
    ) -> JudgmentResult:
        """Record the call."""
        self.calls.append(("raise_severity", categoria, scope, evidence))
        return self.result

    def lift(self, active_cause_id: str, evidence: Evidence) -> JudgmentResult:
        """Record the call."""
        self.calls.append(("lift", active_cause_id, evidence))
        return self.result

    def write_alert(self, case_id: str, texto: str) -> str:
        """Unused by judgment tests."""
        raise AssertionError("not expected")

    def write_news(self, texts: Sequence[tuple[str, str]]) -> tuple[str, ...]:
        """Unused by judgment tests."""
        raise AssertionError("not expected")

    def missing(self) -> tuple[str, ...]:
        """Unused by judgment tests."""
        return ()


def result_of(
    *,
    case_ids: tuple[str, ...] = (),
    active_cause_id: str | None = None,
    lifted_at: str | None = None,
    changed: tuple[Notice, ...] = (),
    pending: tuple[str, ...] = (),
) -> JudgmentResult:
    """A 'JudgmentResult' with the given fields."""
    return JudgmentResult(
        case_ids=case_ids,
        active_cause_id=active_cause_id,
        lifted_at=lifted_at,
        changed=changed,
        pending=pending,
    )


def bare_frame(snapshot_id: str) -> SnapshotFrame:
    """Metric-less frame at 'snapshot_id' with no writer at all."""
    return SnapshotFrame(snapshot_id=snapshot_id, at=datetime(2026, 3, 3, 8, 0), metrics={}, units=())


__all__ = [
    "AC2",
    "EV_T05",
    "PB_CASE",
    "PL_CASE",
    "FakeJudgment",
    "bare_frame",
    "incident_tool_context",
    "result_of",
]
