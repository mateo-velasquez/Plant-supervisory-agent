"""007 T3-T6: coordinator loop stop rules, tool execution, history and budget (R3-R6, E3-E9, X1)."""

import logging
import re

import pytest
from agent_builders import ALERT_ID, USAGE, FakeProgress, FakeTools, end, make_coordinator, stopped, tool

from plant_monitor.agents.brief import render_reminder
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog, LoopOutcome
from plant_monitor.agents.model import (
    Message,
    ModelReply,
    RedactedThinkingBlock,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from plant_monitor.mcp_server.types import ToolOutcome

pytestmark = pytest.mark.anyio

ALERT_ARGS = {"case_id": "S001-Sedán-Local", "texto": "Alerta."}


async def test_e3_done_right_after_the_batch_that_fills_the_last_text() -> None:
    """E3: two requests, no closing request once nothing is missing."""
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress)
    model = FakeModel([tool("get_deviations", {}), tool("emit_alert", ALERT_ARGS, "tu-2")])
    log = LoopLog()
    outcome = await make_coordinator(model, tools).run("S003", "brief", progress, log)
    assert outcome is LoopOutcome.DONE
    assert log.outcome is LoopOutcome.DONE
    assert len(model.requests) == 2
    assert len(model.counted) == 2
    assert len(log.model_calls) == 2
    assert tools.names == ["get_deviations", "emit_alert"]


async def test_e18d_a_judgment_write_that_adds_a_text_keeps_the_loop_going_until_it_is_written() -> None:
    """E18d: required and missing gain an alert after 'raise_severity'; two requests, no third."""
    progress = FakeProgress(creates=(ALERT_ID,))
    tools = FakeTools(progress)
    raise_args = {"categoria": "parada_de_linea", "etapa": "montaje", "modelo": "Pickup"}
    model = FakeModel([tool("raise_severity", raise_args), tool("emit_alert", ALERT_ARGS, "tu-2")])
    outcome = await make_coordinator(model, tools).run("S010", "brief", progress, LoopLog())
    assert outcome is LoopOutcome.DONE
    assert len(model.requests) == 2
    assert tools.names == ["raise_severity", "emit_alert"]


async def test_r14_nothing_required_runs_until_end_turn_without_a_reminder() -> None:
    """R14, E18a: a tool turn with no required text does not stop the loop; 'end_turn' is 'done'."""
    progress = FakeProgress()
    model = FakeModel([tool("get_logbook", {"turno_id": "T01"}), end("Sin causas.")])
    outcome = await make_coordinator(model, FakeTools(progress)).run("S004", "brief", progress, LoopLog())
    assert outcome is LoopOutcome.DONE
    assert len(model.requests) == 2


async def test_e7_turn_cap_ends_with_fallback() -> None:
    """E7: a script that never finishes stops at 'max_turns' requests."""
    progress = FakeProgress(ALERT_ID)
    model = FakeModel([tool("get_deviations", {})] * 3)
    outcome = await make_coordinator(model, FakeTools(progress), max_turns=3).run(
        "S003", "brief", progress, LoopLog()
    )
    assert outcome is LoopOutcome.TURN_CAP
    assert outcome.value == "fallback:turn_cap"
    assert len(model.requests) == 3


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        pytest.param("refusal", "fallback:refusal", id="a"),
        pytest.param("max_tokens", "fallback:max_tokens", id="b"),
        pytest.param("pause_turn", "fallback:unexpected_stop", id="c"),
    ],
)
async def test_e9_stop_reasons_map_to_fallbacks(reason: str, expected: str) -> None:
    """E9: one request, then the fallback named by the stop reason."""
    progress = FakeProgress(ALERT_ID)
    model = FakeModel([stopped(reason)])
    outcome = await make_coordinator(model, FakeTools(progress)).run("S003", "brief", progress, LoopLog())
    assert outcome == expected
    assert len(model.requests) == 1


