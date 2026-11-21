"""Run report of the full-series CLI: tokens, arrivals, scopes, text and JSON (012 R7, R9)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.runner.series import RunSummary
from plant_monitor.telemetry.run_report import (
    Arrivals,
    RunReport,
    RunScope,
    SeriesScope,
    Status,
    Tokens,
    report_path,
)
from plant_monitor.telemetry.trace import (
    ISO_Z_FORMAT,
    USD_DECIMALS,
    TraceLine,
    TraceMode,
    budget_exceeded_steps,
    run_totals,
)

__all__ = ["Mode", "RunOutcome", "build_report", "render_report", "report_path"]

Mode = TraceMode


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
