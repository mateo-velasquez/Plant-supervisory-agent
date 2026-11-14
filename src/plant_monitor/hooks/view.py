"""Read-only view of the snapshot's decisions that hooks check against (010 plan)."""

from collections.abc import Mapping
from typing import Protocol

from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import Notice


class SnapshotView(Protocol):
    """What the hooks may know about the snapshot being processed."""

    def alerts(self) -> tuple[Notice, ...]:
        """Alert notices decided for the snapshot."""
        ...

    def news(self) -> tuple[Notice, ...]:
        """Shift-report news notices decided for the snapshot."""
        ...

    def floors(self) -> Mapping[str, Severity]:
        """Computed minimum severity per case id."""
        ...

    def missing(self) -> tuple[str, ...]:
        """Notice ids still without a written text."""
        ...
