"""Every registry row the dashboard shows, read read-only in one transaction (014 R2, I3, I7)."""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from plant_monitor.domain.cases import CaseHistoryRow
from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import Combination
from plant_monitor.domain.notices import Notice, ShiftReport

from .cases_repo import HISTORY_COLUMNS, history_from_row
from .readonly import check_columns, open_readonly

_KIND_REPORT: Final = "report"
_LOCKED: Final = "database is locked"
_NEEDS: Final[Mapping[str, frozenset[str]]] = {
    "processed_snapshots": frozenset({"snapshot_id", "seq"}),
    "cases": frozenset({"case_id", "modelo", "mercado", "opened_at"}),
    "case_history": frozenset({*HISTORY_COLUMNS, "seq"}),
    "notices": frozenset({"seq", "idx", "kind", "payload"}),
}


@dataclass(frozen=True)
class ProcessedRow:
    """A processed snapshot and its position."""

    snapshot_id: str
    seq: int


@dataclass(frozen=True)
class CaseRow:
    """The identity of a case."""

    case_id: str
    combination: Combination
    opened_at: str


@dataclass(frozen=True)
class HistoryAt:
    """A case history row and the 'seq' it was written at."""

    seq: int
    row: CaseHistoryRow


@dataclass(frozen=True)
class NoticeAt:
    """A stored notice or report with its position."""

    seq: int
    idx: int
    item: Notice | ShiftReport


@dataclass(frozen=True)
class RunRows:
    """Every table the dashboard reads, from one transaction."""

    processed: tuple[ProcessedRow, ...]
    cases: tuple[CaseRow, ...]
    history: tuple[HistoryAt, ...]
    notices: tuple[NoticeAt, ...]


class RegistryBusy(ValueError):
    """The registry is write-locked; the caller may retry."""


def read_run_rows(path: Path) -> RunRows | None:
    """The run rows in 'seq' order, or None when the registry file does not exist."""
    if not path.is_file():
        return None
    try:
        with open_readonly(path) as conn:
            check_columns(conn, path, _NEEDS)
            return _read(conn)
    except sqlite3.OperationalError as error:
        if _LOCKED in str(error):
            raise RegistryBusy("dashboard: registry busy") from error
        raise _unreadable(path, error) from error
    except (sqlite3.Error, ValueError) as error:
        raise _unreadable(path, error) from error


def _unreadable(path: Path, error: Exception) -> ValueError:
    """The 500 error naming only the class of 'error' (I7)."""
    return ValueError(f"dashboard: {path.name} is not a readable registry ({type(error).__name__})")


def _read(conn: sqlite3.Connection) -> RunRows:
    processed = conn.execute("SELECT snapshot_id, seq FROM processed_snapshots ORDER BY seq").fetchall()
    cases = conn.execute("SELECT case_id, modelo, mercado, opened_at FROM cases ORDER BY rowid").fetchall()
    history = conn.execute(
        f"SELECT {', '.join(HISTORY_COLUMNS)}, seq FROM case_history ORDER BY seq, rowid"
    ).fetchall()
    notices = conn.execute("SELECT seq, idx, kind, payload FROM notices ORDER BY seq, idx").fetchall()
    return RunRows(
        processed=tuple(ProcessedRow(snapshot_id=s, seq=n) for s, n in processed),
        cases=tuple(
            CaseRow(case_id=c, combination=Combination(modelo=Model(m), mercado=Market(k)), opened_at=o)
            for c, m, k, o in cases
        ),
        history=tuple(HistoryAt(seq=r[-1], row=history_from_row(r[:-1])) for r in history),
        notices=tuple(NoticeAt(seq=s, idx=i, item=_parse(kind, payload)) for s, i, kind, payload in notices),
    )


def _parse(kind: str, payload: str) -> Notice | ShiftReport:
    """The notice or report stored in 'payload'."""
    if kind == _KIND_REPORT:
        return ShiftReport.model_validate_json(payload)
    return Notice.model_validate_json(payload)
