"""Shared synthetic snapshot builders for tests; payloads mirror the `Sxxx.json` data contract."""

import json
from pathlib import Path


def unit_payload(**overrides: object) -> dict[str, object]:
    """Snapshot unit as it appears in Sxxx.json."""
    payload: dict[str, object] = {
        "unidad_id": "U00001",
        "modelo": "Sedán",
        "mercado": "Local",
        "color": "Gris Plata",
        "etapa": "montaje",
        "ingreso_etapa": "2026-03-02T08:00",
        "retrabajos": 0,
        "embarque_asignado": "LOC-0302",
    }
    payload.update(overrides)
    return payload


def released_payload(**overrides: object) -> dict[str, object]:
    """Released unit as it appears in Sxxx.json liberadas."""
    payload: dict[str, object] = {
        "unidad_id": "U00900",
        "modelo": "SUV",
        "mercado": "Brasil",
        "hora": "2026-03-02T06:21",
    }
    payload.update(overrides)
    return payload


def snapshot_payload(
    units: list[dict[str, object]] | None = None,
    released: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Snapshot payload with S001 defaults: two units and one release."""
    payload: dict[str, object] = {
        "snapshot_id": "S001",
        "timestamp": "2026-03-02T10:00",
        "turno": "T01",
        "unidades": units
        if units is not None
        else [
            unit_payload(),
            unit_payload(
                unidad_id="U00002",
                modelo="SUV",
                mercado="Brasil",
                etapa="pintura",
                ingreso_etapa="2026-03-02T09:00",
                retrabajos=1,
                embarque_asignado="BRA-0303",
            ),
        ],
        "liberadas": released if released is not None else [released_payload()],
    }
    payload.update(overrides)
    return payload


def write_snapshot(tmp_path: Path, payload: dict[str, object], name: str = "S001.json") -> Path:
    """Write a snapshot JSON as UTF-8 with non-ASCII kept literal."""
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path
