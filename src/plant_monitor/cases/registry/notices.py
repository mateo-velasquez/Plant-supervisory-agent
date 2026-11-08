"""Notice decisions and the delivery outbox on the registry's session (ADR-0010)."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import datetime
from pathlib import Path
from typing import Final

from plant_monitor.domain.notices import Notice, NoticeType, PendingDelivery, ShiftReport, report_id_for

from .session import Session

_KIND_NOTICE = "notice"
_KIND_REPORT = "report"
DELIVERABLE_FILTER: Final = "(kind = 'report' OR tipo = 'alerta_inmediata')"
_READ_COLUMNS: Final = frozenset({"seq", "idx", "kind", "tipo", "payload"})


def read_deliverables(path: Path) -> tuple[Notice | ShiftReport, ...]:
    """Deliverable rows of a registry file in (seq, idx) order; read-only, never creates the file."""
    if not path.is_file():
        raise ValueError(f"{path}: registry not found")
    try:
        with closing(sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(notices)")}
            if missing := _READ_COLUMNS - columns:
                raise ValueError(f"{path}: table notices lacks {sorted(missing)}")
            found = conn.execute(
                f"SELECT kind, payload FROM notices WHERE {DELIVERABLE_FILTER} ORDER BY seq, idx"
            ).fetchall()
    except sqlite3.Error as error:
        raise ValueError(f"{path}: not a readable registry ({error})") from error
    try:
        return tuple(_parse(kind, payload) for kind, payload in found)
    except ValueError as error:
        raise ValueError(f"{path}: unreadable payload in notices ({error})") from error


class SqliteNoticeStore:
    """Notice decisions and the delivery outbox on the registry's session (ADR-0010)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, snapshot_id: str, decisions: Sequence[Notice], report: ShiftReport | None) -> None:
        """Replace the open snapshot's set of notices, inside a savepoint."""
        seq = self._session.require_open(snapshot_id)
        stored_ids = [n.snapshot_id for n in decisions] + ([] if report is None else [report.snapshot_id])
        for found in stored_ids:
            if found != snapshot_id:
                raise ValueError(f"notice for {found} saved as part of {snapshot_id}")
        rows: list[tuple[str, str, str, str | None, str]] = [
            (n.notice_id, _KIND_NOTICE, str(n.tipo), n.case_id, n.model_dump_json()) for n in decisions
        ]
        if report is not None:
            rows.append(
                (
                    report_id_for(report.turno_id),
                    _KIND_REPORT,
                    str(NoticeType.SHIFT_REPORT),
                    None,
                    report.model_dump_json(),
                )
            )
        seen: set[str] = set()
        for row in rows:
            if row[0] in seen:
                raise ValueError(f"duplicate notice {row[0]} in the save of {snapshot_id}")
            seen.add(row[0])
        conn = self._session.conn
        current = ""
        try:
            with self._session.savepoint("notices_save"):
                conn.execute("DELETE FROM notices WHERE seq = ?", (seq,))
                for idx, (notice_id, kind, tipo, case_id, payload) in enumerate(rows):
                    current = notice_id
                    conn.execute(
                        "INSERT INTO notices "
                        "(notice_id, snapshot_id, seq, idx, kind, tipo, case_id, payload) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (notice_id, snapshot_id, seq, idx, kind, tipo, case_id, payload),
                    )
        except sqlite3.IntegrityError as error:
            text = str(error)
            if "notices.notice_id" in text:
                raise ValueError(f"notice {current} belongs to another snapshot") from error
            if "notices.case_id" in text:
                case_id = next(r[3] for r in rows if r[0] == current)
                raise ValueError(f"case {case_id} already has an alert") from error
            raise

    def for_snapshot(self, snapshot_id: str) -> tuple[Notice | ShiftReport, ...]:
        """Items saved for 'snapshot_id', in save order."""
        found = self._session.conn.execute(
            "SELECT kind, payload FROM notices WHERE snapshot_id = ? ORDER BY seq, idx", (snapshot_id,)
        ).fetchall()
        return tuple(_parse(r[0], r[1]) for r in found)

    def pending(self) -> tuple[PendingDelivery, ...]:
        """Undelivered alerts and reports in order; only outside a unit of work."""
        if self._session.open is not None:
            raise RuntimeError(f"pending inside the processing of {self._session.open[0]}")
        found = self._session.conn.execute(
            f"SELECT notice_id, kind, payload FROM notices "
            f"WHERE {DELIVERABLE_FILTER} AND delivered_at IS NULL "
            "ORDER BY seq, idx"
        ).fetchall()
        return tuple(PendingDelivery(r[0], _parse(r[1], r[2])) for r in found)

    def mark_delivered(self, notice_id: str, at: datetime) -> None:
        """Record the first delivery time; a repeat is a no-op."""
        if self._session.open is not None:
            raise RuntimeError(f"mark_delivered inside the processing of {self._session.open[0]}")
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError(f"delivery time of {notice_id} must be timezone-aware")
        conn = self._session.conn
        cursor = conn.execute(
            "UPDATE notices SET delivered_at = ? WHERE notice_id = ? AND delivered_at IS NULL",
            (at.isoformat(), notice_id),
        )
        if (
            cursor.rowcount == 0
            and conn.execute("SELECT 1 FROM notices WHERE notice_id = ?", (notice_id,)).fetchone() is None
        ):
            raise ValueError(f"unknown notice {notice_id}")

    def delivered_at(self, notice_id: str) -> datetime | None:
        """Delivery time of a notice, or None while pending."""
        row = self._session.conn.execute(
            "SELECT delivered_at FROM notices WHERE notice_id = ?", (notice_id,)
        ).fetchone()
        return None if row is None or row[0] is None else datetime.fromisoformat(row[0])


def _parse(kind: str, payload: str) -> Notice | ShiftReport:
    if kind == _KIND_REPORT:
        return ShiftReport.model_validate_json(payload)
    return Notice.model_validate_json(payload)
