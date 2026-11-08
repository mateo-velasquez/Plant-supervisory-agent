"""007 T14: E41 series through the agent pipeline, file-backed registry, trace and resume (E20, E21)."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from draft_builders import agent_text

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelCallFailed, ModelReply, ThinkingBlock, ToolUseBlock
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import Settings
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.notify.composite import CompositeNotifier
from plant_monitor.notify.file import FileNotifier
from plant_monitor.runner.agent_pipeline import build_agent_pipeline
from plant_monitor.runner.outbox import OutboxDispatcher
from plant_monitor.runner.pipeline import ThresholdPipeline
from plant_monitor.runner.post_commit import PostCommitChain
from plant_monitor.runner.series import RunAborted, RunSummary, run_series
from plant_monitor.telemetry.trace import TraceWriter, read_trace, run_totals, trace_path
from plant_monitor.telemetry.usage import Usage

from builders import held_out_policy, isolate_settings_env
from notice_builders import FIXTURE_PLANT, plant_context, plant_shifts, write_series

SERIES = ("S001", "S002", "S003", "S004")
CLOCK_TIME = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)
SECOND_START = datetime(2026, 3, 2, 23, 30, tzinfo=UTC)
USAGE = Usage(input_tokens=3000, output_tokens=200)

SEL = "S001-Sedán-Local"
SUV = "S002-SUV-Local"
PL = "S001-Pickup-Local"
PB = "S001-Pickup-Brasil"
ALERT_ID = f"S003-alerta_inmediata-{SEL}"
S002_NEWS = tuple(f"S002-informe_de_turno-{c}" for c in (SEL, SUV, PL, PB))
S004_NEWS = tuple(f"S004-informe_de_turno-{c}" for c in (SEL, PL, PB))
AGENT_IDS = {*S002_NEWS, ALERT_ID, *S004_NEWS}

type Item = Notice | ShiftReport
type Call = tuple[str, str]


class Recorder:
    """Keeps every delivered alert and report, and the '(channel, id)' order."""

    def __init__(self) -> None:
        self.alerts: list[Notice] = []
        self.reports: list[ShiftReport] = []
        self.calls: list[Call] = []

    def alert(self, notice: Notice) -> None:
        self.alerts.append(notice)
        self.calls.append(("alert", notice.notice_id))

    def report(self, report: ShiftReport) -> None:
        self.reports.append(report)
        self.calls.append(("report", report.turno_id))


@dataclass(frozen=True)
class Outcome:
    """An uninterrupted agent run: where it wrote, what it delivered and what the model saw."""

    root: Path
    path: Path
    out: Path
    trace: Path
    recorder: Recorder
    model: FakeModel
    summary: RunSummary


def call_reply(name: str, arguments: dict[str, object], tool_id: str, *thinking: ThinkingBlock) -> ModelReply:
    """A reply that calls one tool, after optional thinking; usage input 3,000 and output 200."""
    return ModelReply((*thinking, ToolUseBlock(tool_id, name, arguments)), "tool_use", USAGE)


def news_args(snapshot_id: str, case_ids: Sequence[str]) -> dict[str, object]:
    """Arguments of 'emit_shift_report' with an agent text per case."""
    return {
        "textos": [
            {"case_id": c, "texto": agent_text(f"{snapshot_id}-informe_de_turno-{c}")} for c in case_ids
        ]
    }


def s002_script() -> list[ModelReply | Exception]:
    return [
        call_reply("get_active_cases", {}, "tu-1", ThinkingBlock("Reviso los casos activos.", "sig-1")),
        call_reply("emit_shift_report", news_args("S002", (SEL, SUV, PL, PB)), "tu-2"),
    ]


def healthy_script() -> list[ModelReply | Exception]:
    """The S003 and S004 replies of E20."""
    return [
        call_reply("get_case", {"case_id": SEL}, "tu-1"),
        call_reply("emit_alert", {"case_id": SEL, "texto": agent_text(ALERT_ID)}, "tu-2"),
        call_reply("get_deviations", {}, "tu-1"),
        call_reply("emit_shift_report", news_args("S004", (SEL, PL, PB)), "tu-2"),
    ]


def run_agent(
    root: Path,
    arrivals: Sequence[Arrival],
    settings: Settings,
    model: FakeModel,
    recorder: Recorder,
    started: datetime,
) -> RunSummary:
    """Run the series on 'root' with the production wiring: file registry, trace and outbox."""
    root.mkdir(parents=True, exist_ok=True)
    out = root / "out"
    trace = TraceWriter(trace_path(root / "traces", started))
    with SqliteRegistry(root / "registry.sqlite3") as registry:
        pipeline = build_agent_pipeline(
            settings, registry, plant_context(), held_out_policy(is_open=True), model, trace
        )
        outbox = OutboxDispatcher(
            registry.notices, CompositeNotifier((FileNotifier(out), recorder)), lambda: CLOCK_TIME
        )
        return run_series(
            arrivals, plant_shifts(), registry, pipeline, post_commit=PostCommitChain([trace, outbox])
        )


def stored_rows(path: Path) -> list[tuple[str, str, str, str, str | None, str]]:
    """Every stored notice row of a closed registry file, in processing order."""
    query = "SELECT notice_id, snapshot_id, kind, tipo, case_id, payload FROM notices ORDER BY seq, idx"
    with closing(sqlite3.connect(path)) as conn:
        return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in conn.execute(query)]


def out_files(out: Path) -> dict[str, bytes]:
    """File name to bytes for everything in the output directory."""
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())} if out.exists() else {}


def items_of(path: Path, snapshot_ids: Sequence[str]) -> dict[str, tuple[Item, ...]]:
    """The stored notices and reports of each snapshot, read through a fresh registry."""
    with SqliteRegistry(path) as registry:
        return {sid: registry.notices.for_snapshot(sid) for sid in snapshot_ids}


def blank(item: Item) -> Item:
    """The item with every 'texto' emptied, so rows compare except for their text."""
    if isinstance(item, ShiftReport):
        news = tuple(n.model_copy(update={"texto": ""}) for n in item.novedades)
        return item.model_copy(update={"novedades": news})
    return item.model_copy(update={"texto": ""})


def texts_by_id(items: Sequence[Item]) -> dict[str, str]:
    """'notice_id' to 'texto' over the notices and the report news."""
    found: dict[str, str] = {}
    for item in items:
        for notice in item.novedades if isinstance(item, ShiftReport) else (item,):
            found[notice.notice_id] = notice.texto
    return found


@pytest.fixture
def arrivals(tmp_path: Path) -> list[Arrival]:
    """E41 arrivals S001-S004 written under 'tmp_path'."""
    return write_series(tmp_path / "snapshots", SERIES)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Default settings with the fixture logbooks under 'data_dir'."""
    isolate_settings_env(monkeypatch, tmp_path)
    return Settings(anthropic_api_key="k", data_dir=FIXTURE_PLANT.parent)


