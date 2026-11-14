"""010 T15: the coordinator step supplies the hooks' snapshot view (E12, R1, R4, R8, US-09 scenario 3)."""

from pathlib import Path

import pytest
from agent_builders import end, tool
from draft_builders import FakeSnapshotWriter, agent_text, s004_notices
from incident_runs import EV_T05, PICKUP_ANY, incident_run
from judgment_builders import incident_tool_context

from plant_monitor.agents.allowlists import COORDINATOR_TOOLS
from plant_monitor.agents.factory import build_coordinator, coordinator_hooks
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog, LoopOutcome
from plant_monitor.agents.model import Message, TextBlock, ToolResultBlock
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity, ShiftPosition
from plant_monitor.domain.models import Snapshot
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import build_server
from plant_monitor.runner.coordinator_step import CoordinatorStep, DecisionView
from plant_monitor.runner.judgment import SnapshotJudgment
from plant_monitor.runner.pipeline import SnapshotDecision

from builders import isolate_settings_env
from notice_builders import (
    PICKUP_BRAZIL_CASE,
    PICKUP_LOCAL_CASE,
    SEDAN_LOCAL_CASE,
    SUV_LOCAL_CASE,
    plant_shifts,
    series_snapshot,
)

SEL, SL, PL, PB = SEDAN_LOCAL_CASE, SUV_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE
NEWS = tuple(f"S004-informe_de_turno-{c}" for c in (SEL, PL, PB))
REMINDER = "Texts are still missing for these notice ids; write them with the write tools: "


def texts(*case_ids: str) -> dict[str, object]:
    """'emit_shift_report' arguments with the agent text of each case."""
    return {"textos": [{"case_id": c, "texto": agent_text(f"S004-informe_de_turno-{c}")} for c in case_ids]}


def results_of(model: FakeModel, request: int) -> list[ToolResultBlock]:
    """The tool results in the last message of request number 'request' (0-based)."""
    return [b for b in model.requests[request].messages[-1].content if isinstance(b, ToolResultBlock)]


def test_e12a_hooks_see_the_writers_snapshot_through_the_step(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E12a: novelty blocks a silent case, the draft refuses a short list, completeness reminds twice."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k", agent_max_turns=8)
    ctx, frames = incident_tool_context()
    server = build_server(ctx, frames, tools=COORDINATOR_TOOLS)
    model = FakeModel(
        [
            tool("emit_shift_report", texts(SEL, PL, PB, SL)),
            tool("emit_shift_report", texts(SEL, PL), "tu-2"),
            end("Listo."),
            end("Listo."),
        ]
    )
    coordinator = build_coordinator(settings, model, lambda: ToolClient(server), hooks=coordinator_hooks())
    snapshot = Snapshot.model_validate({**series_snapshot("S004"), "snapshot_id": "S004"})
    shift, _ = snapshot_position(plant_shifts(), "S004")
    decision = SnapshotDecision(snapshot, shift, ShiftPosition.CLOSING, {}, s004_notices())
    log = LoopLog()
    step = CoordinatorStep(coordinator, frames, lambda d, required: ())
    result = step.run(decision, FakeSnapshotWriter(decision), (), log)
    assert len(model.requests) == 4
    assert results_of(model, 1) == [ToolResultBlock("tu-1", f"{SL}: no news since last report", True)]
    assert results_of(model, 2) == [
        ToolResultBlock(
            "tu-2", "Error executing tool emit_shift_report: missing texto for S001-Pickup-Brasil", True
        )
    ]
    assert model.requests[3].messages[-1] == Message("user", (TextBlock(f"{REMINDER}{', '.join(NEWS)}"),))
    assert result.outcome is LoopOutcome.MISSING_TEXTS
    assert [(h.phase, h.hook, h.tool, h.turn) for h in log.hooks] == [
        ("pre_tool", "novelty", "emit_shift_report", 1),
        ("on_stop", "completeness", None, 3),
        ("on_stop", "completeness", None, 4),
    ]


def test_e12b_decision_view_reads_floors_alerts_and_news_of_a_mid_snapshot() -> None:
    """E12b: after 'decide' at S011 with AC2 linking PL and PB, the view mirrors the delta and the alerts."""
    pe = "S011-Pickup-Europa"

    def view_of(decision: SnapshotDecision) -> SnapshotDecision:
        judgment = SnapshotJudgment(run.pipeline, decision, run.ledger, 1500)
        view = DecisionView(judgment)
        assert view.floors() == {
            "S010-Pickup-Local": Severity.HIGH,
            "S010-Pickup-Brasil": Severity.HIGH,
            pe: Severity.HIGH,
        }
        assert [n.notice_id for n in view.alerts()] == [f"S011-alerta_inmediata-{pe}"]
        assert view.news() == ()
        return decision

    with incident_run() as run:
        run.through(9)
        run.step(10, lambda d: run.raise_cause(d, CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05))
        run.step(11, view_of)
