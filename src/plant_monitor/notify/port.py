"""The notifier port."""

from typing import Protocol

from plant_monitor.domain.notices import Notice, ShiftReport


class Notifier(Protocol):
    """Output channel for delivered notices (FR-26)."""

    def alert(self, notice: Notice) -> None: ...

    def report(self, report: ShiftReport) -> None: ...
