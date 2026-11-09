"""008 T2: registry schema v3, its v2 migration and the cause store (E2, E3)."""

import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest

from plant_monitor.cases.registry import CauseStore, SqliteRegistry
from plant_monitor.cases.registry import sqlite as sqlite_module
from plant_monitor.cases.registry.schema import MIGRATION_V2_TO_V3, SCHEMA_V2_BODY, SCHEMA_VERSION
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import ActiveCause, CauseCategory, CauseScope, CitedCause, Evidence
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import SnapshotCommit

from builders import case_with, history_row

NEW_TABLES = {"active_causes", "active_cause_links", "case_causes"}
PL = "S010-Pickup-Local"
AC2_ID = "S010-causa-1"
EVIDENCE = Evidence(bitacora="T05", fragmento="se paró la línea de montaje de Pickup")
SCOPE = CauseScope(modelo=Model.PICKUP, etapa=Stage.ASSEMBLY, mercado=None)
AC2 = ActiveCause(
    active_cause_id=AC2_ID,
    categoria=CauseCategory.LINE_STOP,
    scope=SCOPE,
    opened_at="S010",
    opened_by=EVIDENCE,
)
CITED = CitedCause(
    categoria=CauseCategory.LINE_STOP,
    etapa=Stage.ASSEMBLY,
    evidence=EVIDENCE,
    set_at="S010",
    active_cause_id=AC2_ID,
)


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
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


def make_v2_file(path: Path) -> None:
    """A version 2 file from the frozen v2 schema holding one case, its history row and one notice."""
    with closing(sqlite3.connect(path, autocommit=True)) as conn:
        conn.executescript(f"BEGIN;\n{SCHEMA_V2_BODY}\nPRAGMA user_version = 2;\nCOMMIT;")
        conn.execute(
            "INSERT INTO cases VALUES (?, 'Pickup', 'Local', 'S010', 'abierto', 'media', 0, 'media',"
            " 'media', 0, 'S010', NULL, NULL, NULL, NULL)",
            (PL,),
        )
        conn.execute(
            "INSERT INTO case_history VALUES (?, 'S010', 1, 'abierto', 'media', 0, 'media', -2.0, NULL,"
            " 0.0, 'montaje', 0)",
            (PL,),
        )
        conn.execute(
            "INSERT INTO notices VALUES ('S010-alerta_inmediata-S010-Pickup-Local', 'S010', 1, 0, 'notice',"
            " 'alerta_inmediata', ?, '{}', NULL)",
            (PL,),
        )


def test_e2a_new_file_is_version_three_with_the_cause_tables_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path):
        pass
    assert user_version(path) == 3 == SCHEMA_VERSION
    assert table_names(path) >= NEW_TABLES
    with SqliteRegistry(path) as again:
        assert again.causes.in_force() == ()


