"""Refusals of the logbook store (R3, R5)."""

from plant_monitor.domain.errors import RejectedRequest


class UnknownLogbook(RejectedRequest):
    """The id is not a shift in 'turnos.csv'."""

    def __init__(self, turno_id: str) -> None:
        super().__init__(f"unknown logbook {turno_id}")


class LogbookHeldOut(RejectedRequest):
    """The shift is held out while closed; its timing is never revealed."""

    def __init__(self, turno_id: str) -> None:
        super().__init__(f"logbook {turno_id} is held out")


class LogbookNotAvailable(RejectedRequest):
    """The shift has not closed at the current snapshot."""

    def __init__(self, turno_id: str, snapshot_id: str, closes_at: str) -> None:
        super().__init__(f"logbook {turno_id} is not available at {snapshot_id}: it closes at {closes_at}")


class EmptyFragment(RejectedRequest):
    """The citation is empty after whitespace normalization."""

    def __init__(self, turno_id: str) -> None:
        super().__init__(f"empty fragment for {turno_id}")


class FragmentNotFound(RejectedRequest):
    """The normalized citation is not a substring of the logbook."""

    def __init__(self, turno_id: str) -> None:
        super().__init__(f"fragment not found in {turno_id}")


class LogbookMissing(RejectedRequest):
    """The shift's logbook file is absent; the review is retried later."""

    def __init__(self, turno_id: str) -> None:
        super().__init__(f"logbook {turno_id} is missing")
