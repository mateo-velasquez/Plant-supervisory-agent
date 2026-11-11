import json
import logging
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from agent_builders import RAISE5, validated

from plant_monitor.telemetry.trace import (
    InvestigatorRecord,
    ModelCallRecord,
    ToolCallRecord,
    TraceLine,
    TraceWriter,
    abort_outcome,
    build_line,
    read_trace,
    run_totals,
    trace_path,
)
from plant_monitor.telemetry.usage import PriceCard, Usage

CARD = PriceCard(
    input=Decimal("0.10"),
    cache_write_5m=Decimal("0.125"),
    cache_write_1h=Decimal("0.20"),
    cache_read=Decimal("0.01"),
    output=Decimal("0.50"),
    long_context_threshold=100_000,
    long_context_multiplier=Decimal(5),
)
ALERT_ID = "S003-alerta_inmediata-S001-Sedán-Local"


def _call(turn: int) -> ModelCallRecord:
    usage = Usage(input_tokens=3_000, output_tokens=200)
    return ModelCallRecord(turn=turn, stop_reason="tool_use", usage=usage, latency_ms=100)


def _line(
    snapshot_id: str = "S003",
    *,
    status: str = "committed",
    outcome: str = "done",
    calls: int = 2,
    decision: str = "call",
    decision_reason: str | None = "text_needed",
    agents_run: tuple[str, ...] = (),
    investigator: InvestigatorRecord | None = None,
) -> TraceLine:
    tools = [
        ToolCallRecord(
            turn=1,
            name="get_case",
            arguments={"case_id": "S001-Sedán-Local"},
            is_error=False,
            result_chars=120,
            error=None,
            latency_ms=5,
        )
    ]
    return build_line(
        snapshot_id=snapshot_id,
        turno_id="T01",
        status=status,
        decision=decision,
        decision_reason=decision_reason,
        outcome=outcome,
        required=[ALERT_ID],
        model_calls=[_call(n) for n in range(1, calls + 1)],
        tool_calls=tools,
        thinking=["Reviso los casos activos."],
        notices_agent=[ALERT_ID],
        notices_template=[],
        report_id=None,
        card=CARD,
        agents_run=agents_run,
        investigator=investigator,
        proposals_applied=["S010-p1"] if investigator and investigator.proposals else [],
        proposals_declined=[],
    )


def _investigator(calls: int = 2) -> InvestigatorRecord:
    return InvestigatorRecord(
        outcome="done",
        logbooks=["T05"],
        missing=[],
        marks={"T05": "revisada"},
        proposals=[validated("S010-p1", RAISE5).item()],
        control_errors=[],
        model_calls=[_call(n) for n in range(1, calls + 1)],
        tool_calls=[],
        thinking=[],
    )


def test_e18a_build_line_costs_each_call_and_totals() -> None:
    """E18a: each call costs 0.0004 when the line is built; totals.usd is 0.0008."""
    line = _line()
    assert [float(c.usd) for c in line.model_calls] == [pytest.approx(0.0004)] * 2
    assert float(line.totals.usd) == pytest.approx(0.0008)
    assert (line.status, line.decision, line.decision_reason) == ("committed", "call", "text_needed")
    assert (line.outcome, line.report_id, line.hooks) == ("done", None, [])


@pytest.mark.parametrize(
    ("decision", "reason"),
    [
        pytest.param("call", "text_needed", id="text_needed"),
        pytest.param("call", "closing_review", id="closing_review"),
        pytest.param("call", "proposals", id="proposals"),
        pytest.param("call", "investigator_only", id="investigator_only"),
        pytest.param("skip", "no_text_needed", id="no_text_needed"),
        pytest.param("skip", None, id="none"),
    ],
)
def test_r14_build_line_stores_each_decision_reason_and_none(decision: str, reason: str | None) -> None:
    """R14: 'decision_reason' is a stored field, so it survives a write and read, 'None' included."""
    line = _line(decision=decision, decision_reason=reason)
    assert line.decision_reason == reason
    assert TraceLine.model_validate_json(line.model_dump_json()).decision_reason == reason


