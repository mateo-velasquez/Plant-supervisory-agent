"""009 T6: registry schema v4, its migration chain and the review store (R7, E12)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.registry import schema as schema_module
from plant_monitor.cases.registry.schema import (
    MIGRATION_V2_TO_V3_BODY,
    MIGRATION_V3_TO_V4_BODY,
    SCHEMA_V2_BODY,
)
from plant_monitor.cases.reviews import LogbookReview
from plant_monitor.domain.models import SnapshotCommit

PL = "S010-Pickup-Local"
T05_FAILED = LogbookReview(
    turno_id="T05", attempts=1, last_attempt_at="S010", reviewed_at=None, given_up_at=None
)


def user_version(path: Path) -> int:
    """PRAGMA user_version of a SQLite file, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def master(path: Path) -> set[tuple[str, str, str | None]]:
    """The (type, name, sql) entries of 'sqlite_master', internal tables excluded."""
    with closing(sqlite3.connect(path)) as conn:
        rows = conn.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
    return {(str(r[0]), str(r[1]), r[2]) for r in rows}


def table_names(path: Path) -> set[str]:
    """Names of the tables of a SQLite file."""
    return {name for kind, name, _ in master(path) if kind == "table"}


def dump(path: Path, table: str) -> list[tuple[object, ...]]:
    """All rows of a table, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def make_old_file(path: Path, version: int) -> None:
    """A v2 or v3 file from the frozen bodies, holding one case (and one active cause at v3)."""
    body = SCHEMA_V2_BODY + (MIGRATION_V2_TO_V3_BODY if version == 3 else "")
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        conn.executescript(f"BEGIN;\n{body}\nPRAGMA user_version = {version};\nCOMMIT;")
        conn.execute(
            "INSERT INTO cases VALUES (?, 'Pickup', 'Local', 'S010', 'abierto', 'media', 0, 'media',"
            " 'media', 0, 'S010', NULL, NULL, NULL, NULL)",
            (PL,),
        )
        if version == 3:
            conn.execute(
                "INSERT INTO active_causes (active_cause_id, seq, categoria, modelo, etapa, mercado,"
                " opened_at, opened_bitacora, opened_fragmento) VALUES"
                " ('S010-causa-1', 1, 'parada_de_linea', 'Pickup', 'montaje', NULL, 'S010', 'T05', 'f')"
            )


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def test_e12a_new_file_is_version_four_with_the_reviews_table_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path):
        pass
    assert user_version(path) == 4
    assert "logbook_reviews" in table_names(path)
    with SqliteRegistry(path) as again:
        assert again.reviews.get(["T05"]) == {}


@pytest.mark.parametrize("version", [2, 3])
def test_e12bc_older_files_migrate_in_place_keeping_their_rows(tmp_path: Path, version: int) -> None:
    path = tmp_path / "r.sqlite3"
    make_old_file(path, version)
    before = {t: dump(path, t) for t in table_names(path)}
    with SqliteRegistry(path):
        pass
    assert user_version(path) == 4
    assert {t: dump(path, t) for t in before} == before
    assert dump(path, "logbook_reviews") == []


@pytest.mark.parametrize("version", [1, 7])
def test_e12d_other_versions_raise_naming_file_found_and_four_and_leave_the_file(
    tmp_path: Path, version: int
) -> None:
    path = tmp_path / "r.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE processed_snapshots (snapshot_id TEXT PRIMARY KEY)")
        conn.execute(f"PRAGMA user_version = {version}")
    with pytest.raises(ValueError) as error:
        SqliteRegistry(path)
    message = str(error.value).replace(str(path), "")
    assert path.name in str(error.value)
    assert str(version) in message
    assert "4" in message
    assert user_version(path) == version
    assert table_names(path) == {"processed_snapshots"}


def test_e12e_fresh_and_migrated_files_have_the_same_schema(tmp_path: Path) -> None:
    fresh = tmp_path / "fresh.sqlite3"
    with SqliteRegistry(fresh):
        pass
    for version in (2, 3):
        migrated = tmp_path / f"v{version}.sqlite3"
        make_old_file(migrated, version)
        with SqliteRegistry(migrated):
            pass
        assert master(migrated) == master(fresh)


def test_e12f_failing_v3_to_v4_step_rolls_back_and_leaves_version_three(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "r.sqlite3"
    make_old_file(path, 3)
    failing = f"{MIGRATION_V3_TO_V4_BODY}\nSELECT * FROM table_that_does_not_exist;"
    monkeypatch.setattr(schema_module, "STEPS", {**schema_module.STEPS, 3: failing})
    with pytest.raises(sqlite3.Error):
        SqliteRegistry(path)
    assert user_version(path) == 3
    assert "logbook_reviews" not in table_names(path)


def test_e12g_review_written_in_processing_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as first, first.processing(commit("S010")):
        first.reviews.save(T05_FAILED)
    with SqliteRegistry(path) as second:
        assert second.reviews.get(["T05", "T06"]) == {"T05": T05_FAILED}


def test_e12h_review_write_outside_processing_raises_runtime_error() -> None:
    with SqliteRegistry(":memory:") as registry, pytest.raises(RuntimeError):
        registry.reviews.save(T05_FAILED)


def test_e12i_review_stamped_for_another_snapshot_names_both_ids() -> None:
    stale = T05_FAILED.model_copy(update={"last_attempt_at": "S011"})
    with (
        SqliteRegistry(":memory:") as registry,
        registry.processing(commit("S010")),
        pytest.raises(ValueError) as error,
    ):
        registry.reviews.save(stale)
    assert "S010" in str(error.value)
    assert "S011" in str(error.value)
