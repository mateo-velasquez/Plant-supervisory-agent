"""Read one notice and the registry facts around it, read-only and in one transaction (013 R2)."""

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.domain.stored import StoredNotice

from .cases_repo import HISTORY_COLUMNS, history_from_row
from .causes_repo import ACTIVE_COLUMNS, CITED_COLUMNS, active_from_row, cited_from_row
from .readonly import check_columns, open_readonly

_KIND_REPORT: Final = "report"
_NEEDS: Final[Mapping[str, frozenset[str]]] = {
    "notices": frozenset({"notice_id", "kind", "payload"}),
    "case_history": frozenset({*HISTORY_COLUMNS, "seq"}),
    "processed_snapshots": frozenset({"snapshot_id", "seq"}),
    "active_causes": frozenset({*ACTIVE_COLUMNS, "seq"}),
    "active_cause_links": frozenset({"active_cause_id", "case_id", "linked_at"}),
    "case_causes": frozenset(CITED_COLUMNS),
}


def read_notice(path: Path, notice_id: str) -> StoredNotice | ShiftReport | None:
    """The stored notice with its registry facts, a report, or None for an unknown id."""
    try:
        with open_readonly(path) as conn:
            return _read(conn, path, notice_id)
    except sqlite3.Error as error:
        raise ValueError(f"{path}: not a readable registry ({error})") from error


def _read(conn: sqlite3.Connection, path: Path, notice_id: str) -> StoredNotice | ShiftReport | None:
    check_columns(conn, path, _NEEDS)
    row = conn.execute("SELECT kind, payload FROM notices WHERE notice_id = ?", (notice_id,)).fetchone()
    if row is None:
        return None
    kind, payload = row
    try:
        if kind == _KIND_REPORT:
            return ShiftReport.model_validate_json(payload)
        notice = Notice.model_validate_json(payload)
    except ValueError as error:
        raise ValueError(f"{path}: unreadable payload of {notice_id}") from error
    case_id = notice.case_id
    history = conn.execute(
        f"SELECT {', '.join(HISTORY_COLUMNS)} FROM case_history WHERE case_id = ? ORDER BY seq", (case_id,)
    ).fetchall()
    order = conn.execute("SELECT snapshot_id, seq FROM processed_snapshots").fetchall()
    link_rows = conn.execute(
        "SELECT active_cause_id, linked_at FROM active_cause_links WHERE case_id = ? ORDER BY rowid",
        (case_id,),
    ).fetchall()
    cause_rows = conn.execute(
        f"SELECT {', '.join(ACTIVE_COLUMNS)} FROM active_causes WHERE active_cause_id IN "
        "(SELECT active_cause_id FROM active_cause_links WHERE case_id = ?) ORDER BY seq",
        (case_id,),
    ).fetchall()
    cited = conn.execute(
        f"SELECT {', '.join(CITED_COLUMNS)} FROM case_causes WHERE case_id = ?", (case_id,)
    ).fetchone()
    try:
        return StoredNotice(
            notice=notice,
            history=tuple(history_from_row(r) for r in history),
            order={snapshot_id: seq for snapshot_id, seq in order},
            causes=tuple(active_from_row(r) for r in cause_rows),
            links={cause_id: linked_at for cause_id, linked_at in link_rows},
            cited=None if cited is None else cited_from_row(cited),
        )
    except ValueError as error:
        raise ValueError(f"{path}: unreadable registry rows of {notice_id}") from error