def test_r14_a_007_trace_line_still_parses() -> None:
    """R14: a line written by 007, with its serialized computed reason, reads back."""
    old: dict[str, object] = {
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
        "hooks": [],
    }
    line = TraceLine.model_validate_json(json.dumps(old))
    assert (line.decision, line.decision_reason) == ("skip", "no_text_needed")


def test_trace_path_is_named_after_the_utc_start(tmp_path: Path) -> None:
    """R14: 'trace-<UTC %Y%m%dT%H%M%SZ>.jsonl' in the traces directory."""
    started = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)
    assert trace_path(tmp_path, started) == tmp_path / "trace-20260302T230000Z.jsonl"


def test_abort_outcome_formats_the_error_class() -> None:
    """R14: the trace layer formats 'aborted:<ErrorClass>'."""
    assert abort_outcome(ValueError("S003 vs S002")) == "aborted:ValueError"


def test_trace_writer_stages_until_after_commit(tmp_path: Path) -> None:
    """R14: nothing on disk until 'after_commit'; it appends once, then clears the stage."""
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.stage(_line("S002"))
    assert not path.exists()
    writer.after_commit()
    writer.after_commit()
    assert [entry.snapshot_id for entry in read_trace(path)] == ["S002"]


def test_e18e_after_commit_with_nothing_staged_is_a_noop(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """E18e: no file is created and nothing is logged."""
    path = tmp_path / "trace.jsonl"
    with caplog.at_level(logging.DEBUG):
        TraceWriter(path).after_commit()
    assert not path.exists()
    assert caplog.records == []


def test_write_now_appends_immediately_as_utf8_lf_json_lines(tmp_path: Path) -> None:
    """R14: 'write_now' appends at once; UTF-8, LF, one JSON object per line."""
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.write_now(_line("S003", status="aborted", outcome="aborted:ModelCallFailed"))
    writer.write_now(_line("S004"))
    raw = path.read_bytes()
    assert b"\r" not in raw
    rows = [json.loads(row) for row in raw.decode("utf-8").split("\n") if row]
    assert [row["snapshot_id"] for row in rows] == ["S003", "S004"]
    assert rows[0]["required"] == [ALERT_ID]


@pytest.mark.parametrize("via", ["after_commit", "write_now"])
def test_e18d_oserror_is_logged_by_the_writer_and_never_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, via: str
) -> None:
    """E18d: an unwritable target logs one ERROR and raises nothing."""
    writer = TraceWriter(tmp_path)  # a directory cannot be opened for append
    with caplog.at_level(logging.ERROR):
        if via == "write_now":
            writer.write_now(_line())
        else:
            writer.stage(_line())
            writer.after_commit()
    assert [r.levelno for r in caplog.records] == [logging.ERROR]


def test_e20_run_totals_sum_every_line_including_aborted(tmp_path: Path) -> None:
    """E20 / R13: read_trace round trips and run_totals counts aborted lines too."""
    path = tmp_path / "trace.jsonl"
    writer = TraceWriter(path)
    writer.write_now(_line("S001", calls=0, outcome="skipped").model_copy(update={"decision": "skip"}))
    writer.write_now(_line("S002"))
    writer.write_now(_line("S003", status="aborted", outcome="aborted:ModelCallFailed", calls=1))
    totals = run_totals(read_trace(path))
    assert (totals.snapshots, totals.called, totals.model_calls) == (3, 2, 3)
    assert (totals.input_tokens, totals.output_tokens) == (9_000, 600)
    assert float(totals.usd) == pytest.approx(0.0012)


