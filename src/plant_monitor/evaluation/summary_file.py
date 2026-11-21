"""Stored evaluation summary: the byte-level writer and the reader of 'eval-<stamp>.json' (015 R10)."""

import json
import os
import re
import tempfile
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, ValidationError

EVAL_NAME: Final = re.compile(r"eval-(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json")
_JSON_NAME: Final = "eval-{stamp:%Y%m%dT%H%M%SZ}.json"
_JSON_INDENT: Final = 2
_TEMP_PREFIX: Final = "."
_TEMP_SUFFIX: Final = ".tmp"


class SectionCounts(BaseModel):
    """Gated and not gated tallies of one section."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    gated: dict[str, int] = {}
    not_gated: dict[str, int] = {}


class StoredNoise(BaseModel):
    """The noise errors of a stored summary."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    errors: int


class StoredSummary(BaseModel):
    """The fields of a stored summary the dashboard reads."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    registry: str
    capabilities: list[str]
    covered_shifts: list[str]
    alerts: SectionCounts
    news: SectionCounts
    causes: SectionCounts = SectionCounts()
    noise: StoredNoise
    gating_errors: int
    exit_code: int
    deliverables: int | None = None


def read_summary(path: Path) -> StoredSummary:
    """Parse a stored summary; any read or shape failure becomes a named 'ValueError'."""
    try:
        return StoredSummary.model_validate_json(path.read_bytes())
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        raise ValueError(f"{path.name} is not a readable evaluation summary") from error


def write_summary_json(data: Mapping[str, object], directory: Path, at: datetime) -> Path:
    """Write 'eval-<UTC stamp>.json' under 'directory' (created if missing); 'at' must be aware."""
    if at.utcoffset() is None:
        raise ValueError("the summary time must be timezone-aware")
    stamp = at.astimezone(UTC)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _JSON_NAME.format(stamp=stamp)
    text = json.dumps(data, ensure_ascii=False, indent=_JSON_INDENT) + "\n"
    _write_atomic(path, text.encode("utf-8"))
    return path


# Kept apart from 'telemetry/run_report.py' and 'notify/atomic.py' on purpose (layer rules).
def _write_atomic(target: Path, data: bytes) -> None:
    """Write through a temp file in the same directory and replace; the temp never survives an error."""
    fd, temp_name = tempfile.mkstemp(dir=target.parent, prefix=_TEMP_PREFIX, suffix=_TEMP_SUFFIX)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temp_name, target)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