def test_e2b_version_two_file_is_migrated_in_place_keeping_its_rows(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    make_v2_file(path)
    before = {t: dump(path, t) for t in ("cases", "case_history", "notices")}
    with SqliteRegistry(path):
        pass
    assert user_version(path) == 3
    assert {t: dump(path, t) for t in before} == before
    assert table_names(path) >= NEW_TABLES
    assert all(dump(path, t) == [] for t in NEW_TABLES)
    with SqliteRegistry(path) as again:
        assert again.causes.in_force() == ()


@pytest.mark.parametrize("version", [1, 7])
def test_e2cd_other_versions_raise_naming_file_found_and_three_and_leave_the_file(
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
    assert "3" in message
    assert user_version(path) == version
    assert table_names(path) == {"processed_snapshots"}


def test_e2e_fresh_v3_file_and_migrated_v2_file_have_the_same_schema(tmp_path: Path) -> None:
    fresh, migrated = tmp_path / "fresh.sqlite3", tmp_path / "migrated.sqlite3"
    with SqliteRegistry(fresh):
        pass
    make_v2_file(migrated)
    with SqliteRegistry(migrated):
        pass
    assert master(fresh) == master(migrated)


def test_e2f_failing_migration_statement_rolls_back_and_leaves_version_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "r.sqlite3"
    make_v2_file(path)
    statements = [s for s in MIGRATION_V2_TO_V3.split(";") if s.strip()]
    statements[1] = "SELECT * FROM table_that_does_not_exist"
    monkeypatch.setattr(sqlite_module, "MIGRATION_V2_TO_V3", ";\n".join(statements) + ";")
    with pytest.raises(sqlite3.Error):
        SqliteRegistry(path)
    assert user_version(path) == 2
    assert not NEW_TABLES & table_names(path)


def write_all(store: CauseStore) -> None:
    """E3 writes: open AC2, link PL, set PL's cited cause."""
    store.open(AC2)
    store.link(AC2_ID, PL, "S010")
    store.set_cited(PL, CITED)


def save_pl(registry: SqliteRegistry) -> None:
    """PL's case and its S010 history row, in the open unit."""
    registry.cases.save_case(
        case_with(PL, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM),
        history_row(PL, "S010", Stage.ASSEMBLY),
    )


def test_e3_cause_writes_commit_with_the_snapshot_and_survive_reopen(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as first, first.processing(commit("S010")):
        save_pl(first)
        write_all(first.causes)
    with SqliteRegistry(path) as second:
        assert second.causes.in_force() == (AC2,)
        assert second.causes.get_active(AC2_ID) == AC2
        assert second.causes.cited([PL]) == {PL: CITED}
    with closing(sqlite3.connect(path)) as conn:
        links = conn.execute("SELECT active_cause_id, case_id, linked_at FROM active_cause_links").fetchall()
    assert links == [(AC2_ID, PL, "S010")]


WRITES: dict[str, Callable[[CauseStore, str], None]] = {
    "open": lambda s, at: s.open(AC2.model_copy(update={"opened_at": at})),
    "lift": lambda s, at: s.lift(AC2_ID, at, EVIDENCE),
    "link": lambda s, at: s.link(AC2_ID, PL, at),
    "set_cited": lambda s, at: s.set_cited(PL, CITED.model_copy(update={"set_at": at})),
}


@pytest.mark.parametrize("name", list(WRITES))
def test_e3a_write_outside_processing_raises_runtime_error(name: str) -> None:
    with SqliteRegistry(":memory:") as registry, pytest.raises(RuntimeError):
        WRITES[name](registry.causes, "S010")


@pytest.mark.parametrize("name", list(WRITES))
def test_e3b_write_stamped_for_another_snapshot_names_both_ids(name: str) -> None:
    with SqliteRegistry(":memory:") as registry, registry.processing(commit("S010")):
        save_pl(registry)
        registry.causes.open(AC2)
        with pytest.raises(ValueError) as error:
            WRITES[name](registry.causes, "S011")
    assert "S010" in str(error.value)
    assert "S011" in str(error.value)


def test_e3c_failed_unit_of_work_stores_no_cause_write() -> None:
    with SqliteRegistry(":memory:") as registry:
        with pytest.raises(RuntimeError, match="boom"), registry.processing(commit("S010")):
            save_pl(registry)
            write_all(registry.causes)
            raise RuntimeError("boom")
        assert registry.causes.in_force() == ()
        assert registry.causes.cited([PL]) == {}


def test_active_causes_keep_their_opening_order_through_seq() -> None:
    """Risk: 'in_force' sorts by id, so a later-opened cause with a lower id would come first."""
    second = AC2.model_copy(
        update={
            "active_cause_id": "S010-causa-2",
            "scope": SCOPE.model_copy(update={"mercado": Market.LOCAL}),
        }
    )
    with SqliteRegistry(":memory:") as registry, registry.processing(commit("S010")):
        registry.causes.open(second)
        registry.causes.open(AC2)
        assert [c.active_cause_id for c in registry.causes.in_force()] == ["S010-causa-2", AC2_ID]
