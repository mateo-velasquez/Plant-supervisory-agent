"""Shared CSV row reader (`utf-8-sig`); rows are reported by physical line (header = 1)."""

import csv
from pathlib import Path

from pydantic import ValidationError

from plant_monitor.domain.models import FrozenModel
from plant_monitor.ingestion.errors import DataLoadError, describe_validation_error


def read_rows[M: FrozenModel](path: Path, model: type[M]) -> list[tuple[int, M]]:
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
