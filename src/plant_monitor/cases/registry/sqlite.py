"""Single-writer SQLite registry: schema bootstrap, processed marks, anomalies and the unit of work."""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Self

from plant_monitor.domain.enums import AnomalyKind, Market, Model
from plant_monitor.domain.models import Anomaly, Combination, SnapshotCommit

from . import schema
from .cases_repo import SqliteCaseRepository
from .causes_repo import SqliteCauseRepository
from .notices import SqliteNoticeStore
from .releases import SqliteReleaseStore
from .reviews_repo import SqliteReviewStore
from .session import Session


def _migrate(conn: sqlite3.Connection, version: int) -> None:
    """Run the steps from 'version' statement by statement in one transaction; any error rolls it back."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Split on ';': a migration statement must not contain ';' inside it.
        for statement in schema.migration_from(version).split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


class SqliteRegistry:
    """Single-writer SQLite registry; satisfies ProcessedStore structurally."""

    def __init__(self, path: str | Path) -> None:
        conn = sqlite3.connect(str(path), autocommit=True)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version == 0:
                conn.executescript(schema.SCHEMA)
            elif version in schema.STEPS:
                _migrate(conn, version)
            elif version != schema.SCHEMA_VERSION:
                raise ValueError(f"{path}: schema version {version}, expected {schema.SCHEMA_VERSION}")
            conn.execute("PRAGMA foreign_keys = ON")
        except BaseException:
            conn.close()
            raise
        self._session = Session(conn)
        self.cases = SqliteCaseRepository(self._session)
        self.releases = SqliteReleaseStore(self._session)
        self.notices = SqliteNoticeStore(self._session)
        self.causes = SqliteCauseRepository(self._session)
        self.reviews = SqliteReviewStore(self._session)

    def close(self) -> None:
        self._session.conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get_hash(self, snapshot_id: str) -> str | None:
        row = self._session.conn.execute(
            "SELECT content_hash FROM processed_snapshots WHERE snapshot_id = ?", (snapshot_id,)
        ).fetchone()
        return None if row is None else str(row[0])

    def known_units(self) -> Mapping[str, Combination]:
        rows = self._session.conn.execute("SELECT unidad_id, modelo, mercado FROM known_units").fetchall()
        return {str(r[0]): Combination(modelo=Model(r[1]), mercado=Market(r[2])) for r in rows}

    def record_anomaly(self, anomaly: Anomaly) -> None:
        if self._session.open is not None:
            raise RuntimeError(f"record_anomaly inside the processing of {self._session.open[0]}")
        self._insert_anomaly(anomaly)

    def _insert_anomaly(self, anomaly: Anomaly) -> None:
        self._session.conn.execute(
            "INSERT OR IGNORE INTO anomalies (kind, snapshot_id, detail) VALUES (?, ?, ?)",
            (str(anomaly.kind), anomaly.snapshot_id, anomaly.detail),
        )

    def recorded_anomalies(self) -> tuple[Anomaly, ...]:
        rows = self._session.conn.execute(
            "SELECT kind, snapshot_id, detail FROM anomalies ORDER BY id"
        ).fetchall()
        return tuple(Anomaly(kind=AnomalyKind(r[0]), snapshot_id=r[1], detail=r[2]) for r in rows)

    def current_snapshot(self) -> str | None:
        """Snapshot of the open unit of work."""
        return self._session.current_snapshot()

    def current_unit(self) -> int | None:
        """Token of the open unit of work; new on every processing entry."""
        return self._session.current_unit()

    @contextmanager
    def processing(self, commit: SnapshotCommit) -> Iterator[None]:
        session = self._session
        if session.open is not None:
            raise RuntimeError(f"processing {commit.snapshot_id} while {session.open[0]} is open")
        if self.get_hash(commit.snapshot_id) is not None:
            raise ValueError(f"snapshot {commit.snapshot_id} is already processed")
        conn = session.conn
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM processed_snapshots").fetchone()
            seq = int(row[0])
            session.begin_unit(commit.snapshot_id, seq)
            yield
            conn.execute(
                "INSERT INTO processed_snapshots (snapshot_id, content_hash, seq) VALUES (?, ?, ?)",
                (commit.snapshot_id, commit.content_hash, seq),
            )
            for anomaly in commit.anomalies:
                self._insert_anomaly(anomaly)
            for unit_id, combo in commit.new_units.items():
                conn.execute(
                    "INSERT OR IGNORE INTO known_units (unidad_id, modelo, mercado) VALUES (?, ?, ?)",
                    (unit_id, str(combo.modelo), str(combo.mercado)),
                )
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            session.end_unit()
