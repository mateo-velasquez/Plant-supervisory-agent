"""Run report of the full-series CLI: tokens, arrivals, scopes, text and JSON (012 R7, R9)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, field_serializer

from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.runner.series import RunSummary
from plant_monitor.telemetry.trace import (
    USD_DECIMALS,
    AgentName,
    AgentRunTotals,
    BudgetStep,
    RunTotals,
    TraceLine,
    budget_exceeded_steps,
    run_totals,
)

Mode = Literal["agent", "thresholds_only"]
Status = Literal["ok", "aborted", "interrupted"]

STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
ISO_Z_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


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
    """The run report; the field order is the JSON key order."""

    model_config = ConfigDict(frozen=True)

    mode: Mode
    status: Status
    started_at: AwareDatetime
    duration_seconds: float
    aborted_at: str | None
    cause: str | None
    run: RunScope
    series: SeriesScope


@dataclass(frozen=True)
class RunOutcome:
    """How the run ended; 'aborted' holds the snapshot id and the cause."""

    status: Status
    summary: RunSummary | None
    aborted: tuple[str, str] | None
    duration_seconds: float

    def __post_init__(self) -> None:
        """Reject combinations the status cannot carry."""
        if (self.aborted is not None) != (self.status == "aborted"):
            raise ValueError("'aborted' must be set exactly when status is 'aborted'")
        if (self.summary is None) != (self.status == "interrupted"):
            raise ValueError("'summary' must be None exactly when status is 'interrupted'")


def build_report(
    *,
    mode: Mode,
    started_at: datetime,
    outcome: RunOutcome,
    run_lines: Sequence[TraceLine],
    series_lines: Sequence[TraceLine],
    deliverables: Sequence[Notice | ShiftReport],
) -> RunReport:
    """Assemble the report from the outcome, trace lines and registry deliverables."""
    summary = outcome.summary
    run = run_totals(run_lines)
    arrivals = None if summary is None else Arrivals(processed=summary.processed, skipped=summary.skipped)
    aborted_at, cause = outcome.aborted if outcome.aborted is not None else (None, None)
    return RunReport(
        mode=mode,
        status=outcome.status,
        started_at=started_at,
        duration_seconds=outcome.duration_seconds,
        aborted_at=aborted_at,
        cause=cause,
        run=RunScope(
            arrivals=arrivals,
            anomalies=0 if summary is None else len(summary.anomalies),
            tokens=Tokens.of(run),
            by_agent={agent: Tokens.of(totals) for agent, totals in run.by_agent.items()},
            budget_exceeded=budget_exceeded_steps(run_lines),
        ),
        series=SeriesScope(
            tokens=Tokens.of(run_totals(series_lines)),
            shift_reports=sum(isinstance(d, ShiftReport) for d in deliverables),
            alerts=sum(isinstance(d, Notice) for d in deliverables),
        ),
    )


def _tokens_line(label: str, tokens: Tokens) -> str:
    usd = format(tokens.usd.quantize(USD_DECIMALS), "f")
    return (
        f"{label} tokens: {tokens.model_calls} calls, input {tokens.input_tokens}, "
        f"output {tokens.output_tokens}, cache read {tokens.cache_read_tokens}, "
        f"cache write {tokens.cache_write_5m_tokens} (5m) {tokens.cache_write_1h_tokens} (1h), usd {usd}"
    )


def render_report(report: RunReport) -> str:
    """The report as fixed text lines, without the 'summary:' path line."""
    started = report.started_at.astimezone(UTC).strftime(ISO_Z_FORMAT)
    lines = [f"run: {report.mode} {report.status}, {report.duration_seconds:.1f} s, started {started}"]
    if report.aborted_at is not None:
        lines.append(f"aborted at {report.aborted_at}: {report.cause}")
    arrivals = report.run.arrivals
    anomalies = report.run.anomalies
    if arrivals is None:
        lines.append(f"arrivals: unknown (interrupted), {anomalies} anomalies")
    else:
        lines.append(
            f"arrivals: {len(arrivals.processed)} processed, {len(arrivals.skipped)} skipped, "
            f"{anomalies} anomalies"
        )
    lines.append(_tokens_line("run", report.run.tokens))
    lines.append(_tokens_line("series", report.series.tokens))
    lines.append(
        f"series deliverables: shift reports {report.series.shift_reports}, alerts {report.series.alerts}"
    )
    steps = ", ".join(f"{s.snapshot_id} {s.agent}" for s in report.run.budget_exceeded)
    lines.append(f"budget exceeded: {steps or 'none'}")
    return "\n".join(lines)


def report_path(directory: Path, started: datetime) -> Path:
    """One file per run, named after the UTC start."""
    return directory / f"run-{started.astimezone(UTC).strftime(STAMP_FORMAT)}.json"


def write_report(report: RunReport, path: Path) -> None:
    """Write the report as indented JSON, creating the directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
