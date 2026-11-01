"""002 T7: load_arrivals reads llegadas.csv into Arrival records sorted by orden (E2, E3, E4, E5)."""

import codecs
import csv
import re
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import Arrival, load_arrivals

ARRIVALS_CSV = "llegadas.csv"
HEADER = "orden,snapshot_id,archivo,recibido"


def quoted(value: str) -> str:
    """CSV-quote a cell so quotes, commas and trailing spaces survive verbatim."""
    return '"' + value.replace('"', '""') + '"'


def row(orden: str, snapshot_id: str, archivo: str | None = None, recibido: str = "2026-03-02T10:05") -> str:
    """One llegadas.csv data line; `archivo` defaults to `<snapshot_id>.json` and is always quoted."""
    name = archivo if archivo is not None else snapshot_id + ".json"
    return f"{orden},{snapshot_id},{quoted(name)},{recibido}"


def write_arrivals(directory: Path, rows: list[str], header: str = HEADER) -> Path:
    """Write llegadas.csv with a UTF-8 BOM; no snapshot files are created (the loader never checks them)."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ARRIVALS_CSV
    path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8-sig", newline="\n")
    return path


def load_error(path: Path) -> str:
    """Message of the DataLoadError raised by load_arrivals, with the directory masked out."""
    with pytest.raises(DataLoadError) as info:
        load_arrivals(path)
    return str(info.value).replace(str(path.parent), "<dir>")


def names_row(message: str, line_no: int) -> bool:
    """True if the message names the given row as `row N` or `line N`."""
    return re.search(rf"\b(?:row|line) {line_no}\b", message, flags=re.IGNORECASE) is not None


def assert_names(message: str, line_no: int, field: str) -> None:
    """The message names llegadas.csv, the physical line and the field."""
    assert ARRIVALS_CSV in message, message
    assert names_row(message, line_no), message
    assert field in message, message


# --- happy paths ---


def test_e2_loader_returns_arrivals_sorted_by_orden_not_file_order(tmp_path: Path) -> None:
    path = write_arrivals(
        tmp_path,
        [
            row("3", "S003", recibido="2026-03-02T10:05"),
            row("1", "S001", recibido="2026-03-02T18:05"),
            row("2", "S002", recibido="2026-03-02T14:05"),
        ],
    )
    arrivals = load_arrivals(path)
    assert [a.orden for a in arrivals] == [1, 2, 3]
    assert [a.snapshot_id for a in arrivals] == ["S001", "S002", "S003"]


def test_e2_loader_returns_arrival_records(tmp_path: Path) -> None:
    arrivals = load_arrivals(write_arrivals(tmp_path, [row("1", "S001")]))
    assert isinstance(arrivals, list)
    assert all(isinstance(a, Arrival) for a in arrivals)


def test_e3_bom_is_stripped_so_first_column_is_orden(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001"), row("2", "S002")])
    assert path.read_bytes().startswith(codecs.BOM_UTF8)
    arrivals = load_arrivals(path)
    assert [a.orden for a in arrivals] == [1, 2]


def test_e5_archivo_resolved_against_the_csv_directory(tmp_path: Path) -> None:
    snaps = tmp_path / "snaps"
    path = write_arrivals(snaps, ["1,S001,S001.json,2026-03-02T10:05"])
    assert load_arrivals(path) == [
        Arrival(
            orden=1, snapshot_id="S001", archivo=snaps / "S001.json", recibido=datetime(2026, 3, 2, 10, 5)
        )
    ]


def test_e5_recibido_parsed_as_naive_datetime(tmp_path: Path) -> None:
    (arrival,) = load_arrivals(write_arrivals(tmp_path, [row("1", "S001", recibido="2026-03-02T10:05")]))
    assert arrival.recibido == datetime(2026, 3, 2, 10, 5)
    assert arrival.recibido.tzinfo is None


def test_snapshot_id_may_repeat_across_rows(tmp_path: Path) -> None:
    path = write_arrivals(
        tmp_path,
        [
            row("1", "S034", "S034.json", "2026-03-07T22:05"),
            row("2", "S034", "S034.json", "2026-03-07T22:35"),
        ],
    )
    arrivals = load_arrivals(path)
    assert [(a.orden, a.snapshot_id) for a in arrivals] == [(1, "S034"), (2, "S034")]
    assert arrivals[0].archivo == arrivals[1].archivo == tmp_path / "S034.json"


def test_repeated_snapshot_id_may_point_to_different_files(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S034", "S034.json"), row("2", "S034", "S034_bis.json")])
    arrivals = load_arrivals(path)
    assert [a.archivo.name for a in arrivals] == ["S034.json", "S034_bis.json"]


def test_absent_archivo_file_still_loads_with_resolved_path(tmp_path: Path) -> None:
    snaps = tmp_path / "snaps"
    path = write_arrivals(snaps, [row("1", "S001")])
    (arrival,) = load_arrivals(path)
    assert not (snaps / "S001.json").exists()
    assert arrival.archivo == snaps / "S001.json"


def test_header_only_file_returns_empty_list(tmp_path: Path) -> None:
    assert load_arrivals(write_arrivals(tmp_path, [])) == []


# --- E4: malformed rows ---


def test_empty_archivo_cell_names_row_2(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001", archivo="")])
    assert_names(load_error(path), 2, "archivo")


def test_e4_a_duplicate_orden_names_row_4_and_cites_row_3(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001"), row("2", "S002"), row("2", "S003")])
    message = load_error(path)
    assert_names(message, 4, "orden")
    assert names_row(message, 3), message


def test_e4_b_non_integer_orden_names_row_3(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001"), row("x", "S002")])
    assert_names(load_error(path), 3, "orden")


def test_e4_c_non_iso_recibido_names_row_2(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001", recibido="3/2/2026 10:05")])
    assert_names(load_error(path), 2, "recibido")


@pytest.mark.parametrize(
    "archivo",
    ["../S001.json", "sub\\S001.json", "C:S001.json", "..", ".", "sub/S001.json", "/S001.json"],
    ids=["e4d-parent", "e4f-backslash", "e4g-drive-colon", "e4h-dotdot", "dot", "slash", "absolute"],
)
def test_e4_non_bare_archivo_names_row_2(tmp_path: Path, archivo: str) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001", archivo)])
    assert_names(load_error(path), 2, "archivo")


@pytest.mark.parametrize("orden", ["0", "-1"], ids=["e4e-zero", "negative"])
def test_e4_e_non_positive_orden_names_row_2(tmp_path: Path, orden: str) -> None:
    path = write_arrivals(tmp_path, [row(orden, "S001")])
    assert_names(load_error(path), 2, "orden")


@pytest.mark.parametrize(
    "archivo",
    [
        "S001.json.",
        "S001.json ",
        "S0*01.json",
        "S0?01.json",
        'S0"01.json',
        "S0<01.json",
        "S0>01.json",
        "S0|01.json",
    ],
    ids=["trailing-dot", "trailing-space", "star", "question", "quote", "less", "greater", "pipe"],
)
def test_non_portable_archivo_names_row_2(tmp_path: Path, archivo: str) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001", archivo)])
    with path.open(encoding="utf-8-sig", newline="") as handle:
        assert [cells["archivo"] for cells in csv.DictReader(handle)] == [archivo]
    assert_names(load_error(path), 2, "archivo")


def test_timezone_aware_recibido_names_row_2(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, [row("1", "S001", recibido="2026-03-02T10:05:00+00:00")])
    assert_names(load_error(path), 2, "recibido")


def test_missing_column_names_file_and_field(tmp_path: Path) -> None:
    path = write_arrivals(tmp_path, ["1,S001,2026-03-02T10:05"], header="orden,snapshot_id,recibido")
    message = load_error(path)
    assert ARRIVALS_CSV in message, message
    assert "archivo" in message, message


# --- Arrival model ---


def arrival(**overrides: object) -> Arrival:
    """Arrival validated from E5-like values with optional overrides."""
    values: dict[str, object] = {
        "orden": 1,
        "snapshot_id": "S001",
        "archivo": Path("snaps") / "S001.json",
        "recibido": datetime(2026, 3, 2, 10, 5),
    }
    values.update(overrides)
    return Arrival.model_validate(values)


def test_arrival_valid_fields() -> None:
    a = arrival()
    assert a.orden == 1
    assert a.snapshot_id == "S001"
    assert a.archivo == Path("snaps") / "S001.json"
    assert a.recibido == datetime(2026, 3, 2, 10, 5)


@pytest.mark.parametrize("orden", [0, -1])
def test_arrival_rejects_non_positive_orden(orden: int) -> None:
    with pytest.raises(ValidationError, match="orden"):
        arrival(orden=orden)


def test_arrival_rejects_timezone_aware_recibido() -> None:
    with pytest.raises(ValidationError, match="recibido"):
        arrival(recibido="2026-03-02T10:05:00+00:00")


def test_arrival_is_frozen() -> None:
    a = arrival()
    with pytest.raises(ValidationError):
        setattr(a, "orden", 2)  # noqa: B010