async def test_x1_tool_use_blocks_with_end_turn_are_not_run() -> None:
    """X1: a reply with 'tool_use' blocks but stop reason 'end_turn' is handled as 'end_turn'."""
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress)
    reply = ModelReply((ToolUseBlock("tu-1", "emit_alert", ALERT_ARGS),), "end_turn", USAGE)
    model = FakeModel([reply, end("Listo.")])
    outcome = await make_coordinator(model, tools).run("S003", "brief", progress, LoopLog())
    assert tools.calls == []
    assert outcome is LoopOutcome.MISSING_TEXTS


async def test_e4_error_results_pass_unchanged_and_unoffered_tools_never_run() -> None:
    """E4: an 'is_error' result goes back as is; a non-offered tool name is refused by the loop."""
    progress = FakeProgress(ALERT_ID)
    unknown = ToolOutcome("unknown case S999-SUV-Local", True)
    tools = FakeTools(progress, {"get_case": unknown})
    model = FakeModel(
        [
            tool("get_case", {"case_id": "S999-SUV-Local"}, "tu-1"),
            tool("delete_case", {}, "tu-2"),
            tool("emit_alert", ALERT_ARGS, "tu-3"),
        ]
    )
    outcome = await make_coordinator(model, tools).run("S003", "brief", progress, LoopLog())
    assert model.requests[1].messages[-1] == Message(
        "user", (ToolResultBlock("tu-1", "unknown case S999-SUV-Local", True),)
    )
    assert model.requests[2].messages[-1] == Message(
        "user", (ToolResultBlock("tu-2", "tool delete_case is not available", True),)
    )
    assert tools.names == ["get_case", "emit_alert"]
    assert outcome is LoopOutcome.DONE


async def test_e5_thinking_blocks_pass_back_byte_identical_and_history_is_append_only() -> None:
    """E5: replies are appended unchanged; 'system' and 'tools' never change; thinking is logged."""
    progress = FakeProgress(ALERT_ID)
    first = ModelReply(
        (
            ThinkingBlock("Busco desvíos.", "sig-1"),
            RedactedThinkingBlock("opaque-1"),
            ToolUseBlock("tu-1", "get_deviations", {}),
        ),
        "tool_use",
        USAGE,
    )
    model = FakeModel([first, tool("emit_alert", ALERT_ARGS, "tu-2")])
    log = LoopLog()
    await make_coordinator(model, FakeTools(progress), system="PROMPT").run("S003", "brief", progress, log)
    one, two = model.requests
    assert two.messages == (
        *one.messages,
        Message("assistant", first.content),
        Message("user", (ToolResultBlock("tu-1", "ok", False),)),
    )
    replayed = two.messages[1].content
    assert replayed[0] == ThinkingBlock("Busco desvíos.", "sig-1")
    assert replayed[1] == RedactedThinkingBlock("opaque-1")
    assert (two.system, two.tools) == (one.system, one.tools)
    assert two.system == "PROMPT"
    assert log.thinking == ["Busco desvíos."]


@pytest.mark.parametrize(
    ("script", "expected", "requests"),
    [
        pytest.param([end("Listo."), tool("emit_alert", ALERT_ARGS, "tu-2")], "done", 2, id="a"),
        pytest.param([end("Listo."), end("Listo.")], "fallback:missing_texts", 2, id="b"),
    ],
)
async def test_e8_one_reminder_turn_then_missing_texts(
    script: list[ModelReply], expected: str, requests: int
) -> None:
    """E8: the first 'end_turn' with texts missing gets one reminder; the second ends the loop."""
    progress = FakeProgress(ALERT_ID)
    model = FakeModel(script)
    outcome = await make_coordinator(model, FakeTools(progress)).run("S003", "brief", progress, LoopLog())
    one, two = model.requests[:2]
    reminder = two.messages[-1]
    assert two.messages == (*one.messages, Message("assistant", script[0].content), reminder)
    assert reminder.role == "user"
    assert reminder.content == (TextBlock(render_reminder([ALERT_ID])),)
    assert ALERT_ID in render_reminder([ALERT_ID])
    assert outcome == expected
    assert len(model.requests) == requests


