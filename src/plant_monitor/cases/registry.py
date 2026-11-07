"""SQLite case registry: unit of work, processed marks, cases, history and released units."""

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Final, Protocol, Self

from plant_monitor.domain.cases import Case, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import AnomalyKind, Market, Model, Severity, Stage
from plant_monitor.domain.models import (
    Anomaly,
    Combination,
    ReleasedUnit,
    Snapshot,
    SnapshotCommit,
    all_combinations,
)

SCHEMA_VERSION: Final = 1

_SCHEMA: Final = f"""
BEGIN;
CREATE TABLE processed_snapshots (
    snapshot_id  TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    seq          INTEGER NOT NULL UNIQUE
);
CREATE TABLE anomalies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    kind        TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    detail      TEXT NOT NULL,
    UNIQUE (kind, snapshot_id, detail)
);
CREATE TABLE known_units (
    unidad_id TEXT PRIMARY KEY,
    modelo    TEXT NOT NULL,
    mercado   TEXT NOT NULL
);
CREATE TABLE released_units (
    seq         INTEGER NOT NULL,
    idx         INTEGER NOT NULL,
    snapshot_id TEXT NOT NULL,
    unidad_id   TEXT NOT NULL,
    modelo      TEXT NOT NULL,
    mercado     TEXT NOT NULL,
    hora        TEXT NOT NULL,
    PRIMARY KEY (seq, idx)
);
CREATE TABLE cases (
    case_id                   TEXT PRIMARY KEY,
    modelo                    TEXT NOT NULL,
    mercado                   TEXT NOT NULL,
    opened_at                 TEXT NOT NULL,
    state                     TEXT NOT NULL,
    minimum_severity          TEXT NOT NULL,
    raised                    INTEGER NOT NULL,
    current_severity          TEXT NOT NULL,
    max_severity_since_report TEXT,
    clean_streak              INTEGER NOT NULL,
    last_snapshot_id          TEXT NOT NULL,
    last_reported_at          TEXT,
    last_reported_state       TEXT,
    last_reported_severity    TEXT,
    resolved_at               TEXT
);
CREATE UNIQUE INDEX one_active_case_per_combination
    ON cases (modelo, mercado) WHERE state <> 'resuelto';
CREATE TABLE case_history (
    case_id            TEXT NOT NULL REFERENCES cases (case_id),
    snapshot_id        TEXT NOT NULL,
    seq                INTEGER NOT NULL,
    state              TEXT NOT NULL,
    minimum_severity   TEXT NOT NULL,
    raised             INTEGER NOT NULL,
    effective_severity TEXT NOT NULL,
    gap_units          REAL NOT NULL,
    gap_pct            REAL,
    delay_days         REAL,
    bottleneck         TEXT,
    clean_streak       INTEGER NOT NULL,
    PRIMARY KEY (case_id, snapshot_id)
);
PRAGMA user_version = {SCHEMA_VERSION};
COMMIT;
"""

_COMBINATION_ORDER: Final = {combo: index for index, combo in enumerate(all_combinations())}


class CaseRepository(Protocol):
    """What CaseTracker needs from the registry."""

    def current_snapshot(self) -> str | None: ...

    def current_unit(self) -> int | None: ...

    def active_cases(self) -> tuple[Case, ...]: ...

    def get_case(self, case_id: str) -> Case | None: ...

    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]: ...

    def save_case(self, case: Case, row: CaseHistoryRow) -> None: ...

    def update_case(self, case: Case) -> None: ...


class _Session:
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
        """The single write guard: returns the open unit's seq for `snapshot_id`."""
        if self.open is None:
            raise RuntimeError(f"write for {snapshot_id} outside a processing unit of work")
        open_id, seq = self.open
        if open_id != snapshot_id:
            raise ValueError(f"write for {snapshot_id} while {open_id} is the open unit of work")
        return seq


def _opt(value: Any) -> str | None:
    """Enum or None to its stored text."""
    return None if value is None else str(value)


class SqliteRegistry:
    """Single-writer SQLite registry; satisfies ProcessedStore structurally."""

    def __init__(self, path: str | Path) -> None:
        conn = sqlite3.connect(str(path), autocommit=True)
        try:
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
            if version == 0:
                conn.executescript(_SCHEMA)
            elif version != SCHEMA_VERSION:
                raise ValueError(f"{path}: schema version {version}, expected {SCHEMA_VERSION}")
            conn.execute("PRAGMA foreign_keys = ON")
        except BaseException:
            conn.close()
            raise
        self._session = _Session(conn)
        self.cases = SqliteCaseRepository(self._session)
        self.releases = SqliteReleaseStore(self._session)

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
        return None if self._session.open is None else self._session.open[0]

    def current_unit(self) -> int | None:
        """Token of the open unit of work; new on every processing entry."""
        return self._session.unit

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


def _case_from_row(r: sqlite3.Row | tuple[Any, ...]) -> Case:
    return Case(
        case_id=r[0],
        combination=Combination(modelo=Model(r[1]), mercado=Market(r[2])),
        opened_at=r[3],
        state=CaseState(r[4]),
        minimum_severity=Severity(r[5]),
        raised=bool(r[6]),
        max_severity_since_report=None if r[7] is None else Severity(r[7]),
        clean_streak=r[8],
        last_snapshot_id=r[9],
        last_reported_at=r[10],
        last_reported_state=None if r[11] is None else CaseState(r[11]),
        last_reported_severity=None if r[12] is None else Severity(r[12]),
        resolved_at=r[13],
    )


_CASE_COLUMNS: Final = (
    "case_id, modelo, mercado, opened_at, state, minimum_severity, raised, max_severity_since_report, "
    "clean_streak, last_snapshot_id, last_reported_at, last_reported_state, "
    "last_reported_severity, resolved_at"
)


