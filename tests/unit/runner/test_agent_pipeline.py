"""007 T13: 'AgentPipeline' over fake steps, a scripted model and the real tools (E15, E16, E18c)."""

import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest
from agent_builders import tool
from draft_builders import agent_text, s001_notices, s003_notices, s010_notices
from mcp.server.mcpserver import MCPServer
from mcp_builders import tool_context

from plant_monitor.agents.factory import COORDINATOR_TOOLS, build_coordinator
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import ToolPort
from plant_monitor.agents.model import ModelReply
from plant_monitor.cases.notice_builder import SnapshotNotices
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Anomaly, Combination, Shift, Snapshot, SnapshotCommit
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import FrameHolder, NoCurrentSnapshot
from plant_monitor.mcp_server.server import build_server
from plant_monitor.runner.agent_pipeline import AgentPipeline
from plant_monitor.runner.pipeline import SnapshotDecision
from plant_monitor.runner.series import RunAborted, run_series
from plant_monitor.telemetry.trace import TraceWriter, read_trace, run_totals
from plant_monitor.telemetry.usage import PriceCard

from builders import isolate_settings_env
from notice_builders import plant_shifts, series_snapshot, write_series

trace_logger = "plant_monitor.telemetry.trace"
SEL = "S001-Sedán-Local"
SEL10 = "S008-Sedán-Local"
ALERT_S003 = f"S003-alerta_inmediata-{SEL}"
ALERT_S010 = f"S010-alerta_inmediata-{SEL10}"
REQUIRED_S010 = (
    ALERT_S010,
    f"S010-informe_de_turno-{SEL10}",
    "S010-informe_de_turno-S007-Pickup-Brasil",
)


class FakeUnit:
    """'OpenUnit' that reports a fixed current snapshot id (or none)."""

    def __init__(self, current: str | None) -> None:
        self._current = current

    def current_snapshot(self) -> str | None:
        return self._current