@pytest.fixture
def baseline(tmp_path: Path, arrivals: list[Arrival]) -> dict[str, tuple[Item, ...]]:
    """E41's threshold-only items per snapshot, the templates the agent run must keep."""
    path = tmp_path / "baseline.sqlite3"
    with SqliteRegistry(path) as registry:
        pipeline = ThresholdPipeline.from_registry(registry, plant_context())
        run_series(arrivals, plant_shifts(), registry, pipeline)
    return items_of(path, SERIES)


@pytest.fixture
def e20(tmp_path: Path, arrivals: list[Arrival], settings: Settings) -> Outcome:
    """E20: the series through the agent pipeline with the exact script."""
    root = tmp_path / "e20"
    model = FakeModel([*s002_script(), *healthy_script()])
    recorder = Recorder()
    summary = run_agent(root, arrivals, settings, model, recorder, CLOCK_TIME)
    trace = root / "traces" / "trace-20260302T230000Z.jsonl"
    return Outcome(root, root / "registry.sqlite3", root / "out", trace, recorder, model, summary)


def test_e20_series_with_the_agent_rewrites_only_the_texts_and_traces_every_snapshot(
    e20: Outcome, baseline: dict[str, tuple[Item, ...]]
) -> None:
    """E20: 6 requests, 17 rows equal to E41's except 'texto', delivered agent texts, 4 trace lines."""
    assert e20.summary.processed == SERIES
    assert (len(e20.model.requests), len(e20.model.counted)) == (6, 6)

    stored = items_of(e20.path, SERIES)
    assert sum(len(items) for items in stored.values()) == 17
    expected = texts_by_id([item for items in baseline.values() for item in items])
    for sid in SERIES:
        assert [blank(i) for i in stored[sid]] == [blank(i) for i in baseline[sid]]
    for notice_id, texto in texts_by_id([i for items in stored.values() for i in items]).items():
        want = agent_text(notice_id) if notice_id in AGENT_IDS else expected[notice_id]
        assert texto == want

    rec = e20.recorder
    assert rec.calls == [("report", "T01"), ("alert", ALERT_ID), ("report", "T02")]
    assert [n.texto for n in rec.reports[0].novedades] == [agent_text(i) for i in S002_NEWS]
    assert rec.alerts[0].texto == agent_text(ALERT_ID)
    assert [n.texto for n in rec.reports[1].novedades] == [agent_text(i) for i in S004_NEWS]

    assert sorted(p.name for p in e20.trace.parent.iterdir()) == [e20.trace.name]
    s001, s002, s003, s004 = read_trace(e20.trace)
    assert [line.snapshot_id for line in (s001, s002, s003, s004)] == list(SERIES)
    assert (s001.decision, s001.decision_reason, s001.outcome) == ("skip", "no_text_needed", "skipped")
    assert s001.notices_template == [f"S001-informe_de_turno-{c}" for c in (SEL, PL, PB)]
    assert s002.notices_agent == list(S002_NEWS)
    assert (s002.report_id, s002.thinking) == ("T01-informe", ["Reviso los casos activos."])
    assert (s003.status, s003.decision, s003.decision_reason, s003.outcome) == (
        "committed",
        "call",
        "text_needed",
        "done",
    )
    assert s003.required == [ALERT_ID]
    assert [(c.turn, c.usd) for c in s003.model_calls] == [(1, Decimal("0.0004")), (2, Decimal("0.0004"))]
    assert [(t.name, t.is_error) for t in s003.tool_calls] == [("get_case", False), ("emit_alert", False)]
    assert s003.tool_calls[0].arguments == {"case_id": SEL}
    assert all(t.result_chars > 0 for t in s003.tool_calls)
    assert s003.notices_agent == [ALERT_ID]
    assert s003.notices_template == [
        f"S003-sin_aviso-{SUV}",
        f"S003-informe_de_turno-{PL}",
        f"S003-informe_de_turno-{PB}",
    ]
    assert (s003.report_id, s003.totals.usd, s003.hooks) == (None, Decimal("0.0008"), [])
    assert s004.notices_agent == list(S004_NEWS)
    assert s004.notices_template == [f"S004-sin_aviso-{SUV}"]
    assert s004.report_id == "T02-informe"
    totals = run_totals(read_trace(e20.trace))
    assert (totals.snapshots, totals.called, totals.model_calls) == (4, 3, 6)
    assert (totals.input_tokens, totals.output_tokens, totals.usd) == (18_000, 1_200, Decimal("0.0024"))


