"""Trace records of the agent loop and the run's JSON-lines trace file (R13, R14)."""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, field_serializer

from plant_monitor.telemetry.usage import PriceCard, Usage, cost_usd


@dataclass(frozen=True)
class ModelCallRecord:
    """One model request: usage and latency, no cost (R13)."""

    turn: int
    stop_reason: str
    usage: Usage
    latency_ms: int


@dataclass(frozen=True)
class ToolCallRecord:
    """One tool call the model asked for, run or refused."""

    turn: int
    name: str
    arguments: Mapping[str, object]
    is_error: bool
    result_chars: int
    error: str | None
    latency_ms: int


logger = logging.getLogger(__name__)

USD_DECIMALS = Decimal(1).scaleb(-8)
DecisionReason = Literal["text_needed", "proposals", "investigator_only", "no_text_needed", "closing_review"]
InvestigatorTrigger = Literal["review", "cause_lookup"]
AgentName = Literal["investigator", "coordinator"]
AGENTS: tuple[AgentName, ...] = ("investigator", "coordinator")


def _usd(value: Decimal) -> Decimal:
    return value.quantize(USD_DECIMALS)


class TraceModelCall(BaseModel):
    """A model request as written to the trace, with its cost."""

    model_config = ConfigDict(frozen=True)

    turn: int
    stop_reason: str
    usage: Usage
    usd: Decimal
    latency_ms: int

    @field_serializer("usd")
    def _write_usd(self, value: Decimal) -> float:
        return float(_usd(value))


class TraceToolCall(BaseModel):
    """A tool call as written to the trace."""

    model_config = ConfigDict(frozen=True)

    turn: int
    name: str
    arguments: dict[str, JsonValue]
    is_error: bool
    result_chars: int
    error: str | None
    latency_ms: int


class TraceTotals(BaseModel):
    """Tokens and cost of one snapshot's model calls."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_5m_tokens: int = 0
    cache_write_1h_tokens: int = 0
    usd: Decimal = Decimal(0)

    @field_serializer("usd")
    def _write_usd(self, value: Decimal) -> float:
        return float(_usd(value))


@dataclass(frozen=True)
class InvestigatorRecord:
    """What the investigator step hands to the trace, uncosted (009 R14)."""

    outcome: str
    logbooks: Sequence[str]
    missing: Sequence[str]
    marks: Mapping[str, str]
    proposals: Sequence[Mapping[str, JsonValue]]
    control_errors: Sequence[Sequence[str]]
    model_calls: Sequence[ModelCallRecord]
    tool_calls: Sequence[ToolCallRecord]
    thinking: Sequence[str]
    trigger: InvestigatorTrigger = "review"


class TraceInvestigator(BaseModel):
    """The investigator's entry in a trace line, costed."""

    model_config = ConfigDict(frozen=True)

    outcome: str
    logbooks: list[str]
    missing: list[str]
    marks: dict[str, str]
    proposals: list[dict[str, JsonValue]]
    control_errors: list[list[str]]
    model_calls: list[TraceModelCall]
    tool_calls: list[TraceToolCall]
    thinking: list[str]
    totals: TraceTotals
    trigger: InvestigatorTrigger = "review"


class TraceLine(BaseModel):
    """One snapshot's line in the run trace; 'totals' sums every agent and may differ from 'model_calls'."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    turno_id: str
    status: Literal["committed", "aborted"]
    decision: Literal["call", "skip"]
    decision_reason: DecisionReason | None
    outcome: str
    required: list[str]
    model_calls: list[TraceModelCall]
    tool_calls: list[TraceToolCall]
    thinking: list[str]
    notices_agent: list[str]
    notices_template: list[str]
    report_id: str | None
    totals: TraceTotals
    hooks: list[str] = []
    agents_run: list[AgentName] | None = None
    investigator: TraceInvestigator | None = None
    proposals_applied: list[str] = []
    proposals_declined: list[str] = []

    @property
    def ran(self) -> list[AgentName]:
        """The agents that ran; lines without 'agents_run' fall back on 'decision'."""
        if self.agents_run is not None:
            return self.agents_run
        return ["coordinator"] if self.decision == "call" else []


class AgentRunTotals(BaseModel):
    """One agent's share of a run: lines that ran it, calls, tokens and cost."""

    model_config = ConfigDict(frozen=True)

    runs: int = 0
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usd: Decimal = Decimal(0)


