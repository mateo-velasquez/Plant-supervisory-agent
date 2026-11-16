"""A notice as stored, with the registry facts a trace needs (013 I7)."""

from collections.abc import Mapping
from dataclasses import dataclass

from plant_monitor.domain.cases import CaseHistoryRow
from plant_monitor.domain.causes import ActiveCause, CitedCause
from plant_monitor.domain.notices import Notice


@dataclass(frozen=True)
class StoredNotice:
    """The stored notice, its case's history, snapshot order, linked causes and cited cause."""

    notice: Notice
    history: tuple[CaseHistoryRow, ...]
    order: Mapping[str, int]
    causes: tuple[ActiveCause, ...]
    links: Mapping[str, str]
    cited: CitedCause | None
