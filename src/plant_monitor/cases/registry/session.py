"""Shared connection and open unit of work."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class Session:
    """Shared connection and open unit of work; owned by SqliteRegistry."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.open: tuple[str, int] | None = None
        self.unit: int | None = None
        self._units_started = 0

    def begin_unit(self, snapshot_id: str, seq: int) -> None:
        """Mark a unit of work open and give it a new in-process token."""
        self._units_started += 1
        self.unit = self._units_started
        self.open = (snapshot_id, seq)

    def end_unit(self) -> None:
        self.open = None
        self.unit = None

    def require_open(self, snapshot_id: str) -> int:
        """The single write guard: returns the open unit's seq for 'snapshot_id'."""
        if self.open is None:
            raise RuntimeError(f"write for {snapshot_id} outside a processing unit of work")
        open_id, seq = self.open
        if open_id != snapshot_id:
            raise ValueError(f"write for {snapshot_id} while {open_id} is the open unit of work")
        return seq

    @contextmanager
    def savepoint(self, name: str) -> Iterator[None]:
        """Nested unit inside the open transaction; rolls back to it on any error."""
        self.conn.execute(f"SAVEPOINT {name}")
        try:
            yield
        except BaseException:
            self.conn.execute(f"ROLLBACK TO {name}")
            self.conn.execute(f"RELEASE {name}")
            raise
        self.conn.execute(f"RELEASE {name}")

    def current_snapshot(self) -> str | None:
        """Snapshot of the open unit of work."""
        return None if self.open is None else self.open[0]

    def current_unit(self) -> int | None:
        """Token of the open unit of work; new on every processing entry."""
        return self.unit


def opt(value: Any) -> str | None:
    """Enum or None to its stored text."""
    return None if value is None else str(value)
