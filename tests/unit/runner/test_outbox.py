"""004 T10: the outbox dispatcher delivers pending notices in order and survives failures (E35)."""

import logging
import sqlite3
from datetime import UTC, datetime

import pytest

from plant_monitor.domain.notices import Notice, PendingDelivery, ShiftReport
from plant_monitor.runner.outbox import OutboxDispatcher

from notice_builders import SEDAN_LOCAL_CASE, alert_notice, shift_report

LOGGER = "plant_monitor.runner.outbox"
CLOCK_TIME = datetime(2026, 3, 2, 18, 0, tzinfo=UTC)
REPORT = shift_report("T01", "S002")
ALERT = alert_notice("S003", SEDAN_LOCAL_CASE)
PENDING = (PendingDelivery("T01-informe", REPORT), PendingDelivery(ALERT.notice_id, ALERT))

type Event = tuple[str, str]


class FakeStore:
    """Pending items in a fixed order; records every mark into the shared event log."""

    def __init__(
        self,
        events: list[Event],
        marks: list[tuple[str, datetime]],
        *,
        pending_error: Exception | None = None,
        mark_error: Exception | None = None,
    ) -> None:
        self.events = events
        self.marks = marks
        self.pending_error = pending_error
        self.mark_error = mark_error

    def pending(self) -> tuple[PendingDelivery, ...]:
        if self.pending_error is not None:
            raise self.pending_error
        return PENDING

    def mark_delivered(self, notice_id: str, at: datetime) -> None:
        self.events.append(("mark", notice_id))
        if self.mark_error is not None:
            raise self.mark_error
        self.marks.append((notice_id, at))


class FakeNotifier:
    """Records every send into the shared event log; raises 'error' when sending a report."""

    def __init__(self, events: list[Event], *, report_error: BaseException | None = None) -> None:
        self.events = events
        self.report_error = report_error

    def alert(self, notice: Notice) -> None:
        self.events.append(("alert", notice.notice_id))

    def report(self, report: ShiftReport) -> None:
        self.events.append(("report", f"{report.turno_id}-informe"))
        if self.report_error is not None:
            raise self.report_error


class Rig:
    """A dispatcher over a fake store and notifier, with the events they share."""

    def __init__(
        self,
        *,
        report_error: BaseException | None = None,
        mark_error: Exception | None = None,
        pending_error: Exception | None = None,
    ) -> None:
        self.events: list[Event] = []
        self.marks: list[tuple[str, datetime]] = []
        store = FakeStore(self.events, self.marks, pending_error=pending_error, mark_error=mark_error)
        notifier = FakeNotifier(self.events, report_error=report_error)
        self.dispatcher = OutboxDispatcher(store, notifier, lambda: CLOCK_TIME)


def errors(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Messages the dispatcher logged at ERROR."""
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == logging.ERROR]


def test_e35a_healthy_flush_sends_then_marks_each_item_in_order_with_the_clock_time(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig()
    rig.dispatcher.after_commit()
    assert rig.events == [
        ("report", "T01-informe"),
        ("mark", "T01-informe"),
        ("alert", ALERT.notice_id),
        ("mark", ALERT.notice_id),
    ]
    assert rig.marks == [("T01-informe", CLOCK_TIME), (ALERT.notice_id, CLOCK_TIME)]
    assert errors(caplog) == []


def test_e35a_flush_returns_the_number_delivered() -> None:
    assert Rig().dispatcher.flush() == 2
    assert Rig(report_error=RuntimeError("boom")).dispatcher.flush() == 0


def test_e35b_a_notifier_failure_logs_names_the_notice_marks_nothing_and_stops(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig(report_error=RuntimeError("boom"))
    rig.dispatcher.after_commit()
    assert rig.events == [("report", "T01-informe")]
    assert rig.marks == []
    (message,) = errors(caplog)
    assert "T01-informe" in message


def test_e35c_keyboard_interrupt_from_the_notifier_propagates_and_marks_nothing() -> None:
    rig = Rig(report_error=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        rig.dispatcher.after_commit()
    assert rig.marks == []
    assert rig.events == [("report", "T01-informe")]


def test_e35d_a_mark_failure_logs_once_and_leaves_the_rest_unattempted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    rig = Rig(mark_error=sqlite3.OperationalError("database is locked"))
    rig.dispatcher.after_commit()
    assert rig.events == [("report", "T01-informe"), ("mark", "T01-informe")]
    assert rig.marks == []
    (message,) = errors(caplog)
    assert "T01-informe" in message


def test_e35e_a_pending_failure_logs_once_and_calls_no_notifier(caplog: pytest.LogCaptureFixture) -> None:
    rig = Rig(pending_error=sqlite3.OperationalError("database is locked"))
    rig.dispatcher.after_commit()
    assert rig.events == []
    assert len(errors(caplog)) == 1


def test_default_clock_gives_timezone_aware_times() -> None:
    """A naive default would make the store reject every mark, so no notice would ever be delivered."""
    events: list[Event] = []
    marks: list[tuple[str, datetime]] = []
    OutboxDispatcher(FakeStore(events, marks), FakeNotifier(events)).after_commit()
    assert len(marks) == 2
    assert all(at.utcoffset() is not None for _, at in marks)
