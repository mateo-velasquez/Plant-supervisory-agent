"""016 T3: registry schema v5 and the forecast store (R8, R12, I4, E13)."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest
from forecast_builders import SB, P, fc, of, plan_rows

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.registry.forecasts import read_forecasts
from plant_monitor.cases.registry.schema import (
    MIGRATION_V2_TO_V3_BODY,
    MIGRATION_V3_TO_V4_BODY,
    SCHEMA_V2_BODY,
)
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import Combination, ReleasedUnit, Snapshot, SnapshotCommit
from plant_monitor.metrics.progress import count_progress

PLAN = plan_rows(24)
HORA = datetime(2026, 3, 2, 10, 0)


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def units(prefix: str, count: int, combo: Combination = P) -> tuple[ReleasedUnit, ...]:
    """'count' released units of 'combo' with ids '<prefix>-<i>'."""
    return tuple(
        ReleasedUnit(unidad_id=f"{prefix}-{i}", modelo=combo.modelo, mercado=combo.mercado, hora=HORA)
        for i in range(count)
    )


def snapshot(snapshot_id: str, released: tuple[ReleasedUnit, ...]) -> Snapshot:
    """A snapshot that only carries released units."""
    return Snapshot(snapshot_id=snapshot_id, timestamp=HORA, turno="T01", unidades=(), liberadas=released)


def user_version(path: Path) -> int:
    """PRAGMA user_version of a SQLite file, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def table_names(path: Path) -> set[str]:
    """Names of the tables of a SQLite file."""
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(r[0]) for r in rows}


def dump(path: Path, table: str) -> list[tuple[object, ...]]:
    """All rows of a table, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def stored(path: Path) -> tuple[ForecastRow, ...] | None:
    """The stored forecast rows, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return read_forecasts(conn)


def make_v4_file(path: Path) -> None:
    """A v4 file with S001-S006 processed: 13 P releases per snapshot up to S004, then 10."""
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        body = SCHEMA_V2_BODY + MIGRATION_V2_TO_V3_BODY + MIGRATION_V3_TO_V4_BODY
        conn.executescript(f"BEGIN;\n{body}\nPRAGMA user_version = 4;\nCOMMIT;")
        for seq in range(1, 7):
            snapshot_id = f"S{seq:03d}"
            conn.execute("INSERT INTO processed_snapshots VALUES (?, ?, ?)", (snapshot_id, "h", seq))
            for idx in range(13 if seq <= 4 else 10):
                conn.execute(
                    "INSERT INTO released_units VALUES (?, ?, ?, ?, 'Pickup', 'Local', ?)",
                    (seq, idx, snapshot_id, f"U{seq}-{idx}", HORA.isoformat()),
                )


def test_e13a_fresh_file_is_version_five_with_the_forecast_table(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path):
        pass
    assert user_version(path) == 5
    assert "gap_forecasts" in table_names(path)


def test_e13b_v4_file_migrates_and_forecasts_at_once_from_released_units(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    make_v4_file(path)
    before = {t: dump(path, t) for t in ("processed_snapshots", "released_units")}
    with SqliteRegistry(path) as registry:
        for snapshot_id in ("S007", "S008"):
            seq = int(snapshot_id[1:])
            with registry.processing(commit(snapshot_id)):
                registry.releases.record_releases(snapshot(snapshot_id, units(snapshot_id, 10)))
                done = count_progress(registry.forecasts.released_through(seq))[P]
                base = count_progress(registry.forecasts.released_through(seq - 4))[P]
                rows = fc(seq, done, base, plan=PLAN)
                assert of(rows).status != "warm_up"
                registry.forecasts.save(snapshot_id, rows)
                if seq == 8:
                    row = of(rows)
    assert user_version(path) == 5
    assert {t: dump(path, t)[: len(rows_before)] for t, rows_before in before.items()} == before
    saved = stored(path)
    assert saved is not None
    assert {r.seq for r in saved} == {7, 8}
    assert len(saved) == 18
    assert (row.gap_units, row.status, row.target_level) == (-4.0, "warning", Severity.MEDIUM)
    assert row.basis is not None
    assert row.basis.rate == 10.0
    assert of([r for r in saved if r.seq == 8]) == row


@pytest.mark.parametrize(
    "update", [{"seq": 1, "snapshot_id": "S002"}, {"seq": 2, "snapshot_id": "S001"}], ids=["id", "seq"]
)
def test_r8_save_refuses_rows_that_are_not_the_open_unit_of_work(
    tmp_path: Path, update: dict[str, object]
) -> None:
    path = tmp_path / "r.sqlite3"
    rows = tuple(row.model_copy(update=update) for row in fc(2, 0, None, plan=PLAN))
    with SqliteRegistry(path) as registry, registry.processing(commit("S001")), pytest.raises(ValueError):
        registry.forecasts.save("S001", rows)
    assert stored(path) == ()


def test_i4_released_through_is_ordered_and_bounded_by_seq(tmp_path: Path) -> None:
    first, second, third = units("A", 2), units("B", 1, SB), units("C", 1)
    with SqliteRegistry(tmp_path / "r.sqlite3") as registry:
        for snapshot_id, released in (("S001", first), ("S002", second)):
            with registry.processing(commit(snapshot_id)):
                registry.releases.record_releases(snapshot(snapshot_id, released))
        with registry.processing(commit("S003")):
            registry.releases.record_releases(snapshot("S003", third))
            assert registry.forecasts.released_through(1) == first
            assert registry.forecasts.released_through(2) == first + second
            assert registry.forecasts.released_through(3) == first + second + third


def test_i4_snapshot_at_names_processed_and_open_snapshots(tmp_path: Path) -> None:
    with SqliteRegistry(tmp_path / "r.sqlite3") as registry:
        with registry.processing(commit("S001")):
            pass
        with registry.processing(commit("S002")):
            assert registry.forecasts.snapshot_at(1) == "S001"
            assert registry.forecasts.snapshot_at(2) == "S002"
            with pytest.raises(ValueError):
                registry.forecasts.snapshot_at(3)


def test_r8_rows_round_trip_in_seq_order_nine_per_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    first, second = fc(1, 0, None, plan=PLAN), fc(2, 0, None, plan=PLAN)
    with SqliteRegistry(path) as registry:
        for rows in (first, second):
            with registry.processing(commit(rows[0].snapshot_id)):
                registry.forecasts.save(rows[0].snapshot_id, rows)
    assert stored(path) == first + second


def test_r8_saving_again_in_the_same_unit_replaces_the_rows(tmp_path: Path) -> None:
    """Risk: a second save in one unit hits the primary key instead of replacing the snapshot's rows."""
    path = tmp_path / "r.sqlite3"
    rows = fc(1, 0, None, plan=PLAN)
    with SqliteRegistry(path) as registry, registry.processing(commit("S001")):
        registry.forecasts.save("S001", rows)
        registry.forecasts.save("S001", rows)
    assert stored(path) == rows


@pytest.mark.parametrize("damage", ["no_table", "bad_payload"])
def test_r12_reader_gives_none_for_a_missing_table_or_an_unreadable_payload(
    tmp_path: Path, damage: str
) -> None:
    """Risk: one unreadable row or an old file crashes the read-only views instead of reading as absent."""
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as registry, registry.processing(commit("S001")):
        registry.forecasts.save("S001", fc(1, 0, None, plan=PLAN))
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        if damage == "no_table":
            conn.execute("DROP TABLE gap_forecasts")
        else:
            conn.execute("UPDATE gap_forecasts SET payload = '{}' WHERE rowid = 1")
    assert stored(path) is None