def test_e21_model_outage_aborts_at_the_snapshot_and_a_second_run_resumes_to_the_same_result(
    tmp_path: Path, arrivals: list[Arrival], settings: Settings, e20: Outcome
) -> None:
    """E21: 'RunAborted.cause' is the 'ModelCallFailed' itself; resume gives E20's rows and files."""
    root = tmp_path / "e21"
    first = Recorder()
    outage: list[ModelReply | Exception] = [*s002_script(), ModelCallFailed("create", 529)]
    with pytest.raises(RunAborted) as info:
        run_agent(root, arrivals, settings, FakeModel(outage), first, CLOCK_TIME)
    aborted = info.value
    assert aborted.snapshot_id == "S003"
    assert type(aborted.cause) is ModelCallFailed
    assert aborted.summary.processed == ("S001", "S002")
    rows = stored_rows(root / "registry.sqlite3")
    assert {r[1] for r in rows} == {"S001", "S002"}
    assert first.calls == [("report", "T01")]
    lines = read_trace(root / "traces" / "trace-20260302T230000Z.jsonl")
    assert [(ln.snapshot_id, ln.status, ln.outcome) for ln in lines] == [
        ("S001", "committed", "skipped"),
        ("S002", "committed", "done"),
        ("S003", "aborted", "aborted:ModelCallFailed"),
    ]
    assert (lines[2].notices_agent, lines[2].notices_template) == ([], [])

    second = Recorder()
    model = FakeModel(healthy_script())
    summary = run_agent(root, arrivals, settings, model, second, SECOND_START)
    assert (summary.processed, summary.skipped) == (("S003", "S004"), ("S001", "S002"))
    assert len(model.requests) == 4
    assert second.calls == [("alert", ALERT_ID), ("report", "T02")]
    assert [ln.snapshot_id for ln in read_trace(root / "traces" / "trace-20260302T233000Z.jsonl")] == [
        "S003",
        "S004",
    ]
    assert stored_rows(root / "registry.sqlite3") == stored_rows(e20.path)
    assert out_files(root / "out") == out_files(e20.out)
