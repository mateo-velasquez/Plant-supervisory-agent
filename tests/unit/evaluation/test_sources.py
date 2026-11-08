"""005 T6: 'load_run_output', the registry source of a run with the held-out refusal (E9)."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from plant_monitor.evaluation.sources import load_run_output
from plant_monitor.ingestion.errors import DataLoadError

from builders import held_out_policy
from eval_builders import E40_ALERT, E40_T01, E40_T02, write_e40_registry


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    """E40's closed registry file."""
    path = tmp_path / "registry.sqlite3"
    write_e40_registry(path)
    return path


def test_e9a_an_open_policy_splits_alerts_and_reports_as_saved(registry_path: Path) -> None:
    run = load_run_output(registry_path, held_out_policy("T02", is_open=True))
    assert run.alerts == (E40_ALERT,)
    assert run.reports == (E40_T01, E40_T02)


def test_e9b_a_closed_policy_refuses_the_first_held_out_item(registry_path: Path) -> None:
    with pytest.raises(DataLoadError) as error:
        load_run_output(registry_path, held_out_policy("T02"))
    assert "S003" in str(error.value)
    assert "held out" in str(error.value)


def test_e9c_a_missing_path_raises_data_load_error_and_creates_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite3"
    with pytest.raises(DataLoadError, match=r"nope\.sqlite3"):
        load_run_output(missing, held_out_policy("T03", is_open=True))
    assert not missing.exists()


def test_e9d_a_file_without_a_notices_table_raises_data_load_error(tmp_path: Path) -> None:
    path = tmp_path / "other.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
        conn.commit()
    with pytest.raises(DataLoadError) as error:
        load_run_output(path, held_out_policy("T03", is_open=True))
    assert "other.sqlite3" in str(error.value)
    assert "notices" in str(error.value)
