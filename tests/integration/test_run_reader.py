"""014 T3: 'read_run_rows' over TH_DIR and AGENT_DIR, read-only (R2, E16, E22, E23, E24, I3, I7)."""

import ast
import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import trace_builders
from trace_builders import copied

from plant_monitor.cases.registry.notices import is_deliverable, read_deliverables
from plant_monitor.cases.registry.run_reader import RegistryBusy, read_run_rows
from plant_monitor.config import Settings

from builders import isolate_settings_env

agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir

PACKAGE = Path(__file__).resolve().parents[2] / "src" / "plant_monitor"
REGISTRY_DIR = PACKAGE / "cases" / "registry"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _count(path: Path, table: str) -> int:
    with closing(sqlite3.connect(path)) as conn:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def test_i3_rows_are_in_seq_order_and_counts_match_sql(thresholds_dir: Settings) -> None:
    """014 I3 (R2): rows come in 'seq' order and every table holds as many rows as the registry."""
    path = thresholds_dir.registry_path
    rows = read_run_rows(path)
    assert rows is not None
    assert [p.snapshot_id for p in rows.processed] == [f"S{n:03d}" for n in range(1, 13)]
    assert [p.seq for p in rows.processed] == sorted(p.seq for p in rows.processed)
    seqs = [h.seq for h in rows.history]
    assert seqs == sorted(seqs)
    keys = [(n.seq, n.idx) for n in rows.notices]
    assert keys == sorted(keys)
    assert len(rows.processed) == _count(path, "processed_snapshots")
    assert len(rows.cases) == _count(path, "cases")
    assert len(rows.history) == _count(path, "case_history")
    assert len(rows.notices) == _count(path, "notices")


@pytest.mark.parametrize("fixture", ["thresholds_dir", "agent_dir"])
def test_e23_deliverables_agree_with_read_deliverables(fixture: str, request: pytest.FixtureRequest) -> None:
    """014 E23 (I3, R7): 'is_deliverable' over every notice row equals 'read_deliverables'."""
    settings: Settings = request.getfixturevalue(fixture)
    rows = read_run_rows(settings.registry_path)
    assert rows is not None
    mine = [n.item for n in rows.notices if is_deliverable(n.item)]
    assert mine == list(read_deliverables(settings.registry_path))
    assert mine


def test_r2_missing_registry_gives_none_and_is_not_created(tmp_path: Path) -> None:
    """014 R2: a missing file returns 'None' and nothing is created."""
    path = tmp_path / "out" / "registry.sqlite3"
    assert read_run_rows(path) is None
    assert not path.exists()
    assert not path.parent.exists()


def test_e16_not_sqlite_file_raises_unreadable_registry_without_values(tmp_path: Path) -> None:
    """014 E16 (I7): a file that is not sqlite gives the 500 message, class name only."""
    path = tmp_path / "registry.sqlite3"
    path.write_bytes(b"not sqlite")
    with pytest.raises(
        ValueError, match=r"\Adashboard: registry\.sqlite3 is not a readable registry \(DatabaseError\)\Z"
    ) as error:
        read_run_rows(path)
    assert not isinstance(error.value, RegistryBusy)


def test_r2_reading_changes_no_bytes_and_creates_no_files(thresholds_dir: Settings, tmp_path: Path) -> None:
    """014 R2 (E17): the registry bytes and the output tree are the same after reading."""
    settings = copied(thresholds_dir, tmp_path)
    before = hashlib.sha256(settings.registry_path.read_bytes()).hexdigest()
    names = sorted(p.name for p in settings.output_dir.rglob("*"))
    assert read_run_rows(settings.registry_path) is not None
    assert hashlib.sha256(settings.registry_path.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in settings.output_dir.rglob("*")) == names


def test_e24_locked_registry_raises_busy_then_reads_after_release(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """014 E24 (R2): a write lock gives 'RegistryBusy', not corruption; released, it reads."""
    path = copied(thresholds_dir, tmp_path).registry_path
    real_connect = sqlite3.connect

    def quick(database: str, *, uri: bool, autocommit: bool, timeout: float) -> sqlite3.Connection:
        return real_connect(database, timeout=0.05, uri=uri, autocommit=autocommit)

    monkeypatch.setattr(sqlite3, "connect", quick)
    with closing(real_connect(path, isolation_level=None)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        with pytest.raises(RegistryBusy) as error:
            read_run_rows(path)
        assert str(error.value) == "dashboard: registry busy"
        writer.execute("ROLLBACK")
    assert read_run_rows(path) is not None


def test_e22_run_reader_and_readonly_import_only_domain_and_registry() -> None:
    """014 E22 (R16): 'run_reader.py' and 'readonly.py' import only 'domain' and 'cases.registry'."""
    allowed = ("plant_monitor.domain", "plant_monitor.cases.registry")
    for name in ("run_reader.py", "readonly.py"):
        tree = ast.parse((REGISTRY_DIR / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = ["plant_monitor", "cases", "registry"][: 3 - node.level + 1] if node.level else []
                modules = [".".join([*base, *(node.module.split(".") if node.module else [])])]
            for module in modules:
                if module.split(".")[0] == "plant_monitor":
                    assert module.startswith(allowed), f"{name} imports {module}"
