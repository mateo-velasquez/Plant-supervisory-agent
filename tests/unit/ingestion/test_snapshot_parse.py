"""002 T5: parse_snapshot validates snapshot bytes already read; load_snapshot delegates to it (E6b)."""

import json
from pathlib import Path

import pytest

from plant_monitor.domain.models import Snapshot
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.snapshot import load_snapshot, parse_snapshot

from builders import snapshot_payload, unit_payload


def encode(payload: dict[str, object]) -> bytes:
    """UTF-8 JSON bytes with non-ASCII kept literal, as in the real files."""
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def write_bytes(tmp_path: Path, data: bytes, name: str) -> Path:
    """Write raw bytes to a file named like a snapshot."""
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_e6b_a_valid_bytes_equal_load_snapshot_of_the_same_file(tmp_path: Path) -> None:
    path = write_bytes(tmp_path, encode(snapshot_payload()), "S001.json")
    parsed = parse_snapshot(path.read_bytes(), path)
    assert isinstance(parsed, Snapshot)
    assert parsed == load_snapshot(path)
    assert parsed.snapshot_id == "S001"


def test_e6b_a_non_ascii_values_decoded_as_utf8() -> None:
    parsed = parse_snapshot(encode(snapshot_payload()), Path("S001.json"))
    assert parsed.unidades[0].modelo.value == "Sedán"


def test_parse_snapshot_does_not_read_the_source_path(tmp_path: Path) -> None:
    source = tmp_path / "absent" / "S001.json"
    parsed = parse_snapshot(encode(snapshot_payload()), source)
    assert parsed.snapshot_id == "S001"
    assert not source.exists()


def test_e6b_b_truncated_json_names_the_source() -> None:
    with pytest.raises(DataLoadError) as info:
        parse_snapshot(b'{"snapshot_id": "S002", "unidades": [', Path("S002.json"))
    assert "S002.json" in str(info.value)


def test_e6b_c_non_utf8_bytes_name_the_source() -> None:
    with pytest.raises(DataLoadError) as info:
        parse_snapshot(b"\xff\xfe", Path("S002.json"))
    assert "S002.json" in str(info.value)


def test_schema_error_names_the_source_and_the_field() -> None:
    unit = unit_payload()
    del unit["etapa"]
    with pytest.raises(DataLoadError) as info:
        parse_snapshot(encode(snapshot_payload(snapshot_id="S002", unidades=[unit])), Path("S002.json"))
    assert "S002.json" in str(info.value)
    assert "etapa" in str(info.value)


@pytest.mark.parametrize(
    "data",
    [
        b'{"snapshot_id": "S002", "unidades": [',
        b"\xff\xfe",
        encode(snapshot_payload(timestamp="3/2/2026 10:00")),
    ],
    ids=["truncated", "non-utf8", "schema"],
)
def test_load_snapshot_errors_match_parse_snapshot_errors(tmp_path: Path, data: bytes) -> None:
    path = write_bytes(tmp_path, data, "S002.json")
    with pytest.raises(DataLoadError) as from_bytes:
        parse_snapshot(data, path)
    with pytest.raises(DataLoadError) as from_file:
        load_snapshot(path)
    assert str(from_bytes.value) == str(from_file.value)
