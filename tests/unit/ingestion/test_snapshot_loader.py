"""T4: load_snapshot validates one snapshot JSON into a Snapshot (US-01)."""

from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import ReleasedUnit, Snapshot, Unit
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.snapshot import load_snapshot

from builders import released_payload, snapshot_payload, unit_payload, write_snapshot


def test_valid_snapshot_loads_header_fields(tmp_path: Path) -> None:
    snapshot = load_snapshot(write_snapshot(tmp_path, snapshot_payload()))
    assert isinstance(snapshot, Snapshot)
    assert snapshot.snapshot_id == "S001"
    assert snapshot.timestamp == datetime(2026, 3, 2, 10, 0)
    assert snapshot.timestamp.tzinfo is None
    assert snapshot.turno == "T01"


def test_valid_snapshot_loads_units(tmp_path: Path) -> None:
    snapshot = load_snapshot(write_snapshot(tmp_path, snapshot_payload()))
    assert len(snapshot.unidades) == 2
    assert all(isinstance(u, Unit) for u in snapshot.unidades)
    first, second = snapshot.unidades
    assert first.modelo is Model.SEDAN
    assert first.mercado is Market.LOCAL
    assert first.etapa is Stage.ASSEMBLY
    assert first.ingreso_etapa == datetime(2026, 3, 2, 8, 0)
    assert second.etapa is Stage.PAINT
    assert second.retrabajos == 1
    assert second.embarque_asignado == "BRA-0303"


def test_valid_snapshot_loads_liberadas(tmp_path: Path) -> None:
    snapshot = load_snapshot(write_snapshot(tmp_path, snapshot_payload()))
    assert len(snapshot.liberadas) == 1
    released = snapshot.liberadas[0]
    assert isinstance(released, ReleasedUnit)
    assert released.unidad_id == "U00900"
    assert released.modelo is Model.SUV
    assert released.mercado is Market.BRAZIL
    assert released.hora == datetime(2026, 3, 2, 6, 21)


def test_snapshot_with_no_releases_loads(tmp_path: Path) -> None:
    snapshot = load_snapshot(write_snapshot(tmp_path, snapshot_payload(released=[])))
    assert snapshot.liberadas == ()


def test_unit_without_etapa_fails_naming_file_and_field(tmp_path: Path) -> None:
    unit = unit_payload()
    del unit["etapa"]
    path = write_snapshot(tmp_path, snapshot_payload(units=[unit]), name="S007.json")
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "S007.json" in str(info.value)
    assert "etapa" in str(info.value)


def test_unit_with_unknown_etapa_fails_naming_file_and_field(tmp_path: Path) -> None:
    path = write_snapshot(tmp_path, snapshot_payload(units=[unit_payload(etapa="horno")]))
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "S001.json" in str(info.value)
    assert "etapa" in str(info.value)


@pytest.mark.parametrize("bad", ["2026-03-02 10h", "3/2/2026 10:00", "ayer"])
def test_bad_timestamp_fails_naming_the_field(tmp_path: Path, bad: str) -> None:
    path = write_snapshot(tmp_path, snapshot_payload(timestamp=bad))
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "S001.json" in str(info.value)
    assert "timestamp" in str(info.value)


def test_bad_unit_ingreso_etapa_fails_naming_the_field(tmp_path: Path) -> None:
    path = write_snapshot(tmp_path, snapshot_payload(units=[unit_payload(ingreso_etapa="3/2/2026 08:00")]))
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "S001.json" in str(info.value)
    assert "ingreso_etapa" in str(info.value)


def test_bad_released_hora_fails_naming_the_field(tmp_path: Path) -> None:
    path = write_snapshot(tmp_path, snapshot_payload(released=[released_payload(hora="06:21")]))
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "S001.json" in str(info.value)
    assert "hora" in str(info.value)


def test_timezone_aware_timestamp_fails_naming_the_field(tmp_path: Path) -> None:
    path = write_snapshot(tmp_path, snapshot_payload(timestamp="2026-03-02T10:00:00Z"))
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "timestamp" in str(info.value)


def test_missing_liberadas_key_fails_naming_the_field(tmp_path: Path) -> None:
    payload = snapshot_payload()
    del payload["liberadas"]
    with pytest.raises(DataLoadError) as info:
        load_snapshot(write_snapshot(tmp_path, payload))
    assert "S001.json" in str(info.value)
    assert "liberadas" in str(info.value)


def test_invalid_json_fails_naming_the_file(tmp_path: Path) -> None:
    path = tmp_path / "S001.json"
    path.write_text('{"snapshot_id": "S001", "unidades": [', encoding="utf-8")
    with pytest.raises(DataLoadError) as info:
        load_snapshot(path)
    assert "S001.json" in str(info.value)
