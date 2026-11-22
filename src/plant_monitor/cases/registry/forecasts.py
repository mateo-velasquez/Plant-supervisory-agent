"""Gap forecast rows on the registry's session, and their read-only reader."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager
from datetime import datetime

from pydantic import ValidationError

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import ReleasedUnit

from .session import Session


class SqliteForecastStore:
    """Forecast persistence; writes go through the single write guard."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def open_seq(self, snapshot_id: str) -> int:
        """Seq of the open unit of work, which must be 'snapshot_id'."""
        return self._session.require_open(snapshot_id)

    def released_through(self, seq: int) -> tuple[ReleasedUnit, ...]:
        """Released units up to and including 'seq', in release order."""
        rows = self._session.conn.execute(
            "SELECT unidad_id, modelo, mercado, hora FROM released_units WHERE seq <= ? ORDER BY seq, idx",
            (seq,),
        ).fetchall()
        return tuple(
            ReleasedUnit(
                unidad_id=r[0], modelo=Model(r[1]), mercado=Market(r[2]), hora=datetime.fromisoformat(r[3])
            )
            for r in rows
        )

    def snapshot_at(self, seq: int) -> str:
        """Snapshot id at 'seq', including the open unit's; 'ValueError' if none."""
        if self._session.open is not None and self._session.open[1] == seq:
            return self._session.open[0]
        row = self._session.conn.execute(
            "SELECT snapshot_id FROM processed_snapshots WHERE seq = ?", (seq,)
        ).fetchone()
        if row is None:
            raise ValueError(f"no snapshot at seq {seq}")
        return str(row[0])

    def savepoint(self) -> AbstractContextManager[None]:
        return self._session.savepoint("forecast")

    def save(self, snapshot_id: str, rows: Sequence[ForecastRow]) -> None:
        seq = self._session.require_open(snapshot_id)
        for row in rows:
            if row.seq != seq or row.snapshot_id != snapshot_id:
                raise ValueError(
                    f"forecast row {row.snapshot_id}/{row.seq} is not the open unit {snapshot_id}/{seq}"
                )
        conn = self._session.conn
        conn.execute("DELETE FROM gap_forecasts WHERE seq = ?", (seq,))
        conn.executemany(
            "INSERT INTO gap_forecasts (seq, snapshot_id, modelo, mercado, status, payload) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    row.seq,
                    row.snapshot_id,
                    str(row.combination.modelo),
                    str(row.combination.mercado),
                    row.status,
                    row.model_dump_json(),
                )
                for row in rows
            ],
        )


def _payloads(conn: sqlite3.Connection) -> Iterator[str]:
    for (payload,) in conn.execute("SELECT payload FROM gap_forecasts ORDER BY seq, rowid"):
        yield str(payload)


def read_forecasts(conn: sqlite3.Connection) -> tuple[ForecastRow, ...] | None:
    """Stored rows by seq; None when the table is missing or any payload is unreadable."""
    try:
        return tuple(ForecastRow.model_validate_json(p) for p in _payloads(conn))
    except sqlite3.OperationalError, ValidationError:
        return None
