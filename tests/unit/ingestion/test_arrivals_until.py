"""005 T3: 'load_arrivals_until' streams llegadas.csv up to the allowed set (E6, E7, Q-37)."""

import re
from pathlib import Path

import pytest

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import load_arrivals_until

from builders import held_out_policy

HEADER = "orden,snapshot_id,archivo,recibido"
BAD_DATE = "not-a-date"


def row(orden: str, snapshot_id: str, recibido: str = "2026-03-02T10:05") -> str:
    """One llegadas.csv data line with the file named after the snapshot."""
    return f"{orden},{snapshot_id},{snapshot_id}.json,{recibido}"


def write_arrivals(directory: Path, rows: list[str]) -> Path:
    """Write llegadas.csv as UTF-8 with BOM."""
    path = directory / "llegadas.csv"
    path.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8-sig", newline="\n")
    return path


def e6_rows() -> list[str]:
    """E6 rows: S003 repeats before the allowed set completes; row 6 has an unparseable date."""
    return [
        row("1", "S001", "2026-03-02T10:02"),
        row("2", "S002", "2026-03-02T14:01"),
        row("3", "S003", "2026-03-02T18:03"),
        row("4", "S003", "2026-03-02T18:30"),
        row("5", "S004", "2026-03-02T22:02"),
        row("6", "S005", BAD_DATE),
    ]


def until_error(path: Path, policy: HeldOutPolicy) -> str:
    """Message of the DataLoadError raised by 'load_arrivals_until'."""
    with pytest.raises(DataLoadError) as info:
        load_arrivals_until(path, policy)
    return str(info.value)


def names_row(message: str, line_no: int) -> bool:
    """True if the message names the physical line as 'row N' or 'line N'."""
    return re.search(rf"\b(?:row|line) {line_no}\b", message, flags=re.IGNORECASE) is not None


@pytest.mark.parametrize("is_open", [False, True], ids=["closed", "open"])
def test_e6_stops_after_the_row_that_completes_the_allowed_set(tmp_path: Path, is_open: bool) -> None:
    path = write_arrivals(tmp_path, e6_rows())
    arrivals = load_arrivals_until(path, held_out_policy("T03", is_open=is_open))
    assert [a.orden for a in arrivals] == [1, 2, 3, 4, 5]
    assert [a.snapshot_id for a in arrivals] == ["S001", "S002", "S003", "S003", "S004"]
    assert arrivals[0].archivo == tmp_path / "S001.json"


def test_e6_file_handle_is_closed_on_return(tmp_path: Path) -> None:
    """On Windows an open handle would make the delete fail."""
    path = write_arrivals(tmp_path, e6_rows())
    load_arrivals_until(path, held_out_policy("T03"))
    path.unlink()
    assert not path.exists()


def test_e7_a_out_of_order_orden_names_line_3(tmp_path: Path) -> None:
    rows = e6_rows()
    path = write_arrivals(tmp_path, [rows[0], rows[2], rows[1], rows[3], rows[4]])
    message = until_error(path, held_out_policy("T03"))
    assert names_row(message, 3), message
    assert "orden" in message
    assert "expected 2" in message


@pytest.mark.parametrize("is_open", [False, True], ids=["closed", "open"])
def test_e7_b_held_out_snapshot_row_is_refused_even_when_open(tmp_path: Path, is_open: bool) -> None:
    rows = e6_rows()
    rows[3] = row("4", "S005", "2026-03-02T18:30")
    message = until_error(write_arrivals(tmp_path, rows), held_out_policy("T03", is_open=is_open))
    assert names_row(message, 5), message
    assert "S005" in message
    assert "held out" in message


def test_e7_c_file_ending_before_completion_names_the_missing_snapshot(tmp_path: Path) -> None:
    message = until_error(write_arrivals(tmp_path, e6_rows()[:4]), held_out_policy("T03"))
    assert "S004" in message
    assert "ends before" in message


def test_e7_d_first_row_with_orden_2_names_line_2(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("2", "S001"), row("3", "S002")])
    message = until_error(path, held_out_policy("T03"))
    assert names_row(message, 2), message
    assert "orden" in message
    assert "expected 1" in message


def test_e7_e_schema_error_in_a_row_read_names_line_3_and_field(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001"), row("2", "S002", "yesterday")])
    message = until_error(path, held_out_policy("T03"))
    assert names_row(message, 3), message
    assert "recibido" in message


def test_e7_f_empty_allowed_set_raises_value_error(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, e6_rows())
    with pytest.raises(ValueError, match="allowed"):
        load_arrivals_until(path, held_out_policy("T01"))


def test_e7_g_late_repeat_after_completion_is_not_read(tmp_path: Path) -> None:
    """Documented limitation (Q-37): the set completes at row 4, so the row-5 repeat is never read."""
    rows = [row("1", "S001"), row("2", "S002"), row("3", "S003"), row("4", "S004")]
    path = write_arrivals(tmp_path, [*rows, row("5", "S003"), row("6", "S005", BAD_DATE)])
    arrivals = load_arrivals_until(path, held_out_policy("T03"))
    assert [a.snapshot_id for a in arrivals] == ["S001", "S002", "S003", "S004"]
