"""Typed loaders for the plant CSVs (`utf-8-sig`); rows are reported by physical line (header = 1)."""

import csv
from pathlib import Path

from pydantic import ValidationError

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import FrozenModel, PlanRow, Shift, Shipment, StandardTime
from plant_monitor.ingestion.errors import DataLoadError, describe_validation_error

type PlanKey = tuple[str, Model, Market]


def _read_rows[M: FrozenModel](path: Path, model: type[M]) -> list[tuple[int, M]]:
    """Validate every CSV row into `model`, paired with its line number; empty cells become None."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = [
            name for name, info in model.model_fields.items() if info.is_required() and name not in columns
        ]
        if missing:
            raise DataLoadError(f"{path}: missing columns: {', '.join(missing)}")
        rows: list[tuple[int, M]] = []
        for raw in reader:
            line = reader.line_num
            if None in raw:
                raise DataLoadError(f"{path}, row {line}: more cells than header columns")
            values = {key: (value or None) for key, value in raw.items()}
            try:
                rows.append((line, model.model_validate(values)))
            except ValidationError as exc:
                raise DataLoadError(f"{path}, row {line}: {describe_validation_error(exc)}") from exc
    return rows


def _combination(key: PlanKey) -> str:
    """Render a plan key's combination as `modelo/mercado`."""
    return f"{key[1]}/{key[2]}"


def load_plan(path: Path, shifts: list[Shift]) -> list[PlanRow]:
    """Load `plan_produccion.csv`; every shift needs exactly one row per model and market combination."""
    rows = _read_rows(path, PlanRow)
    known_shifts = {shift.turno_id for shift in shifts}
    first_line: dict[PlanKey, int] = {}
    problems: list[str] = []
    for line, row in rows:
        key = (row.turno_id, row.modelo, row.mercado)
        if row.turno_id not in known_shifts:
            problems.append(f"row {line}: shift {row.turno_id} ({_combination(key)}) is not in turnos.csv")
        elif key in first_line:
            problems.append(
                f"row {line}: duplicate row for shift {row.turno_id}, {_combination(key)}"
                f" (first at row {first_line[key]})"
            )
        else:
            first_line[key] = line
    for shift in shifts:
        for model in Model:
            for market in Market:
                key = (shift.turno_id, model, market)
                if key not in first_line:
                    problems.append(f"shift {shift.turno_id} has no row for {_combination(key)}")
    if problems:
        raise DataLoadError(f"{path}: {'; '.join(problems)}")
    return [row for _, row in rows]


def load_standards(path: Path) -> list[StandardTime]:
    """Load `tiempos_estandar.csv`."""
    return [row for _, row in _read_rows(path, StandardTime)]


def load_shipments(path: Path) -> list[Shipment]:
    """Load `embarques.csv`."""
    return [row for _, row in _read_rows(path, Shipment)]


def load_shifts(path: Path) -> list[Shift]:
    """Load `turnos.csv`; `fecha` is kept raw and `inicio`/`fin` carry the time."""
    return [row for _, row in _read_rows(path, Shift)]
