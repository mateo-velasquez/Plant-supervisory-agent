"""Loader for `llegadas.csv`: the order in which snapshots reached the plant."""

from pathlib import Path

from pydantic import NaiveDatetime, PositiveInt, field_validator

from plant_monitor.domain.models import FrozenModel
from plant_monitor.ingestion.errors import DataLoadError
from plant_monitor.ingestion.rows import read_rows

FORBIDDEN_NAME_CHARS = '/\\:*?"<>|'
FORBIDDEN_NAME_ENDINGS = ". "
RELATIVE_NAMES = (".", "..")


class Arrival(FrozenModel):
    """One snapshot delivery with its file resolved against the CSV directory."""

    orden: PositiveInt
    snapshot_id: str
    archivo: Path
    recibido: NaiveDatetime


class _ArrivalRow(FrozenModel):
    """Raw `llegadas.csv` row; `archivo` must be a bare file name."""

    orden: PositiveInt
    snapshot_id: str
    archivo: str
    recibido: NaiveDatetime

    @field_validator("archivo")
    @classmethod
    def _bare_name(cls, value: str) -> str:
        if (
            value in RELATIVE_NAMES
            or any(char in value for char in FORBIDDEN_NAME_CHARS)
            or value.endswith(tuple(FORBIDDEN_NAME_ENDINGS))
        ):
            raise ValueError(
                f"must be a portable bare file name: none of {FORBIDDEN_NAME_CHARS!r}, "
                f"no trailing {' or '.join(repr(c) for c in FORBIDDEN_NAME_ENDINGS)}"
            )
        return value


def load_arrivals(path: Path) -> list[Arrival]:
    """Load `llegadas.csv` sorted by `orden`; `archivo` is resolved against the CSV directory, not checked."""
    first_line: dict[int, int] = {}
    rows = read_rows(path, _ArrivalRow)
    for line, row in rows:
        if row.orden in first_line:
            raise DataLoadError(
                f"{path}, row {line}: field 'orden': duplicate value {row.orden}"
                f" (first at row {first_line[row.orden]})"
            )
        first_line[row.orden] = line
    arrivals = [
        Arrival(
            orden=row.orden,
            snapshot_id=row.snapshot_id,
            archivo=path.parent / row.archivo,
            recibido=row.recibido,
        )
        for _, row in rows
    ]
    return sorted(arrivals, key=lambda arrival: arrival.orden)
