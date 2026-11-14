"""010 T7: hook records in the trace line (R10, E16)."""

import json
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from plant_monitor.telemetry.trace import (
    HookRecord,
    TraceHook,
    TraceLine,
    TraceWriter,
    build_line,
    read_trace,
)
from plant_monitor.telemetry.usage import PriceCard

CARD = PriceCard(
    input=Decimal("0.10"),
    cache_write_5m=Decimal("0.125"),
    cache_write_1h=Decimal("0.20"),
    cache_read=Decimal("0.01"),
    output=Decimal("0.50"),
    long_context_threshold=100_000,
    long_context_multiplier=Decimal(5),
)
REASON_A = "tool emit_alert is not allowed for the investigator"
REASON_B = "Texts are still missing for these notice ids; write them with the write tools: S010-x"
H1 = HookRecord("investigator", "pre_tool", "allowlist", "emit_alert", 1, REASON_A)
H2 = HookRecord("coordinator", "on_stop", "completeness", None, 2, REASON_B)


def _line(hooks: list[HookRecord]) -> TraceLine:
    return build_line(
        snapshot_id="S010",
        turno_id="T05",
        status="committed",
        decision="call",
        decision_reason="text_needed",
        outcome="done",
        required=[],
        model_calls=[],
        tool_calls=[],
        thinking=[],
        notices_agent=[],
        notices_template=[],
        report_id=None,
        card=CARD,
        hooks=hooks,
    )


def _old_line() -> dict[str, object]:
    return {
        "snapshot_id": "S001",
        "turno_id": "T01",
        "status": "committed",
        "decision": "skip",
        "decision_reason": "no_text_needed",
        "outcome": "skipped",
        "required": [],
        "model_calls": [],
        "tool_calls": [],
        "thinking": [],
        "notices_agent": [],
        "notices_template": [],
        "report_id": None,
        "totals": {"input_tokens": 0, "output_tokens": 0, "usd": 0.0},
    }


def test_e16a_hook_records_serialize_and_round_trip_through_the_writer(tmp_path: Path) -> None:
    """010 E16a: records dump as the R10 objects and survive 'write_now' + 'read_trace'."""
    line = _line([H1, H2])
    assert line.model_dump(mode="json")["hooks"] == [
        {
            "agent": "investigator",
            "phase": "pre_tool",
            "hook": "allowlist",
            "tool": "emit_alert",
            "turn": 1,
            "reason": REASON_A,
        },
        {
            "agent": "coordinator",
            "phase": "on_stop",
            "hook": "completeness",
            "tool": None,
            "turn": 2,
            "reason": REASON_B,
        },
    ]
    assert all(isinstance(hook, TraceHook) for hook in line.hooks)
    assert (line.totals.input_tokens, line.totals.output_tokens) == (0, 0)
    path = tmp_path / "trace.jsonl"
    TraceWriter(path).write_now(line)
    assert list(read_trace(path)) == [line]


@pytest.mark.parametrize("with_key", [True, False])
def test_e16b_a_009_line_with_or_without_the_hooks_key_reads_as_empty(with_key: bool) -> None:
    """010 E16b: 'hooks' [] and a missing key both parse to []."""
    raw = _old_line()
    if with_key:
        raw["hooks"] = []
    assert TraceLine.model_validate_json(json.dumps(raw)).hooks == []


def test_e16c_a_post_tool_phase_is_rejected() -> None:
    """010 E16c: post-tool never blocks, so 'post_tool' is not a valid phase."""
    raw = _old_line()
    raw["hooks"] = [
        {"agent": "coordinator", "phase": "post_tool", "hook": "floor", "tool": "x", "turn": 1, "reason": "r"}
    ]
    with pytest.raises(ValidationError):
        TraceLine.model_validate_json(json.dumps(raw))
