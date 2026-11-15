from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from multi_agent_builders import SECOND_START

from plant_monitor.runner.series import RunSummary
from plant_monitor.runner.summary import RunOutcome, build_report, render_report, report_path
from plant_monitor.telemetry.trace import (
    InvestigatorRecord,
    ModelCallRecord,
    TraceLine,
    build_line,
    trace_path,
)
from plant_monitor.telemetry.usage import PriceCard, Usage

from notice_builders import SEDAN_LOCAL_CASE, alert_notice, shift_report

CARD = PriceCard(
    input=Decimal("0.10"),
    cache_write_5m=Decimal("0.125"),
    cache_write_1h=Decimal("0.20"),
    cache_read=Decimal("0.01"),
    output=Decimal("0.50"),
    long_context_threshold=100_000,
    long_context_multiplier=Decimal(5),
)


def _call(usage: Usage) -> ModelCallRecord:
    return ModelCallRecord(turn=1, stop_reason="end_turn", usage=usage, latency_ms=10)


def _line(
    snapshot_id: str,
    *,
    outcome: str = "done",
    status: str = "committed",
    coordinator: Usage | None = None,
    investigator: Usage | None = None,
) -> TraceLine:
    record = (
        None
        if investigator is None
        else InvestigatorRecord(
            outcome="done",
            logbooks=[],
            missing=[],
            marks={},
            proposals=[],
            control_errors=[],
            model_calls=[_call(investigator)],
            tool_calls=[],
            thinking=[],
        )
    )
    return build_line(
        snapshot_id=snapshot_id,
        turno_id="T01",
        status=status,
        decision="call",
        decision_reason="text_needed",
        outcome=outcome,
        required=[],
        model_calls=[] if coordinator is None else [_call(coordinator)],
        tool_calls=[],
        thinking=[],
        notices_agent=[],
        notices_template=[],
        report_id=None,
        card=CARD,
        investigator=record,
    )


def _e10_lines() -> tuple[list[TraceLine], list[TraceLine]]:
    run = [
        _line("S003", coordinator=Usage(input_tokens=1000, output_tokens=200, cache_write_5m_tokens=2000)),
        _line(
            "S004",
            outcome="fallback:budget_exceeded",
            investigator=Usage(input_tokens=500, output_tokens=100, cache_read_tokens=2000),
        ),
    ]
    earlier = _line(
        "S003",
        outcome="aborted:ModelCallFailed",
        status="aborted",
        coordinator=Usage(input_tokens=300, output_tokens=50),
    )
    return run, [*run, earlier]


TOKENS_RUN = {
    "model_calls": 2,
    "input_tokens": 1500,
    "output_tokens": 300,
    "cache_read_tokens": 2000,
    "cache_write_5m_tokens": 2000,
    "cache_write_1h_tokens": 0,
    "usd": 0.00057,
}
TOKENS_INVESTIGATOR = {
    "model_calls": 1,
    "input_tokens": 500,
    "output_tokens": 100,
    "cache_read_tokens": 2000,
    "cache_write_5m_tokens": 0,
    "cache_write_1h_tokens": 0,
    "usd": 0.00012,
}
TOKENS_COORDINATOR = {
    "model_calls": 1,
    "input_tokens": 1000,
    "output_tokens": 200,
    "cache_read_tokens": 0,
    "cache_write_5m_tokens": 2000,
    "cache_write_1h_tokens": 0,
    "usd": 0.00045,
}
TOKENS_SERIES = {
    "model_calls": 3,
    "input_tokens": 1800,
    "output_tokens": 350,
    "cache_read_tokens": 2000,
    "cache_write_5m_tokens": 2000,
    "cache_write_1h_tokens": 0,
    "usd": 0.000625,
}


def test_e10_report_shape_json_and_rendered_lines() -> None:
    """E10: the report sums run and series scopes; JSON and text are exact."""
    run_lines, series_lines = _e10_lines()
    outcome = RunOutcome("ok", RunSummary(("S003", "S004"), ("S001", "S002")), None, 12.5)
    report = build_report(
        mode="agent",
        started_at=SECOND_START,
        outcome=outcome,
        run_lines=run_lines,
        series_lines=series_lines,
        deliverables=[
            shift_report("T01", "S002"),
            shift_report("T02", "S004"),
            alert_notice("S003", SEDAN_LOCAL_CASE),
        ],
    )
    assert report.model_dump(mode="json") == {
        "mode": "agent",
        "status": "ok",
        "started_at": "2026-03-02T23:30:00Z",
        "duration_seconds": 12.5,
        "aborted_at": None,
        "cause": None,
        "run": {
            "arrivals": {"processed": ["S003", "S004"], "skipped": ["S001", "S002"]},
            "anomalies": 0,
            "tokens": TOKENS_RUN,
            "by_agent": {"investigator": TOKENS_INVESTIGATOR, "coordinator": TOKENS_COORDINATOR},
            "budget_exceeded": [{"snapshot_id": "S004", "agent": "coordinator"}],
        },
        "series": {"tokens": TOKENS_SERIES, "shift_reports": 2, "alerts": 1},
    }
    assert render_report(report).split("\n") == [
        "run: agent ok, 12.5 s, started 2026-03-02T23:30:00Z",
        "arrivals: 2 processed, 2 skipped, 0 anomalies",
        "run tokens: 2 calls, input 1500, output 300, cache read 2000, cache write 2000 (5m) 0 (1h), "
        "usd 0.00057000",
        "series tokens: 3 calls, input 1800, output 350, cache read 2000, cache write 2000 (5m) 0 (1h), "
        "usd 0.00062500",
        "series deliverables: shift reports 2, alerts 1",
        "budget exceeded: S004 coordinator",
    ]


def test_i5_interrupted_report_has_unknown_arrivals() -> None:
    """I5: an interrupted run has no summary, so 'arrivals' is null and the text says unknown."""
    report = build_report(
        mode="thresholds_only",
        started_at=SECOND_START,
        outcome=RunOutcome("interrupted", None, None, 1.0),
        run_lines=[],
        series_lines=[],
        deliverables=[],
    )
    assert report.run.arrivals is None
    assert "arrivals: unknown (interrupted), 0 anomalies" in render_report(report).split("\n")


def test_i12_report_path_converts_to_utc_like_trace_path(tmp_path: Path) -> None:
    """I12: a non-UTC aware start gives the UTC name, the same stamp as 'trace_path'."""
    started = datetime(2026, 3, 3, 1, 30, tzinfo=timezone(timedelta(hours=2)))
    assert report_path(tmp_path, started) == tmp_path / "run-20260302T233000Z.json"
    assert trace_path(tmp_path, started).name == "trace-20260302T233000Z.jsonl"
    assert report_path(tmp_path, started.astimezone(UTC)) == report_path(tmp_path, started)
