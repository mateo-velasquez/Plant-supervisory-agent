"""Released units on the registry's session."""

from datetime import datetime

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import ReleasedUnit, Snapshot

from .session import Session


class SqliteReleaseStore:
    """Released units on the registry's session (FR-05, Q-20)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record_releases(self, snapshot: Snapshot) -> None:
        seq = self._session.require_open(snapshot.snapshot_id)
        conn = self._session.conn
        conn.execute("DELETE FROM released_units WHERE seq = ?", (seq,))
        conn.executemany(
            "INSERT INTO released_units (seq, idx, snapshot_id, unidad_id, modelo, mercado, hora) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    seq,
                    idx,
                    snapshot.snapshot_id,
                    u.unidad_id,
                    str(u.modelo),
                    str(u.mercado),
                    u.hora.isoformat(),
                )
                for idx, u in enumerate(snapshot.liberadas)
            ],
        )

    def released_so_far(self) -> tuple[ReleasedUnit, ...]:
        rows = self._session.conn.execute(
            "SELECT unidad_id, modelo, mercado, hora FROM released_units ORDER BY seq, idx"
        ).fetchall()
        return tuple(
            ReleasedUnit(
                unidad_id=r[0], modelo=Model(r[1]), mercado=Market(r[2]), hora=datetime.fromisoformat(r[3])
            )
            for r in rows
        )
