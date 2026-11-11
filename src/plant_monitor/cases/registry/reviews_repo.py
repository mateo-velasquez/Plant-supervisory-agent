"""Logbook review progress on the registry's session."""

from collections.abc import Collection
from typing import Protocol

from plant_monitor.cases.reviews import LogbookReview

from .session import Session


class ReviewStore(Protocol):
    """What the review step needs from the registry."""

    def get(self, turno_ids: Collection[str]) -> dict[str, LogbookReview]: ...

    def save(self, review: LogbookReview) -> None: ...


class SqliteReviewStore:
    """Review persistence; writes go through the single write guard."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, turno_ids: Collection[str]) -> dict[str, LogbookReview]:
        """Reviews of the given logbooks; logbooks never attempted are absent."""
        if not turno_ids:
            return {}
        marks = ", ".join("?" for _ in turno_ids)
        rows = self._session.conn.execute(
            "SELECT turno_id, attempts, last_attempt_at, reviewed_at, given_up_at "
            f"FROM logbook_reviews WHERE turno_id IN ({marks})",
            tuple(turno_ids),
        ).fetchall()
        return {
            r[0]: LogbookReview(
                turno_id=r[0], attempts=r[1], last_attempt_at=r[2], reviewed_at=r[3], given_up_at=r[4]
            )
            for r in rows
        }

    def save(self, review: LogbookReview) -> None:
        self._session.require_open(review.last_attempt_at)
        self._session.conn.execute(
            "INSERT INTO logbook_reviews (turno_id, attempts, last_attempt_at, reviewed_at, given_up_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(turno_id) DO UPDATE SET attempts = excluded.attempts, "
            "last_attempt_at = excluded.last_attempt_at, reviewed_at = excluded.reviewed_at, "
            "given_up_at = excluded.given_up_at",
            (
                review.turno_id,
                review.attempts,
                review.last_attempt_at,
                review.reviewed_at,
                review.given_up_at,
            ),
        )
