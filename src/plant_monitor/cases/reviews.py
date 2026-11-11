"""Reviewed-logbook rules: which logbooks are pending and how an attempt settles (009 R7)."""

from collections.abc import Mapping, Sequence
from enum import StrEnum

from plant_monitor.domain.models import FrozenModel


class ReviewMark(StrEnum):
    """Outcome of one review attempt, as shown to the report."""

    REVIEWED = "revisada"
    RETRY = "reintento"
    GIVEN_UP = "sin_revisar"


class LogbookReview(FrozenModel):
    """Review progress of one logbook; at most one of the two dates is set."""

    turno_id: str
    attempts: int
    last_attempt_at: str
    reviewed_at: str | None
    given_up_at: str | None

    @property
    def settled(self) -> bool:
        return self.reviewed_at is not None or self.given_up_at is not None


def pending_logbooks(available: Sequence[str], reviews: Mapping[str, LogbookReview]) -> tuple[str, ...]:
    """Available logbooks not yet settled, in the order given."""
    return tuple(t for t in available if t not in reviews or not reviews[t].settled)


def review_succeeded(valid: bool, unapplied: int, coordinator_done: bool | None) -> bool:
    """True iff the output was valid and every accepted proposal was applied (Q-53)."""
    return valid and (unapplied == 0 or coordinator_done is True)


def next_review(
    current: LogbookReview | None, turno_id: str, snapshot_id: str, succeeded: bool, max_attempts: int
) -> tuple[LogbookReview, ReviewMark]:
    """The review after one more attempt at 'snapshot_id'."""
    attempts = 1 if current is None else current.attempts + 1
    reviewed_at = snapshot_id if succeeded else None
    gave_up = not succeeded and attempts >= max_attempts
    review = LogbookReview(
        turno_id=turno_id,
        attempts=attempts,
        last_attempt_at=snapshot_id,
        reviewed_at=reviewed_at,
        given_up_at=snapshot_id if gave_up else None,
    )
    if succeeded:
        return review, ReviewMark.REVIEWED
    return review, ReviewMark.GIVEN_UP if gave_up else ReviewMark.RETRY