class FakeSteps:
    """'NoticeSteps' that decides a fixed snapshot and records each 'finish' with the frame state."""

    def __init__(self, decision: SnapshotDecision, frames: FrameHolder) -> None:
        self._decision = decision
        self._frames = frames
        self.finished: list[SnapshotDecision] = []
        self.frame_open: list[bool] = []

    def decide(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> SnapshotDecision:
        return self._decision

    def finish(self, decision: SnapshotDecision) -> None:
        self.finished.append(decision)
        try:
            self._frames.current()
        except NoCurrentSnapshot:
            self.frame_open.append(False)
        else:
            self.frame_open.append(True)


class CommitFailingStore:
    """'ProcessedStore' whose unit of work raises on a clean exit, after 'process' returned (E18c)."""

    def get_hash(self, snapshot_id: str) -> str | None:
        return None

    def known_units(self) -> Mapping[str, Combination]:
        return {}

    def record_anomaly(self, anomaly: Anomaly) -> None:
        return None

    @contextmanager
    def processing(self, commit: SnapshotCommit) -> Iterator[None]:
        yield
        raise RuntimeError("commit failed")


@dataclass
class Rig:
    """The pipeline under test and the doubles it runs on."""

    pipeline: AgentPipeline
    steps: FakeSteps
    model: FakeModel
    trace: TraceWriter
    path: Path
    decision: SnapshotDecision


def decision_for(
    snapshot_id: str, notices: SnapshotNotices, source: str, position: ShiftPosition
) -> SnapshotDecision:
    """A decision for 'snapshot_id' over the series snapshot 'source' and its shift."""
    snapshot = Snapshot.model_validate({**series_snapshot(source), "snapshot_id": snapshot_id})
    shift, _ = snapshot_position(plant_shifts(), source)
    return SnapshotDecision(snapshot, shift, position, {}, notices)


def tool_factory(server: MCPServer) -> Callable[[], AbstractAsyncContextManager[ToolPort]]:
    """The tool client opener the coordinator takes, annotated once."""
    return lambda: ToolClient(server)


def price_card(settings: Settings) -> PriceCard:
    """The default prices of 'settings' as a card."""
    return PriceCard(
        input=settings.price_input_per_mtok,
        cache_write_5m=settings.price_cache_write_5m_per_mtok,
        cache_write_1h=settings.price_cache_write_1h_per_mtok,
        cache_read=settings.price_cache_read_per_mtok,
        output=settings.price_output_per_mtok,
        long_context_threshold=settings.long_context_threshold_tokens,
        long_context_multiplier=settings.long_context_multiplier,
    )


def make_rig(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: SnapshotDecision,
    script: Sequence[ModelReply | Exception],
    *,
    current: str | None,
    max_turns: int = 8,
    trace_path: Path | None = None,
) -> Rig:
    """An 'AgentPipeline' over the real tool server, a scripted model and a trace under 'tmp_path'."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k", agent_max_turns=max_turns)
    ctx, frames = tool_context()
    server = build_server(ctx, frames, tools=COORDINATOR_TOOLS)
    model = FakeModel(script)
    steps = FakeSteps(decision, frames)
    path = trace_path or tmp_path / "traces" / "trace.jsonl"
    trace = TraceWriter(path)
    pipeline = AgentPipeline(
        steps=steps,
        unit=FakeUnit(current),
        frames=frames,
        coordinator=build_coordinator(settings, model, tool_factory(server)),
        trace=trace,
        prices=price_card(settings),
        max_chars=settings.notice_text_max_chars,
    )
    return Rig(pipeline, steps, model, trace, path, decision)


def run_process(rig: Rig) -> None:
    """Call 'process' with the decision's own snapshot, shift and position."""
    d = rig.decision
    rig.pipeline.process(d.snapshot, d.shift, d.position)


def s003_decision() -> SnapshotDecision:
    """E41's S003: an alert and no report."""
    return decision_for("S003", s003_notices(), "S003", ShiftPosition.MID)


def leaves(error: BaseException) -> list[BaseException]:
    """Every non-group exception inside 'error', depth first."""
    if isinstance(error, BaseExceptionGroup):
        return [leaf for inner in error.exceptions for leaf in leaves(inner)]
    return [error]


@pytest.mark.parametrize(
    ("current", "named"),
    [pytest.param("S002", ("S003", "S002"), id="other-snapshot"), pytest.param(None, (), id="no-open-unit")],
)
def test_e15_frame_mismatch_or_no_open_unit_aborts_before_any_model_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, current: str | None, named: tuple[str, ...]
) -> None:
    """E15: ValueError naming both ids; no request, no save, nothing staged, one aborted line."""
    script = [tool("emit_alert", {"case_id": SEL, "texto": agent_text(ALERT_S003)})]
    rig = make_rig(tmp_path, monkeypatch, s003_decision(), script, current=current)
    with pytest.raises(ValueError) as info:
        run_process(rig)
    assert all(snapshot_id in str(info.value) for snapshot_id in named)
    assert (rig.model.requests, rig.model.counted, rig.steps.finished) == ([], [], [])
    rig.trace.after_commit()
    (line,) = read_trace(rig.path)
    assert (line.snapshot_id, line.status, line.outcome) == ("S003", "aborted", "aborted:ValueError")
    assert line.model_calls == []


