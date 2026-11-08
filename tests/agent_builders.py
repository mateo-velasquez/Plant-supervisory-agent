"""Minimal doubles and reply builders for 007 loop tests (fake tool port, progress, scripted replies)."""

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import Coordinator, LoopConfig, ToolPort
from plant_monitor.agents.model import ModelReply, TextBlock, ToolUseBlock
from plant_monitor.mcp_server.types import ToolOutcome, ToolSpec
from plant_monitor.telemetry.usage import Usage

OFFERED = (
    "list_available_logbooks",
    "get_logbook",
    "get_deviations",
    "get_active_cases",
    "get_case",
    "get_delayed_units",
    "emit_alert",
    "emit_shift_report",
)
WRITE_NAMES = ("emit_alert", "emit_shift_report")
ALERT_ID = "S003-alerta_inmediata-S001-Sedán-Local"
USAGE = Usage(input_tokens=100, output_tokens=20)


class FakeProgress:
    """Notice ids still missing; a successful write tool empties them."""

    def __init__(self, *pending: str) -> None:
        self.pending = list(pending)

    def missing(self) -> tuple[str, ...]:
        return tuple(self.pending)


class FakeTools:
    """A tool port that records calls and answers from a table ('ok' by default)."""

    def __init__(
        self,
        progress: FakeProgress,
        answers: Mapping[str, ToolOutcome] | None = None,
        offered: Sequence[str] = OFFERED,
    ) -> None:
        self.progress = progress
        self.answers = dict(answers or {})
        self.offered = tuple(offered)
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    async def list_tools(self) -> tuple[ToolSpec, ...]:
        return tuple(ToolSpec(name, f"{name} tool", {"type": "object"}) for name in self.offered)

    async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome:
        self.calls.append((name, arguments))
        outcome = self.answers.get(name, ToolOutcome("ok", False))
        if name in WRITE_NAMES and not outcome.is_error:
            self.progress.pending.clear()
        return outcome

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def opener(self) -> Callable[[], AbstractAsyncContextManager[ToolPort]]:
        @asynccontextmanager
        async def open_tools() -> AsyncIterator[ToolPort]:
            yield self

        return open_tools


def tool(name: str, arguments: Mapping[str, object], tool_use_id: str = "tu-1") -> ModelReply:
    """A reply that calls one tool."""
    return ModelReply((ToolUseBlock(tool_use_id, name, arguments),), "tool_use", USAGE)


def end(text: str) -> ModelReply:
    """A reply that ends the turn with text."""
    return ModelReply((TextBlock(text),), "end_turn", USAGE)


def stopped(reason: str) -> ModelReply:
    """A text reply with the given stop reason."""
    return ModelReply((TextBlock("..."),), reason, USAGE)


def make_coordinator(
    model: FakeModel,
    tools: FakeTools,
    *,
    max_turns: int = 8,
    limit: int = 95_000,
    allowed: tuple[str, ...] = OFFERED,
    system: str = "SYSTEM",
) -> Coordinator:
    config = LoopConfig(max_turns=max_turns, prompt_token_limit=limit, max_tokens=16_000, effort="medium")
    return Coordinator(model, tools.opener(), system, allowed, config)
