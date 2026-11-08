"""005 T5: 'read_deliverables', the read-only reader of a registry's reports and alerts (E40)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.domain.notices import PendingDelivery

from eval_builders import E40_ALERT, E40_T01, E40_T02, write_e40_registry


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    """E40's closed registry file."""
    path = tmp_path / "registry.sqlite3"
    write_e40_registry(path)
    return path


def test_e40a_deliverables_come_in_processing_order_delivered_and_pending_alike(registry_path: Path) -> None:
    assert read_deliverables(registry_path) == (E40_T01, E40_ALERT, E40_T02)


def test_e40b_reading_leaves_the_file_unchanged(registry_path: Path) -> None:
    before = registry_path.read_bytes()
    listing = sorted(p.name for p in registry_path.parent.iterdir())
    read_deliverables(registry_path)
    assert registry_path.read_bytes() == before
    assert sorted(p.name for p in registry_path.parent.iterdir()) == listing


def test_e40g_a_corrupt_payload_row_raises_naming_the_file(tmp_path: Path) -> None:
    """A bad stored row must surface as a 'ValueError', not a raw parse error."""
    path = tmp_path / "corrupt.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE notices (seq INTEGER, idx INTEGER, kind TEXT, tipo TEXT, payload TEXT)")
        conn.execute("INSERT INTO notices VALUES (1, 0, 'report', 'informe_de_turno', '{not json')")
        conn.commit()
    with pytest.raises(ValueError, match=r"corrupt\.sqlite3"):
        read_deliverables(path)


def test_e40h_a_file_that_is_not_sqlite_raises_naming_the_file(tmp_path: Path) -> None:
    """Any 'sqlite3.Error' must be reported as a 'ValueError' naming the file."""
    path = tmp_path / "garbage.sqlite3"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(ValueError, match=r"garbage\.sqlite3"):
        read_deliverables(path)


def test_e40c_a_missing_path_raises_naming_it_and_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite3"
    with pytest.raises(ValueError, match=r"nope\.sqlite3"):
        read_deliverables(missing)
    assert not missing.exists()


def test_e40d_a_notices_table_without_payload_raises_naming_file_and_column(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE notices (seq INTEGER, idx INTEGER, kind TEXT, tipo TEXT)")
        conn.commit()
    with pytest.raises(ValueError) as error:
        read_deliverables(path)
    assert "old.sqlite3" in str(error.value)
    assert "payload" in str(error.value)


def test_e40e_a_fresh_registry_has_no_deliverables(tmp_path: Path) -> None:
    path = tmp_path / "fresh.sqlite3"
    with SqliteRegistry(path):
        pass
    assert read_deliverables(path) == ()


def test_e40f_pending_is_unchanged_through_the_shared_filter(registry_path: Path) -> None:
    with SqliteRegistry(registry_path) as registry:
        assert registry.notices.pending() == (
            PendingDelivery("S003-alerta_inmediata-S001-Sedán-Local", E40_ALERT),
            PendingDelivery("T02-informe", E40_T02),
        )
