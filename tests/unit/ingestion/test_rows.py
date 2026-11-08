"""005 T3: 'iter_rows' streams validated CSV rows; 'read_rows' is built on it (plan: ingestion/rows.py)."""

import inspect
from pathlib import Path

import pytest

from plant_monitor.domain.models import FrozenModel
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.rows import iter_rows, read_rows


class _Pair(FrozenModel):
    """Two-column row for the reader tests."""

    a: int
    b: str


def write_csv(path: Path, lines: list[str]) -> Path:
    """Write a CSV as UTF-8 with BOM, like the real data."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8-sig", newline="\n")
    return path


def test_iter_rows_is_a_generator_yielding_physical_lines(tmp_path: Path) -> None:
    rows = iter_rows(write_csv(tmp_path / "p.csv", ["a,b", "1,x", "2,y"]), _Pair)
    assert inspect.isgenerator(rows)
    assert list(rows) == [(2, _Pair(a=1, b="x")), (3, _Pair(a=2, b="y"))]


def test_iter_rows_validates_lazily_so_earlier_rows_are_yielded(tmp_path: Path) -> None:
    """The arrivals reader relies on never parsing rows after the one it stops at."""
    rows = iter_rows(write_csv(tmp_path / "p.csv", ["a,b", "1,x", "oops,y"]), _Pair)
    assert next(rows) == (2, _Pair(a=1, b="x"))
    with pytest.raises(DataLoadError, match="row 3"):
        next(rows)


def test_iter_rows_checks_missing_columns_on_first_next(tmp_path: Path) -> None:
    rows = iter_rows(write_csv(tmp_path / "p.csv", ["a", "1"]), _Pair)
    with pytest.raises(DataLoadError, match="missing columns: b"):
        next(rows)


def test_read_rows_equals_the_list_of_iter_rows(tmp_path: Path) -> None:
    path = write_csv(tmp_path / "p.csv", ["a,b", "1,x", "2,y"])
    assert read_rows(path, _Pair) == list(iter_rows(path, _Pair))
