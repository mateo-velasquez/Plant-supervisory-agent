"""Outbox dispatcher: delivers stored notices after each commit (ADR-0010)."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from plant_monitor.domain.notices import PendingDelivery, ShiftReport
from plant_monitor.notify.port import Notifier

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


class PendingNotices(Protocol):
    """What the dispatcher needs from the notice store; SqliteNoticeStore satisfies it structurally."""

    def pending(self) -> tuple[PendingDelivery, ...]: ...

    def mark_delivered(self, notice_id: str, at: datetime) -> None: ...


class OutboxDispatcher:
    """Delivers pending notices in order after each commit (ADR-0010); implements PostCommit."""

    def __init__(
        self, notices: PendingNotices, notifier: Notifier, clock: Callable[[], datetime] = _utc_now
    ) -> None:
        self._notices = notices
        self._notifier = notifier
        self._clock = clock

    def after_commit(self) -> None:
        self.flush()

    def flush(self) -> int:
        """Deliver pending notices in order; stop at the first failure and leave the rest pending."""
        try:
            pending = self._notices.pending()
        except Exception:
            logger.exception("could not read pending notices")
            return 0
        for done, item in enumerate(pending):
            try:
                if isinstance(item.item, ShiftReport):
                    self._notifier.report(item.item)
                else:
                    self._notifier.alert(item.item)
                self._notices.mark_delivered(item.notice_id, self._clock())
            except Exception:
                logger.exception(
                    "delivery of %s failed; %d notices left pending", item.notice_id, len(pending) - done
                )
                return done
        return len(pending)
