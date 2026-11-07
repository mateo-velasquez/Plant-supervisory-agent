"""Fan-out of one delivery to several channels."""

from collections.abc import Sequence

from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.notify.port import Notifier


class CompositeNotifier:
    """Calls each notifier in order; the first failure propagates and skips the rest."""

    def __init__(self, notifiers: Sequence[Notifier]) -> None:
        self._notifiers = tuple(notifiers)

    def alert(self, notice: Notice) -> None:
        for notifier in self._notifiers:
            notifier.alert(notice)

    def report(self, report: ShiftReport) -> None:
        for notifier in self._notifiers:
            notifier.report(report)
