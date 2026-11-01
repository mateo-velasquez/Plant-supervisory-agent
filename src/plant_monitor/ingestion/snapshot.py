"""Loader for one snapshot JSON (`Sxxx.json`), read as UTF-8 and validated into a `Snapshot`."""

import json
from pathlib import Path

from pydantic import ValidationError

from plant_monitor.domain.models import Snapshot
from plant_monitor.ingestion.errors import DataLoadError, describe_validation_error


def parse_snapshot(data: bytes, source: Path) -> Snapshot:
    """Validate raw snapshot bytes; `source` only labels errors and the filesystem is never touched."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DataLoadError(f"{source}: invalid JSON: {exc}") from exc
    try:
        return Snapshot.model_validate(raw)
    except ValidationError as exc:
        raise DataLoadError(f"{source}: {describe_validation_error(exc)}") from exc


def load_snapshot(path: Path) -> Snapshot:
    """Load and validate a snapshot file; errors name the file and the failing field."""
    return parse_snapshot(path.read_bytes(), path)