@pytest.mark.parametrize(
    ("counts", "script", "expected", "sent", "warned_turn"),
    [
        pytest.param((95_001,), [], "fallback:budget_exceeded", 0, 1, id="a"),
        pytest.param((95_000,), [tool("emit_alert", ALERT_ARGS)], "done", 1, None, id="b"),
        pytest.param((3_000, 95_001), [tool("get_deviations", {})], "fallback:budget_exceeded", 1, 2, id="c"),
    ],
)
async def test_e6_budget_guard_sends_at_the_limit_and_not_above(
    caplog: pytest.LogCaptureFixture,
    counts: tuple[int, ...],
    script: list[ModelReply],
    expected: str,
    sent: int,
    warned_turn: int | None,
) -> None:
    """E6: above 'prompt_token_limit' nothing is sent and one WARNING names snapshot, turn, count, limit."""
    caplog.set_level(logging.WARNING)
    progress = FakeProgress(ALERT_ID)
    model = FakeModel(script, count=lambda request: counts[min(len(request.messages) // 2, len(counts) - 1)])
    log = LoopLog()
    outcome = await make_coordinator(model, FakeTools(progress), limit=95_000).run(
        "S003", "brief", progress, log
    )
    assert outcome == expected
    assert len(model.requests) == sent
    assert len(log.model_calls) == sent
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    if warned_turn is None:
        assert warnings == []
        return
    assert len(warnings) == 1
    assert "S003" in warnings[0]
    assert re.search(rf"turn\D*{warned_turn}\b", warnings[0])
    assert str(counts[-1]) in warnings[0]
    assert "95000" in warnings[0]


class FakeReview:
    """An 'EndReview' that answers 'note' to the first 'rejects' texts and accepts the rest."""

    def __init__(self, rejects: int, note: str = "N1") -> None:
        self.rejects = rejects
        self.note = note
        self.texts: list[str] = []

    @property
    def exhausted(self) -> LoopOutcome:
        """The outcome after a second note."""
        return LoopOutcome.INVALID_OUTPUT

    def review(self, text: str) -> str | None:
        """Record the text; return the note while rejecting."""
        self.texts.append(text)
        return self.note if len(self.texts) <= self.rejects else None


@pytest.mark.parametrize(
    ("script", "rejects", "expected", "texts", "noted"),
    [
        pytest.param([end("x"), end("y")], 1, "done", ["x", "y"], True, id="a-note-then-accept"),
        pytest.param(
            [end("x"), end("y")], 2, "fallback:invalid_output", ["x", "y"], True, id="b-rejects-every-text"
        ),
        pytest.param(
            [tool("get_logbook", {"turno_id": "T05"}), end("z")], 0, "done", ["z"], False, id="c-accepts"
        ),
    ],
)
async def test_e5_end_of_turn_goes_through_the_review(
    script: list[ModelReply], rejects: int, expected: str, texts: list[str], noted: bool
) -> None:
    """E5: a note is appended once as a user turn; a second one ends with the review's outcome."""
    progress = FakeProgress()
    model = FakeModel(script)
    review = FakeReview(rejects)
    outcome = await make_coordinator(model, FakeTools(progress)).run(
        "S010", "task", progress, LoopLog(), review
    )
    one, two = model.requests
    assert outcome == expected
    assert review.texts == texts
    if noted:
        assert two.messages == (
            *one.messages,
            Message("assistant", script[0].content),
            Message("user", (TextBlock("N1"),)),
        )


async def test_t4_allowed_tool_missing_from_the_server_is_a_wiring_error() -> None:
    """T4: a server without an allowed tool raises 'ValueError' instead of offering fewer tools."""
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress, offered=("get_deviations",))
    with pytest.raises(ValueError, match="emit_alert"):
        await make_coordinator(FakeModel([]), tools).run("S003", "brief", progress, LoopLog())
