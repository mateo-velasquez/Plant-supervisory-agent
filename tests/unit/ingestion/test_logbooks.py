"""005 T4: 'read_logbook_texts' loads shift logbooks through the held-out guard (E8, FR-40)."""

import re
from pathlib import Path

import pytest

from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.logbooks import read_logbook_texts

from builders import held_out_policy


def write_logbook(directory: Path) -> None:
    """'T01.txt' with a UTF-8 BOM and CRLF line ends, written as bytes."""
    (directory / "T01.txt").write_bytes(b"\xef\xbb\xbf" + "Línea 1\r\nLínea 2\r\n".encode())


def test_e8_a_bom_and_crlf_are_stripped(tmp_path: Path) -> None:
    write_logbook(tmp_path)
    texts = read_logbook_texts(tmp_path, ["T01"], held_out_policy("T03", is_open=True))
    assert texts == {"T01": "Línea 1\nLínea 2\n"}


def test_e8_b_missing_file_names_it(tmp_path: Path) -> None:
    write_logbook(tmp_path)
    with pytest.raises(DataLoadError, match=r"T02\.txt"):
        read_logbook_texts(tmp_path, ["T02"], held_out_policy("T03", is_open=True))


def forbid_file_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every 'Path' open or read fail the test."""

    def boom(*args: object, **kwargs: object) -> object:
        raise AssertionError("a file was accessed")

    for name in ("open", "read_text", "read_bytes", "is_file", "exists"):
        monkeypatch.setattr(Path, name, boom)


def test_e8_c_refusal_comes_before_any_file_is_opened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_logbook(tmp_path)
    (tmp_path / "T03.txt").write_text("held out", encoding="utf-8")
    policy = held_out_policy("T03")
    forbid_file_access(monkeypatch)
    with pytest.raises(DataLoadError) as info:
        read_logbook_texts(tmp_path, ["T01", "T03"], policy)
    message = str(info.value)
    assert "T03" in message
    assert "held out" in message
    assert "not found" not in message


@pytest.mark.parametrize("turno_id", ["./T03", "t03"])
def test_e8_d_spelling_variants_of_a_held_out_id_are_refused_unopened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, turno_id: str
) -> None:
    """Guards against a path trick or a case change slipping past the guard."""
    write_logbook(tmp_path)
    (tmp_path / "T03.txt").write_text("held out", encoding="utf-8")
    policy = held_out_policy("T03")
    forbid_file_access(monkeypatch)
    with pytest.raises(DataLoadError, match=re.escape(turno_id)):
        read_logbook_texts(tmp_path, [turno_id], policy)
