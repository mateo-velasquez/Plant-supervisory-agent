"""010 T2: hook seams in the coordinator loop (R1, R9; E2, E3, E4, E5b, E14)."""

import pytest
from agent_builders import (
    ALERT_ID,
    OFFERED,
    FakeProgress,
    FakeTools,
    end,
    make_coordinator,
    tool,
)
from hook_builders import FakeView

from plant_monitor.agents.brief import render_reminder
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog, LoopOutcome
from plant_monitor.agents.model import Message, TextBlock, ToolResultBlock
from plant_monitor.hooks.chain import FloorViolation, HookChain, HookContext, ToolCall
from plant_monitor.mcp_server.types import ToolOutcome
from plant_monitor.telemetry.trace import HookRecord

pytestmark = pytest.mark.anyio

ALERT_ARGS = {"case_id": "S001-Sedán-Local", "texto": "Alerta."}


class FakePre:
    """A pre hook named 'fake' that blocks 'emit_alert' with a reason and records the contexts it saw."""

    name = "fake"

    def __init__(self, reason: str = "blocked: x") -> None:
        self.reason = reason
        self.contexts: list[HookContext] = []

    def check(self, call: ToolCall, ctx: HookContext) -> str | None:
        """Record the context; block 'emit_alert'."""
        self.contexts.append(ctx)
        return self.reason if call.name == "emit_alert" else None


class FakeStop:
    """A stop hook named 'fake' that blocks with 'note' or always passes."""

    name = "fake"

    def __init__(self, note: str | None) -> None:
        self.note = note

    def check(self, text: str, ctx: HookContext) -> str | None:
        """The configured note."""
        return self.note


class RaisingPost:
    """A post hook that raises 'FloorViolation'."""

    name = "boom"

    def verify(self, call: ToolCall, outcome: ToolOutcome, ctx: HookContext) -> None:
        """Always raise."""
        raise FloorViolation("boom")


async def test_e2_pre_block_skips_the_port_and_is_recorded() -> None:
    """E2: a blocked call never reaches the port; the reason is the error result and a hook record."""
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress)
    model = FakeModel([tool("emit_alert", ALERT_ARGS), end("Listo."), end("Listo.")])
    log = LoopLog()
    hooks = HookChain(pre=[FakePre()])
    outcome = await make_coordinator(model, tools, allowed=OFFERED, hooks=hooks).run(
        "S003", "brief", progress, log
    )
    assert tools.calls == []
    assert model.requests[1].messages[-1] == Message("user", (ToolResultBlock("tu-1", "blocked: x", True),))
    assert (log.tool_calls[0].is_error, log.tool_calls[0].error) == (True, "blocked: x")
    assert log.hooks == [HookRecord("coordinator", "pre_tool", "fake", "emit_alert", 1, "blocked: x")]
    assert outcome is LoopOutcome.MISSING_TEXTS


@pytest.mark.parametrize(
    ("note", "pending", "last_note", "records"),
    [
        pytest.param("note", (), "note", 2, id="a-stop-hook-blocks"),
        pytest.param(None, (ALERT_ID,), render_reminder([ALERT_ID]), 0, id="b-hook-passes-default-review"),
    ],
)
async def test_e3_on_stop_hook_note_or_default_review(
    note: str | None, pending: tuple[str, ...], last_note: str, records: int
) -> None:
    """E3: a blocking stop hook's reason is the note; a passing one leaves the default review's."""
    progress = FakeProgress(*pending)
    model = FakeModel([end("a"), end("b")])
    log = LoopLog()
    hooks = HookChain(stop=[FakeStop(note)])
    outcome = await make_coordinator(model, FakeTools(progress), hooks=hooks).run(
        "S003", "brief", progress, log
    )
    assert len(model.requests) == 2
    assert model.requests[1].messages[-1] == Message("user", (TextBlock(last_note),))
    assert outcome is LoopOutcome.MISSING_TEXTS
    assert log.hooks == [
        HookRecord("coordinator", "on_stop", "fake", None, turn, "note") for turn in range(1, records + 1)
    ]


async def test_e4_post_hook_exception_propagates_after_the_call_is_logged() -> None:
    """E4: a raising post hook leaves 'run' with the exception; the call ran and is in the log."""
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress)
    args = {"propuesta": "S010-p1"}
    model = FakeModel([tool("apply_proposal", args)])
    log = LoopLog()
    hooks = HookChain(post=[RaisingPost()])
    with pytest.raises(FloorViolation, match="boom"):
        await make_coordinator(model, tools, hooks=hooks).run("S010", "brief", progress, log)
    assert tools.calls == [("apply_proposal", args)]
    assert [c.name for c in log.tool_calls] == ["apply_proposal"]
    assert log.outcome is None


async def test_e14_blocks_repeated_to_the_turn_cap_end_in_turn_cap() -> None:
    """E14: a blocked call costs its turn; the cap ends the loop and every block is recorded."""
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress)
    model = FakeModel([tool("emit_alert", ALERT_ARGS)] * 3)
    log = LoopLog()
    hooks = HookChain(pre=[FakePre()])
    outcome = await make_coordinator(model, tools, max_turns=3, hooks=hooks).run(
        "S003", "brief", progress, log
    )
    assert outcome is LoopOutcome.TURN_CAP
    assert tools.calls == []
    assert [c.is_error for c in log.tool_calls] == [True] * 3
    assert [h.turn for h in log.hooks] == [1, 2, 3]


async def test_risk_hooks_see_the_agent_turn_and_the_view_given_to_run() -> None:
    """Risk (R1, I1): a loop dropping 'view' or 'agent' makes view-based hooks raise or misattribute."""
    progress = FakeProgress()
    view = FakeView()
    spy = FakePre("unused")
    model = FakeModel([tool("get_deviations", {}), end("Listo.")])
    coordinator = make_coordinator(
        model, FakeTools(progress), hooks=HookChain(pre=[spy]), agent="investigator"
    )
    await coordinator.run("S010", "brief", progress, LoopLog(), view=view)
    assert spy.contexts == [HookContext("investigator", 1, view)]


async def test_risk_allowlist_hook_runs_before_every_extra_pre_hook() -> None:
    """Risk (R1, R3): an extra hook running first would see (or answer for) tools outside the agent's list."""
    progress = FakeProgress()
    tools = FakeTools(progress)
    spy = FakePre()
    model = FakeModel([tool("delete_case", {}), end("Listo.")])
    log = LoopLog()
    await make_coordinator(model, tools, hooks=HookChain(pre=[spy])).run("S010", "brief", progress, log)
    assert spy.contexts == []
    assert tools.calls == []
    assert [h.hook for h in log.hooks] == ["allowlist"]