class RunTotals(BaseModel):
    """Sums over a run's trace lines, aborted ones included; 'model_calls' counts both agents."""

    model_config = ConfigDict(frozen=True)

    snapshots: int
    called: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    usd: Decimal
    by_agent: dict[AgentName, AgentRunTotals] = {}


def _costed(calls: Sequence[ModelCallRecord], card: PriceCard) -> tuple[list[TraceModelCall], TraceTotals]:
    """Each call costed, and their totals."""
    costed = [
        TraceModelCall(
            turn=c.turn,
            stop_reason=c.stop_reason,
            usage=c.usage,
            usd=cost_usd(c.usage, card),
            latency_ms=c.latency_ms,
        )
        for c in calls
    ]
    totals = TraceTotals(
        input_tokens=sum(c.usage.input_tokens for c in costed),
        output_tokens=sum(c.usage.output_tokens for c in costed),
        cache_read_tokens=sum(c.usage.cache_read_tokens for c in costed),
        cache_write_5m_tokens=sum(c.usage.cache_write_5m_tokens for c in costed),
        cache_write_1h_tokens=sum(c.usage.cache_write_1h_tokens for c in costed),
        usd=sum((c.usd for c in costed), Decimal(0)),
    )
    return costed, totals


def _sum_totals(first: TraceTotals, second: TraceTotals) -> TraceTotals:
    """Field-wise sum of two totals."""
    return TraceTotals(
        input_tokens=first.input_tokens + second.input_tokens,
        output_tokens=first.output_tokens + second.output_tokens,
        cache_read_tokens=first.cache_read_tokens + second.cache_read_tokens,
        cache_write_5m_tokens=first.cache_write_5m_tokens + second.cache_write_5m_tokens,
        cache_write_1h_tokens=first.cache_write_1h_tokens + second.cache_write_1h_tokens,
        usd=first.usd + second.usd,
    )


def _tool_calls(calls: Sequence[ToolCallRecord]) -> list[TraceToolCall]:
    """Tool calls as written to the trace."""
    return [
        TraceToolCall.model_validate(
            {
                "turn": t.turn,
                "name": t.name,
                "arguments": dict(t.arguments),
                "is_error": t.is_error,
                "result_chars": t.result_chars,
                "error": t.error,
                "latency_ms": t.latency_ms,
            }
        )
        for t in calls
    ]


def _trace_investigator(record: InvestigatorRecord, card: PriceCard) -> TraceInvestigator:
    """The record costed."""
    calls, totals = _costed(record.model_calls, card)
    return TraceInvestigator(
        outcome=record.outcome,
        logbooks=list(record.logbooks),
        missing=list(record.missing),
        marks=dict(record.marks),
        proposals=[dict(p) for p in record.proposals],
        control_errors=[list(e) for e in record.control_errors],
        model_calls=calls,
        tool_calls=_tool_calls(record.tool_calls),
        thinking=list(record.thinking),
        totals=totals,
        trigger=record.trigger,
    )


