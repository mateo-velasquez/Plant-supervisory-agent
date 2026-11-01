"""Loader for one snapshot JSON (`Sxxx.json`), read as UTF-8 and validated into a `Snapshot`."""

import json
from pathlib import Path

from pydantic import ValidationError

from plant_monitor.domain.models import Snapshot
from plant_monitor.ingestion.errors import DataLoadError, describe_validation_error


def load_snapshot(path: Path) -> Snapshot:
    """Load and validate a snapshot; errors name the file and the failing field."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DataLoadError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return Snapshot.model_validate(raw)
    except ValidationError as exc:
        raise DataLoadError(f"{path}: {describe_validation_error(exc)}") from exc
