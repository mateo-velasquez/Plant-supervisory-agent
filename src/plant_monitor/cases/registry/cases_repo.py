"""Case and history persistence on the registry's session."""

import sqlite3
from typing import Any, Final, Protocol

from plant_monitor.cases.novelty import case_order
from plant_monitor.domain.cases import Case, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage, is_deviation
from plant_monitor.domain.models import Combination, all_combinations

from .session import Session
from .session import opt as _opt

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


_HISTORY_COLUMNS: Final = (
    "case_id, snapshot_id, state, minimum_severity, raised, gap_units, gap_pct, delay_days, "
    "bottleneck, clean_streak"
)


def _history_from_row(r: sqlite3.Row | tuple[Any, ...]) -> CaseHistoryRow:
    return CaseHistoryRow(
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


class SqliteCaseRepository:
    """Cases and history on the registry's session; satisfies CaseRepository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def current_snapshot(self) -> str | None:
        return self._session.current_snapshot()

    def current_unit(self) -> int | None:
        return self._session.current_unit()

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
            f"SELECT {_HISTORY_COLUMNS} FROM case_history WHERE case_id = ? ORDER BY seq", (case_id,)
        ).fetchall()
        return tuple(_history_from_row(r) for r in rows)

    def resolved_unreported(self) -> tuple[Case, ...]:
        """Resolved cases not yet reported as resolved, in 'case_order'."""
        rows = self._session.conn.execute(
            f"SELECT {_CASE_COLUMNS} FROM cases WHERE state = ? "
            "AND (last_reported_state IS NULL OR last_reported_state <> ?)",
            (str(CaseState.RESOLVED), str(CaseState.RESOLVED)),
        ).fetchall()
        return tuple(sorted((_case_from_row(r) for r in rows), key=case_order))

    def last_deviation_row(self, case_id: str) -> CaseHistoryRow | None:
        """Latest history row whose minimum severity is 'media' or more."""
        deviating = tuple(str(s) for s in Severity if is_deviation(s))
        marks = ", ".join("?" for _ in deviating)
        rows = self._session.conn.execute(
            f"SELECT {_HISTORY_COLUMNS} FROM case_history WHERE case_id = ? "
            f"AND minimum_severity IN ({marks}) ORDER BY seq DESC LIMIT 1",
            (case_id, *deviating),
        ).fetchall()
        return next((_history_from_row(r) for r in rows), None)

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