def build_line(
    *,
    snapshot_id: str,
    turno_id: str,
    status: str,
    decision: str,
    decision_reason: str | None,
    outcome: str,
    required: Sequence[str],
    model_calls: Sequence[ModelCallRecord],
    tool_calls: Sequence[ToolCallRecord],
    thinking: Sequence[str],
    notices_agent: Sequence[str],
    notices_template: Sequence[str],
    report_id: str | None,
    card: PriceCard,
    agents_run: Sequence[str] = (),
    investigator: InvestigatorRecord | None = None,
    proposals_applied: Sequence[str] = (),
    proposals_declined: Sequence[str] = (),
) -> TraceLine:
    """Cost each call and total every agent here; the loop knows no prices (R13, R14)."""
    calls, totals = _costed(model_calls, card)
    traced = None if investigator is None else _trace_investigator(investigator, card)
    if traced is not None:
        totals = _sum_totals(totals, traced.totals)
    return TraceLine.model_validate(
        {
            "snapshot_id": snapshot_id,
            "turno_id": turno_id,
            "status": status,
            "decision": decision,
            "decision_reason": decision_reason,
            "outcome": outcome,
            "required": list(required),
            "model_calls": calls,
            "tool_calls": _tool_calls(tool_calls),
            "thinking": list(thinking),
            "notices_agent": list(notices_agent),
            "notices_template": list(notices_template),
            "report_id": report_id,
            "totals": totals,
            "agents_run": list(agents_run),
            "investigator": traced,
            "proposals_applied": list(proposals_applied),
            "proposals_declined": list(proposals_declined),
        }
    )


def abort_outcome(error: BaseException) -> str:
    """The only place that formats 'aborted:<ErrorClass>'."""
    return f"aborted:{type(error).__name__}"


def trace_path(directory: Path, started: datetime) -> Path:
    """One file per run, named after the UTC start."""
    return directory / f"trace-{started.astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')}.jsonl"


class TraceWriter:
    """Appends trace lines; a committed line is staged until the post-commit step (R14)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._staged: TraceLine | None = None

    def stage(self, line: TraceLine) -> None:
        """Keep the line for 'after_commit', replacing (with a warning) any one already staged."""
        if self._staged is not None:
            logger.warning("trace line for %s replaced by %s", self._staged.snapshot_id, line.snapshot_id)
        self._staged = line

    def after_commit(self) -> None:
        """Append the staged line and clear it; nothing staged is a no-op."""
        line, self._staged = self._staged, None
        if line is not None:
            self.write_now(line)

    def write_now(self, line: TraceLine) -> None:
        """Append at once; an 'OSError' is logged here and never raised."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line.model_dump_json() + "\n")
        except OSError:
            logger.exception("could not write the trace line of %s to %s", line.snapshot_id, self._path)


def read_trace(path: Path) -> tuple[TraceLine, ...]:
    """Every line of a trace file, in order."""
    text = path.read_text(encoding="utf-8")
    return tuple(TraceLine.model_validate_json(row) for row in text.split("\n") if row)


def run_totals(lines: Iterable[TraceLine]) -> RunTotals:
    """Sum over the lines, aborted ones included."""
    rows = tuple(lines)
    by_agent: dict[AgentName, AgentRunTotals] = {}
    for agent in AGENTS:
        costs = [
            call
            for row in rows
            for call in (
                row.model_calls
                if agent == "coordinator"
                else (row.investigator.model_calls if row.investigator else [])
            )
        ]
        by_agent[agent] = AgentRunTotals(
            runs=sum(agent in row.ran for row in rows),
            model_calls=len(costs),
            input_tokens=sum(call.usage.input_tokens for call in costs),
            output_tokens=sum(call.usage.output_tokens for call in costs),
            usd=sum((call.usd for call in costs), Decimal(0)),
        )
    return RunTotals(
        snapshots=len(rows),
        called=sum(row.decision == "call" for row in rows),
        model_calls=sum(
            len(row.model_calls) + (0 if row.investigator is None else len(row.investigator.model_calls))
            for row in rows
        ),
        by_agent=by_agent,
        input_tokens=sum(row.totals.input_tokens for row in rows),
        output_tokens=sum(row.totals.output_tokens for row in rows),
        usd=sum((row.totals.usd for row in rows), Decimal(0)),
    )
