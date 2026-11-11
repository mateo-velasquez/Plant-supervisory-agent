"""009 T6: reviewed-logbook rules (R7, Q-53, E11)."""

import pytest

from plant_monitor.cases.reviews import (
    LogbookReview,
    ReviewMark,
    next_review,
    pending_logbooks,
    review_succeeded,
)

AVAILABLE = ("T01", "T02", "T03", "T04", "T05", "T06")
MAX_ATTEMPTS = 2


def reviewed(turno_id: str, at: str) -> LogbookReview:
    """A logbook reviewed at 'at' on its first attempt."""
    return LogbookReview(turno_id=turno_id, attempts=1, last_attempt_at=at, reviewed_at=at, given_up_at=None)


T05_FAILED_ONCE = LogbookReview(
    turno_id="T05", attempts=1, last_attempt_at="S010", reviewed_at=None, given_up_at=None
)
REVIEWS = {
    "T01": reviewed("T01", "S002"),
    "T02": reviewed("T02", "S004"),
    "T03": reviewed("T03", "S006"),
    "T04": reviewed("T04", "S008"),
    "T05": T05_FAILED_ONCE,
}


def test_e11a_pending_are_the_unsettled_available_logbooks_in_order() -> None:
    assert pending_logbooks(AVAILABLE, REVIEWS) == ("T05", "T06")


def test_e11b_first_failed_attempt_is_a_retry() -> None:
    review, mark = next_review(None, "T06", "S012", False, MAX_ATTEMPTS)
    assert review.attempts == 1
    assert review.reviewed_at is None
    assert review.given_up_at is None
    assert mark is ReviewMark.RETRY


def test_e11c_second_failed_attempt_gives_up_and_leaves_only_t06_pending() -> None:
    review, mark = next_review(T05_FAILED_ONCE, "T05", "S012", False, MAX_ATTEMPTS)
    assert review.attempts == 2
    assert review.given_up_at == "S012"
    assert review.reviewed_at is None
    assert mark is ReviewMark.GIVEN_UP
    assert pending_logbooks(AVAILABLE, {**REVIEWS, "T05": review}) == ("T06",)


def test_e11d_second_attempt_that_succeeds_is_reviewed() -> None:
    review, mark = next_review(T05_FAILED_ONCE, "T05", "S012", True, MAX_ATTEMPTS)
    assert review.attempts == 2
    assert review.reviewed_at == "S012"
    assert review.given_up_at is None
    assert mark is ReviewMark.REVIEWED


@pytest.mark.parametrize(
    ("valid", "unapplied", "coordinator_done", "expected"),
    [
        (True, 0, None, True),
        (True, 1, True, True),
        (True, 1, False, False),
        (False, 0, None, False),
        (True, 0, False, True),
    ],
)
def test_e11f_review_succeeded(
    valid: bool, unapplied: int, coordinator_done: bool | None, expected: bool
) -> None:
    assert review_succeeded(valid, unapplied, coordinator_done) is expected
