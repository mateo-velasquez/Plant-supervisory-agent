"""Builders for the 015 metrics tests: costed model calls, trace lines and a 'RunView' over them."""

import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from dashboard_builders import HOST, app_of, run_view
from incident_builders import INCIDENTS, incident_shifts

from plant_monitor.cases.registry.run_reader import RunRows
from plant_monitor.config import Settings
from plant_monitor.dashboard.source import Calendar, RunView
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.evaluation.noise import NoiseScore
from plant_monitor.evaluation.summary import EvalSummary
from plant_monitor.evaluation.summary_file import write_summary_json
from plant_monitor.telemetry.trace import TraceInvestigator, TraceLine, TraceModelCall, TraceTotals
from plant_monitor.telemetry.usage import Usage

_TRACE_FILE = "trace-20260302T230000Z.jsonl"
# T5: the spec's CAL, the incidents calendar (T01-T03 on 3/2/2026, T04-T06 on 3/3/2026), guard open.
CAL = Calendar.load(INCIDENTS / "planta", HeldOutPolicy.from_calendar(incident_shifts(), "T06", is_open=True))


def MT(settings: Settings, query: str = "") -> dict[str, Any]:
    """The spec's MT(s, q): the parsed JSON of 'GET /api/metrics?q' on the app over 'settings'."""
    body: dict[str, Any] = json.loads(app_of(settings).handle("GET", f"/api/metrics?{query}", HOST).body)
    return body


def call(
    usd: float | str,
    latency: int = 0,
    in_: int = 0,
    out: int = 0,
    cr: int = 0,
    w5: int = 0,
    w1: int = 0,
) -> TraceModelCall:
    """The spec's C(usd, latency, in, out, cr, w5, w1): one costed model call, omitted counts 0."""
    usage = Usage(
        input_tokens=in_,
        output_tokens=out,
        cache_read_tokens=cr,
        cache_write_5m_tokens=w5,
        cache_write_1h_tokens=w1,
    )
    return TraceModelCall(
        turn=1, stop_reason="end_turn", usage=usage, usd=Decimal(str(usd)), latency_ms=latency
    )


def eval_file(
    directory: Path,
    at: datetime,
    registry: str | Path,
    *,
    covered_shifts: Sequence[str] = ("T05",),
    deliverables: int | None = 8,
) -> Path:
    """The spec's EVAL: an 'eval-<stamp>.json' for 'registry'; a 'None' count leaves the key out."""
    summary = EvalSummary(
        registry=str(registry),
        golden="evals/golden",
        capabilities=frozenset(),
        covered_shifts=tuple(covered_shifts),
        alerts=(),
        news=(),
        noise=NoiseScore(repeats=(), duplicate_alerts=()),
        deliverables=deliverables,
    )
    data = summary.to_json()
    if deliverables is None:
        del data["deliverables"]
    return write_summary_json(data, directory, at)


def _totals(calls: Sequence[TraceModelCall], usd: Decimal | None = None) -> TraceTotals:
    """Totals summed from 'calls'; 'usd' overrides the summed cost."""
    return TraceTotals(
        input_tokens=sum(c.usage.input_tokens for c in calls),
        output_tokens=sum(c.usage.output_tokens for c in calls),
        cache_read_tokens=sum(c.usage.cache_read_tokens for c in calls),
        cache_write_5m_tokens=sum(c.usage.cache_write_5m_tokens for c in calls),
        cache_write_1h_tokens=sum(c.usage.cache_write_1h_tokens for c in calls),
        usd=sum((c.usd for c in calls), Decimal(0)) if usd is None else usd,
    )


def metric_line(
    snapshot_id: str,
    coord: Sequence[TraceModelCall] = (),
    inv: Sequence[TraceModelCall] = (),
    *,
    status: Literal["committed", "aborted"] = "committed",
    totals_usd: float | str | None = None,
) -> TraceLine:
    """The spec's LN: a line whose totals are summed from its calls unless 'totals_usd' overrides the USD."""
    investigator = (
        TraceInvestigator(
            outcome="done",
            logbooks=[],
            missing=[],
            marks={},
            proposals=[],
            control_errors=[],
            model_calls=list(inv),
            tool_calls=[],
            thinking=[],
            totals=_totals(inv),
        )
        if inv
        else None
    )
    return TraceLine(
        snapshot_id=snapshot_id,
        turno_id="T01",
        status=status,
        decision="call" if coord or inv else "skip",
        decision_reason=None,
        outcome="done",
        required=[],
        model_calls=list(coord),
        tool_calls=[],
        thinking=[],
        notices_agent=[],
        notices_template=[],
        report_id=None,
        totals=_totals([*coord, *inv], None if totals_usd is None else Decimal(str(totals_usd))),
        agents_run=["investigator", "coordinator"] if inv else ["coordinator"] if coord else [],
        investigator=investigator,
    )


def metric_view(rows: RunRows, lines: Sequence[TraceLine]) -> RunView:
    """The spec's MV: a 'RunView' in agent mode over hand-built rows and trace lines."""
    attempts = tuple((_TRACE_FILE, line) for line in lines)
    aborted: dict[str, tuple[tuple[str, TraceLine], ...]] = {}
    for attempt in attempts:
        if attempt[1].status == "aborted":
            aborted[attempt[1].snapshot_id] = (*aborted.get(attempt[1].snapshot_id, ()), attempt)
    return replace(
        run_view(rows),
        lines=attempts,
        committed={line.snapshot_id: line for line in lines if line.status == "committed"},
        aborted=aborted,
        mode="agent",
    )