class SqliteCaseRepository:
    """Cases and history on the registry's session; satisfies CaseRepository."""

    def __init__(self, session: _Session) -> None:
        self._session = session

    def current_snapshot(self) -> str | None:
        return None if self._session.open is None else self._session.open[0]

    def current_unit(self) -> int | None:
        return self._session.unit

    def active_cases(self) -> tuple[Case, ...]:
        rows = self._session.conn.execute(
            f"SELECT {_CASE_COLUMNS} FROM cases WHERE state <> ?", (str(CaseState.RESOLVED),)
        ).fetchall()
        return tuple(
            sorted((_case_from_row(r) for r in rows), key=lambda c: _COMBINATION_ORDER[c.combination])
        )

    def get_case(self, case_id: str) -> Case | None:
        row = self._session.conn.execute(
            f"SELECT {_CASE_COLUMNS} FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        return None if row is None else _case_from_row(row)

    def history(self, case_id: str) -> tuple[CaseHistoryRow, ...]:
        rows = self._session.conn.execute(
            "SELECT case_id, snapshot_id, state, minimum_severity, raised, gap_units, gap_pct, delay_days, "
            "bottleneck, clean_streak FROM case_history WHERE case_id = ? ORDER BY seq",
            (case_id,),
        ).fetchall()
        return tuple(
            CaseHistoryRow(
                case_id=r[0],
                snapshot_id=r[1],
                state=CaseState(r[2]),
                minimum_severity=Severity(r[3]),
                raised=bool(r[4]),
                gap_units=r[5],
                gap_pct=r[6],
                delay_days=r[7],
                bottleneck=None if r[8] is None else Stage(r[8]),
                clean_streak=r[9],
            )
            for r in rows
        )

    def save_case(self, case: Case, row: CaseHistoryRow) -> None:
        Case.model_validate({name: getattr(case, name) for name in Case.model_fields})
        if row.case_id != case.case_id:
            raise ValueError(f"history row belongs to {row.case_id}, case is {case.case_id}")
        if case.last_snapshot_id != row.snapshot_id:
            raise ValueError(
                f"case {case.case_id} is at {case.last_snapshot_id}, history row at {row.snapshot_id}"
            )
        seq = self._session.require_open(row.snapshot_id)
        conn = self._session.conn
        try:
            conn.execute(
                """
                INSERT INTO cases (case_id, modelo, mercado, opened_at, state, minimum_severity, raised,
                    current_severity, max_severity_since_report, clean_streak, last_snapshot_id,
                    last_reported_at, last_reported_state, last_reported_severity, resolved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (case_id) DO UPDATE SET
                    modelo = excluded.modelo, mercado = excluded.mercado, opened_at = excluded.opened_at,
                    state = excluded.state, minimum_severity = excluded.minimum_severity,
                    raised = excluded.raised, current_severity = excluded.current_severity,
                    max_severity_since_report = excluded.max_severity_since_report,
                    clean_streak = excluded.clean_streak, last_snapshot_id = excluded.last_snapshot_id,
                    last_reported_at = excluded.last_reported_at,
                    last_reported_state = excluded.last_reported_state,
                    last_reported_severity = excluded.last_reported_severity,
                    resolved_at = excluded.resolved_at
                """,
                (
                    case.case_id,
                    str(case.combination.modelo),
                    str(case.combination.mercado),
                    case.opened_at,
                    str(case.state),
                    str(case.minimum_severity),
                    int(case.raised),
                    str(case.current_severity),
                    _opt(case.max_severity_since_report),
                    case.clean_streak,
                    case.last_snapshot_id,
                    case.last_reported_at,
                    _opt(case.last_reported_state),
                    _opt(case.last_reported_severity),
                    case.resolved_at,
                ),
            )
        except sqlite3.IntegrityError as error:
            if "cases.modelo, cases.mercado" not in str(error):
                raise
            raise ValueError(
                f"an active case already exists for {case.combination.modelo} x {case.combination.mercado}"
            ) from error
        conn.execute(
            """
            INSERT INTO case_history (case_id, snapshot_id, seq, state, minimum_severity, raised,
                effective_severity, gap_units, gap_pct, delay_days, bottleneck, clean_streak)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (case_id, snapshot_id) DO UPDATE SET
                state = excluded.state, minimum_severity = excluded.minimum_severity,
                raised = excluded.raised, effective_severity = excluded.effective_severity,
                gap_units = excluded.gap_units, gap_pct = excluded.gap_pct,
                delay_days = excluded.delay_days, bottleneck = excluded.bottleneck,
                clean_streak = excluded.clean_streak
            """,
            (
                row.case_id,
                row.snapshot_id,
                seq,
                str(row.state),
                str(row.minimum_severity),
                int(row.raised),
                str(row.effective_severity),
                row.gap_units,
                row.gap_pct,
                row.delay_days,
                _opt(row.bottleneck),
                row.clean_streak,
            ),
        )

    def update_case(self, case: Case) -> None:
        if case.last_reported_at is None:
            raise ValueError(f"case {case.case_id} has no last_reported_at to update")
        self._session.require_open(case.last_reported_at)
        cursor = self._session.conn.execute(
            "UPDATE cases SET last_reported_at = ?, last_reported_state = ?, last_reported_severity = ?, "
            "max_severity_since_report = ? WHERE case_id = ?",
            (
                case.last_reported_at,
                _opt(case.last_reported_state),
                _opt(case.last_reported_severity),
                _opt(case.max_severity_since_report),
                case.case_id,
            ),
        )
        if cursor.rowcount == 0:
            raise ValueError(f"unknown case {case.case_id}")


class SqliteReleaseStore:
    """Released units on the registry's session (FR-05, Q-20)."""

    def __init__(self, session: _Session) -> None:
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
