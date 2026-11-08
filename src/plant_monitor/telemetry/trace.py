"""Trace records of the agent loop and the run's JSON-lines trace file (R13, R14)."""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, computed_field, field_serializer

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
NO_TEXT_REASON = "no_text_needed"
TEXT_REASON = "text_needed"


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


class TraceLine(BaseModel):
    """One snapshot's line in the run trace (R14)."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    turno_id: str
    status: Literal["committed", "aborted"]
    decision: Literal["call", "skip"]
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def decision_reason(self) -> str:
        return TEXT_REASON if self.decision == "call" else NO_TEXT_REASON


class RunTotals(BaseModel):
    """Sums over a run's trace lines, aborted ones included (R13)."""

    model_config = ConfigDict(frozen=True)

    snapshots: int
    called: int
    model_calls: int
    input_tokens: int
    output_tokens: int
    usd: Decimal


def build_line(
    *,
    snapshot_id: str,
    turno_id: str,
    status: str,
    decision: str,
    outcome: str,
    required: Sequence[str],
    model_calls: Sequence[ModelCallRecord],
    tool_calls: Sequence[ToolCallRecord],
    thinking: Sequence[str],
    notices_agent: Sequence[str],
    notices_template: Sequence[str],
    report_id: str | None,
    card: PriceCard,
) -> TraceLine:
    """Cost each call and total the line here; the loop knows no prices (R13)."""
    calls = [
        TraceModelCall(
            turn=c.turn,
            stop_reason=c.stop_reason,
            usage=c.usage,
            usd=cost_usd(c.usage, card),
            latency_ms=c.latency_ms,
        )
        for c in model_calls
    ]
    totals = TraceTotals(
        input_tokens=sum(c.usage.input_tokens for c in calls),
        output_tokens=sum(c.usage.output_tokens for c in calls),
        cache_read_tokens=sum(c.usage.cache_read_tokens for c in calls),
        cache_write_5m_tokens=sum(c.usage.cache_write_5m_tokens for c in calls),
        cache_write_1h_tokens=sum(c.usage.cache_write_1h_tokens for c in calls),
        usd=sum((c.usd for c in calls), Decimal(0)),
    )
    return TraceLine.model_validate(
        {
            "snapshot_id": snapshot_id,
            "turno_id": turno_id,
            "status": status,
            "decision": decision,
            "outcome": outcome,
            "required": list(required),
            "model_calls": calls,
            "tool_calls": [
                TraceToolCall(
                    turn=t.turn,
                    name=t.name,
                    arguments=dict(t.arguments),
                    is_error=t.is_error,
                    result_chars=t.result_chars,
                    error=t.error,
                    latency_ms=t.latency_ms,
                )
                for t in tool_calls
            ],
            "thinking": list(thinking),
            "notices_agent": list(notices_agent),
            "notices_template": list(notices_template),
            "report_id": report_id,
            "totals": totals,
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
    return RunTotals(
        snapshots=len(rows),
        called=sum(row.decision == "call" for row in rows),
        model_calls=sum(len(row.model_calls) for row in rows),
        input_tokens=sum(row.totals.input_tokens for row in rows),
        output_tokens=sum(row.totals.output_tokens for row in rows),
        usd=sum((row.totals.usd for row in rows), Decimal(0)),
    )
