"""The run report file: models, path, atomic write and read (012 R7, 015 R13)."""

import os
import re
import tempfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer

from plant_monitor.telemetry.trace import (
    STAMP_FORMAT,
    USD_DECIMALS,
    AgentName,
    AgentRunTotals,
    BudgetStep,
    RunTotals,
    TraceMode,
)

Status = Literal["ok", "aborted", "interrupted"]

REPORT_NAME: Final = re.compile(r"run-(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json")
_TEMP_PREFIX: Final = "."
_TEMP_SUFFIX: Final = ".tmp"


class Tokens(BaseModel):
    """Calls, tokens and cost of one scope, as written to the report."""

    model_config = ConfigDict(frozen=True)

    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    usd: Decimal = Decimal(0)

    @field_serializer("usd")
    def _write_usd(self, value: Decimal) -> float:
        return float(value.quantize(USD_DECIMALS))

    @classmethod
    def of(cls, totals: RunTotals | AgentRunTotals) -> Self:
        """The report's tokens from a trace total."""
        return cls(
            model_calls=totals.model_calls,
            input_tokens=totals.input_tokens,
            output_tokens=totals.output_tokens,
            cache_read_tokens=totals.cache_read_tokens,
            cache_write_5m_tokens=totals.cache_write_5m_tokens,
            cache_write_1h_tokens=totals.cache_write_1h_tokens,
            usd=totals.usd,
        )


class Arrivals(BaseModel):
    """Snapshot ids a run processed and skipped."""

    model_config = ConfigDict(frozen=True)

    processed: tuple[str, ...]
    skipped: tuple[str, ...]


class RunScope(BaseModel):
    """What this run did, read from its own trace file."""

    model_config = ConfigDict(frozen=True)

    arrivals: Arrivals | None
    anomalies: int
    tokens: Tokens
    by_agent: dict[AgentName, Tokens]
    budget_exceeded: tuple[BudgetStep, ...]


class SeriesScope(BaseModel):
    """The whole series so far: every trace file and the registry's deliverables."""

    model_config = ConfigDict(frozen=True)

    tokens: Tokens
    shift_reports: int
    alerts: int


class RunReport(BaseModel):
    """The run report; the field order is the JSON key order. New fields need a default."""

    model_config = ConfigDict(frozen=True)

    mode: TraceMode
    status: Status
    started_at: AwareDatetime
    duration_seconds: float
    aborted_at: str | None
    cause: str | None
    run: RunScope
    series: SeriesScope


def report_path(directory: Path, started: datetime) -> Path:
    """One file per run, named after the UTC start."""
    return directory / f"run-{started.astimezone(UTC).strftime(STAMP_FORMAT)}.json"


# Kept apart from 'evaluation/summary_file.py' and 'notify/atomic.py' on purpose (layer rules).
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


def write_report(report: RunReport, path: Path) -> None:
    """Write the report as indented JSON, atomically, creating the directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(path, (report.model_dump_json(indent=2) + "\n").encode("utf-8"))


def read_report(path: Path) -> RunReport:
    """The report in a file; anything unreadable raises 'ValueError'."""
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"{path.name} is not a readable run report") from exc
    return parse_report(data, path.name)


def parse_report(data: bytes, name: str) -> RunReport:
    """The report in 'data'; a bad shape raises 'ValueError' naming 'name'."""
    try:
        return RunReport.model_validate_json(data)
    except ValueError as exc:
        raise ValueError(f"{name} is not a readable run report") from exc