def test_e16_turn_cap_fallback_keeps_the_agent_alert_and_the_template_news_with_one_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E16: 'fallback:turn_cap'; agent alert text, template news, one save after the frame."""
    original = s010_notices()
    decision = decision_for("S010", original, "S004", ShiftPosition.CLOSING)
    script = [
        tool("emit_alert", {"case_id": SEL10, "texto": agent_text(ALERT_S010)}),
        tool("get_deviations", {}, "tu-2"),
    ]
    rig = make_rig(tmp_path, monkeypatch, decision, script, current="S010", max_turns=2)
    run_process(rig)
    assert len(rig.model.requests) == 2
    assert len(rig.steps.finished) == 1
    assert rig.steps.frame_open == [False]
    final = rig.steps.finished[0].notices
    assert final.decisions[0].texto == agent_text(ALERT_S010)
    assert final.decisions[1:] == original.decisions[1:]
    assert final.report == original.report
    assert final.to_mark == original.to_mark
    rig.trace.after_commit()
    (line,) = read_trace(rig.path)
    assert (line.status, line.decision, line.outcome) == ("committed", "call", "fallback:turn_cap")
    assert line.required == list(REQUIRED_S010)
    assert line.notices_agent == [ALERT_S010]
    assert line.notices_template == [n.notice_id for n in original.decisions[1:]]


def test_e18c_commit_failure_after_process_leaves_no_trace_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E18c, X2: the line is only staged; a rolled-back snapshot never gets one."""
    script = [tool("emit_alert", {"case_id": SEL, "texto": agent_text(ALERT_S003)})]
    rig = make_rig(tmp_path, monkeypatch, s003_decision(), script, current="S003")
    arrivals = write_series(tmp_path / "snapshots", ("S003",))
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, plant_shifts(), CommitFailingStore(), rig.pipeline, post_commit=rig.trace)
    assert isinstance(info.value.cause, RuntimeError)
    assert len(rig.steps.finished) == 1
    assert not rig.path.exists()


def test_r1_no_required_text_saves_the_templates_without_a_model_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R1, R14: no text needed means no request, one save of the unchanged notices and a 'skip' line."""
    original = s001_notices()
    decision = decision_for("S001", original, "S001", ShiftPosition.MID)
    rig = make_rig(tmp_path, monkeypatch, decision, [], current="S001")
    run_process(rig)
    assert (rig.model.requests, rig.model.counted) == ([], [])
    assert [d.notices for d in rig.steps.finished] == [original]
    rig.trace.after_commit()
    (line,) = read_trace(rig.path)
    assert (line.status, line.decision, line.decision_reason) == ("committed", "skip", "no_text_needed")
    assert line.outcome == "skipped"
    assert line.model_calls == []
    assert line.notices_agent == []
    assert line.notices_template == [n.notice_id for n in original.decisions]
    assert line.totals.usd == Decimal(0)


def test_r14_e18_aborted_line_without_required_text_is_a_skip_not_a_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R14, E18, FR-37: a 'finish' failure on a no-text snapshot logs 'skip', so 'called' stays 0."""
    original = s001_notices()
    decision = decision_for("S001", original, "S001", ShiftPosition.MID)
    rig = make_rig(tmp_path, monkeypatch, decision, [], current="S001")

    def failing_finish(_: SnapshotDecision) -> None:
        raise RuntimeError("sink down")

    monkeypatch.setattr(rig.steps, "finish", failing_finish)
    with pytest.raises(RuntimeError):
        run_process(rig)
    (line,) = read_trace(rig.path)
    assert (line.status, line.decision, line.decision_reason) == ("aborted", "skip", "no_text_needed")
    assert run_totals([line]).called == 0


def test_e18d_unwritable_trace_on_abort_reraises_the_original_error_and_logs_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """E18 (d): 'write_now' failing on an E15 abort keeps the 'ValueError' and logs once."""
    script = [tool("emit_alert", {"case_id": SEL, "texto": agent_text(ALERT_S003)})]
    rig = make_rig(tmp_path, monkeypatch, s003_decision(), script, current="S002", trace_path=tmp_path)
    with caplog.at_level(logging.ERROR), pytest.raises(ValueError) as info:
        run_process(rig)
    assert type(info.value) is ValueError
    errors = [r for r in caplog.records if r.name == trace_logger and r.levelno == logging.ERROR]
    assert len(errors) == 1


def test_risk_a_group_with_several_errors_is_not_unwrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: unwrapping a multi-error group would hide the second failure (R12)."""
    group = ExceptionGroup("two", [RuntimeError("a"), KeyError("b")])
    rig = make_rig(tmp_path, monkeypatch, s003_decision(), [group], current="S003")
    with pytest.raises(BaseExceptionGroup) as info:
        run_process(rig)
    assert {type(leaf) for leaf in leaves(info.value)} == {RuntimeError, KeyError}
    assert rig.steps.finished == []
