from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from plant_monitor.telemetry.run_report import (
    REPORT_NAME,
    Arrivals,
    RunReport,
    RunScope,
    SeriesScope,
    Tokens,
    read_report,
    report_path,
    write_report,
)
from plant_monitor.telemetry.trace import ISO_Z_FORMAT, STAMP_FORMAT, TRACE_NAME, trace_path

STARTED = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)


def _report() -> RunReport:
    tokens = Tokens(model_calls=2, input_tokens=100, output_tokens=20, usd=Decimal("0.5"))
    return RunReport(
        mode="agent",
        status="ok",
        started_at=STARTED,
        duration_seconds=1.0,
        aborted_at=None,
        cause=None,
        run=RunScope(
            arrivals=Arrivals(processed=("S001",), skipped=()),
            anomalies=0,
            tokens=tokens,
            by_agent={"coordinator": tokens},
            budget_exceeded=(),
        ),
        series=SeriesScope(tokens=tokens, shift_reports=1, alerts=2),
    )


def test_e16_read_report_returns_what_write_report_wrote(tmp_path: Path) -> None:
    """015 E16 (R13; I5, I10): the written report reads back equal and leaves no temp file."""
    path = report_path(tmp_path / "runs", STARTED)
    report = _report()

    write_report(report, path)

    assert read_report(path) == report
    assert list(path.parent.iterdir()) == [path]


def test_i5_stamp_constants_match_the_names_the_writers_produce(tmp_path: Path) -> None:
    """Risk: a drifting stamp format makes the dashboard pair traces and reports wrongly (015 I5)."""
    stamp = STARTED.strftime(STAMP_FORMAT)
    trace = trace_path(tmp_path, STARTED)
    report = report_path(tmp_path, STARTED)

    assert stamp == "20260302T230000Z"
    assert STARTED.strftime(ISO_Z_FORMAT) == "2026-03-02T23:00:00Z"
    trace_match = TRACE_NAME.fullmatch(trace.name)
    report_match = REPORT_NAME.fullmatch(report.name)
    assert trace_match is not None and trace_match["stamp"] == stamp
    assert report_match is not None and report_match["stamp"] == stamp