def test_e17a_a_line_with_an_investigator_costs_both_agents_and_round_trips() -> None:
    """E17a: investigator totals 6000 / 400 / 0.0008; the line totals add the coordinator's call."""
    line = _line(calls=1, agents_run=("investigator", "coordinator"), investigator=_investigator())
    assert line.investigator is not None
    assert (line.investigator.totals.input_tokens, line.investigator.totals.output_tokens) == (6_000, 400)
    assert float(line.investigator.totals.usd) == pytest.approx(0.0008)
    assert (line.totals.input_tokens, line.totals.output_tokens) == (9_000, 600)
    assert float(line.totals.usd) == pytest.approx(0.0012)
    assert line.agents_run == ["investigator", "coordinator"]
    assert (line.investigator.outcome, line.investigator.logbooks, line.investigator.marks) == (
        "done",
        ["T05"],
        {"T05": "revisada"},
    )
    assert line.investigator.proposals[0]["id"] == "S010-p1"
    assert (line.proposals_applied, line.proposals_declined) == (["S010-p1"], [])
    assert TraceLine.model_validate_json(line.model_dump_json()) == line


@pytest.mark.parametrize(
    ("decision", "ran"),
    [pytest.param("call", ["coordinator"], id="call"), pytest.param("skip", [], id="skip")],
)
def test_e17b_a_008_line_without_the_new_keys_parses(decision: str, ran: list[str]) -> None:
    """E17b: no 'investigator', empty proposal lists, and 'agents_run' read from the decision."""
    old: dict[str, object] = {
        "snapshot_id": "S001",
        "turno_id": "T01",
        "status": "committed",
        "decision": decision,
        "decision_reason": "text_needed" if decision == "call" else "no_text_needed",
        "outcome": "done" if decision == "call" else "skipped",
        "required": [],
        "model_calls": [],
        "tool_calls": [],
        "thinking": [],
        "notices_agent": [],
        "notices_template": [],
        "report_id": None,
        "totals": {"input_tokens": 0, "output_tokens": 0, "usd": 0.0},
        "hooks": [],
    }
    line = TraceLine.model_validate_json(json.dumps(old))
    assert line.investigator is None
    assert (line.proposals_applied, line.proposals_declined) == ([], [])
    assert list(line.ran) == ran


def test_r14_the_investigator_entry_keeps_its_trigger_and_an_older_line_reads_as_review() -> None:
    """R14, R2b: 'trigger' round trips; an entry written without it reads as 'review'."""
    lookup = replace(_investigator(), trigger="cause_lookup", logbooks=[], marks={})
    line = _line(agents_run=("investigator",), investigator=lookup)
    assert line.investigator is not None
    assert line.investigator.trigger == "cause_lookup"
    assert TraceLine.model_validate_json(line.model_dump_json()) == line
    old = _line(agents_run=("investigator",), investigator=_investigator()).model_dump(mode="json")
    del old["investigator"]["trigger"]
    parsed = TraceLine.model_validate_json(json.dumps(old))
    assert parsed.investigator is not None
    assert parsed.investigator.trigger == "review"


def test_e17c_run_totals_split_the_cost_by_agent() -> None:
    """E17c: totals sum both agents; 'by_agent' counts runs from 'agents_run'."""
    both = _line("S001", calls=1, agents_run=("investigator", "coordinator"), investigator=_investigator())
    skipped = _line("S002", calls=0, outcome="skipped", decision="skip", decision_reason="no_text_needed")
    only_inv = _line(
        "S003",
        calls=0,
        outcome="skipped",
        decision_reason="investigator_only",
        agents_run=("investigator",),
        investigator=_investigator(),
    )
    totals = run_totals([both, skipped, only_inv])
    assert (totals.snapshots, totals.called, totals.model_calls) == (3, 2, 5)
    assert (totals.input_tokens, totals.output_tokens) == (15_000, 1_000)
    assert float(totals.usd) == pytest.approx(0.002)
    coordinator, investigator = totals.by_agent["coordinator"], totals.by_agent["investigator"]
    assert (coordinator.runs, coordinator.model_calls) == (1, 1)
    assert (coordinator.input_tokens, coordinator.output_tokens) == (3_000, 200)
    assert float(coordinator.usd) == pytest.approx(0.0004)
    assert (investigator.runs, investigator.model_calls) == (2, 4)
    assert (investigator.input_tokens, investigator.output_tokens) == (12_000, 800)
    assert float(investigator.usd) == pytest.approx(0.0016)
