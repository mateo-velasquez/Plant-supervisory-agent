"""Active causes, their case links and cited causes on the registry's session."""

import sqlite3
from collections.abc import Collection
from typing import Any, Final, Protocol

from plant_monitor.domain.causes import (
    ActiveCause,
    CauseCategory,
    CauseScope,
    CitedCause,
    Evidence,
)
from plant_monitor.domain.enums import Market, Model, Stage

from .session import Session
from .session import opt as _opt

_ACTIVE_COLUMNS: Final = (
    "active_cause_id, categoria, modelo, etapa, mercado, opened_at, opened_bitacora, opened_fragmento, "
    "lifted_at, lifted_bitacora, lifted_fragmento"
)


class CauseStore(Protocol):
    """What the cause ledger needs from the registry."""

    def in_force(self) -> tuple[ActiveCause, ...]: ...

    def get_active(self, active_cause_id: str) -> ActiveCause | None: ...

    def opened_count(self, snapshot_id: str) -> int: ...

    def links(self, ids: Collection[str]) -> dict[str, tuple[str, ...]]: ...

    def cited(self, case_ids: Collection[str]) -> dict[str, CitedCause]: ...

    def open(self, cause: ActiveCause) -> None: ...

    def lift(self, active_cause_id: str, snapshot_id: str, evidence: Evidence) -> None: ...

    def link(self, active_cause_id: str, case_id: str, snapshot_id: str) -> None: ...

    def set_cited(self, case_id: str, cause: CitedCause) -> None: ...


def _active_from_row(r: sqlite3.Row | tuple[Any, ...]) -> ActiveCause:
    lifted = None if r[8] is None else Evidence(bitacora=r[9], fragmento=r[10])
    return ActiveCause(
        active_cause_id=r[0],
        categoria=CauseCategory(r[1]),
        scope=CauseScope(
            modelo=Model(r[2]), etapa=Stage(r[3]), mercado=None if r[4] is None else Market(r[4])
        ),
        opened_at=r[5],
        opened_by=Evidence(bitacora=r[6], fragmento=r[7]),
        lifted_at=r[8],
        lifted_by=lifted,
    )


def _placeholders(values: Collection[str]) -> str:
    return ", ".join("?" for _ in values)


class SqliteCauseRepository:
    """Cause persistence on the registry's session; writes go through the single write guard."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def in_force(self) -> tuple[ActiveCause, ...]:
        rows = self._session.conn.execute(
            f"SELECT {_ACTIVE_COLUMNS} FROM active_causes WHERE lifted_at IS NULL ORDER BY seq"
        ).fetchall()
        return tuple(_active_from_row(r) for r in rows)

    def get_active(self, active_cause_id: str) -> ActiveCause | None:
        row = self._session.conn.execute(
            f"SELECT {_ACTIVE_COLUMNS} FROM active_causes WHERE active_cause_id = ?", (active_cause_id,)
        ).fetchone()
        return None if row is None else _active_from_row(row)

    def opened_count(self, snapshot_id: str) -> int:
        row = self._session.conn.execute(
            "SELECT COUNT(*) FROM active_causes WHERE opened_at = ?", (snapshot_id,)
        ).fetchone()
        return int(row[0])

    def links(self, ids: Collection[str]) -> dict[str, tuple[str, ...]]:
        """Case ids linked to each active cause id; causes without links are absent."""
        if not ids:
            return {}
        rows = self._session.conn.execute(
            "SELECT active_cause_id, case_id FROM active_cause_links "
            f"WHERE active_cause_id IN ({_placeholders(ids)}) ORDER BY rowid",
            tuple(ids),
        ).fetchall()
        found: dict[str, list[str]] = {}
        for cause_id, case_id in rows:
            found.setdefault(cause_id, []).append(case_id)
        return {cause_id: tuple(case_ids) for cause_id, case_ids in found.items()}

    def cited(self, case_ids: Collection[str]) -> dict[str, CitedCause]:
        if not case_ids:
            return {}
        rows = self._session.conn.execute(
            "SELECT case_id, categoria, etapa, bitacora, fragmento, set_at, active_cause_id "
            f"FROM case_causes WHERE case_id IN ({_placeholders(case_ids)})",
            tuple(case_ids),
        ).fetchall()
        return {
            r[0]: CitedCause(
                categoria=CauseCategory(r[1]),
                etapa=Stage(r[2]),
                evidence=Evidence(bitacora=r[3], fragmento=r[4]),
                set_at=r[5],
                active_cause_id=r[6],
            )
            for r in rows
        }

    def open(self, cause: ActiveCause) -> None:
        self._session.require_open(cause.opened_at)
        scope = cause.scope
        self._session.conn.execute(
            "INSERT INTO active_causes (active_cause_id, seq, categoria, modelo, etapa, mercado, opened_at, "
            "opened_bitacora, opened_fragmento) "
            "VALUES (?, (SELECT COALESCE(MAX(seq), 0) + 1 FROM active_causes), ?, ?, ?, ?, ?, ?, ?)",
            (
                cause.active_cause_id,
                str(cause.categoria),
                str(scope.modelo),
                str(scope.etapa),
                _opt(scope.mercado),
                cause.opened_at,
                cause.opened_by.bitacora,
                cause.opened_by.fragmento,
            ),
        )

    def lift(self, active_cause_id: str, snapshot_id: str, evidence: Evidence) -> None:
        self._session.require_open(snapshot_id)
        cursor = self._session.conn.execute(
            "UPDATE active_causes SET lifted_at = ?, lifted_bitacora = ?, lifted_fragmento = ? "
            "WHERE active_cause_id = ? AND lifted_at IS NULL",
            (snapshot_id, evidence.bitacora, evidence.fragmento, active_cause_id),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"no active cause in force with id {active_cause_id}")

    def link(self, active_cause_id: str, case_id: str, snapshot_id: str) -> None:
        self._session.require_open(snapshot_id)
        self._session.conn.execute(
            "INSERT OR IGNORE INTO active_cause_links (active_cause_id, case_id, linked_at) VALUES (?, ?, ?)",
            (active_cause_id, case_id, snapshot_id),
        )

    def set_cited(self, case_id: str, cause: CitedCause) -> None:
        self._session.require_open(cause.set_at)
        self._session.conn.execute(
            "INSERT INTO case_causes "
            "(case_id, categoria, etapa, bitacora, fragmento, set_at, active_cause_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(case_id) DO UPDATE SET categoria = excluded.categoria, etapa = excluded.etapa, "
            "bitacora = excluded.bitacora, fragmento = excluded.fragmento, set_at = excluded.set_at, "
            "active_cause_id = excluded.active_cause_id",
            (
                case_id,
                str(cause.categoria),
                str(cause.etapa),
                cause.evidence.bitacora,
                cause.evidence.fragmento,
                cause.set_at,
                cause.active_cause_id,
            ),
        )
