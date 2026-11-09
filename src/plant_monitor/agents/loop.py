"""Coordinator loop: stop rules, tool execution, append-only history and budget guard (R3-R6)."""

import logging
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol

from plant_monitor.agents.brief import render_reminder
from plant_monitor.agents.model import (
    Effort,
    Message,
    ModelPort,
    ModelReply,
    ModelRequest,
    ModelSession,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
)
from plant_monitor.mcp_server.types import ToolOutcome, ToolSpec
from plant_monitor.telemetry.trace import ModelCallRecord, ToolCallRecord

logger = logging.getLogger(__name__)

MS_PER_SECOND = 1000


class ToolPort(Protocol):
    """The door to the tools; 'ToolClient' satisfies it structurally."""

    async def list_tools(self) -> tuple[ToolSpec, ...]: ...

    async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome: ...


class TextProgress(Protocol):
    """Notice ids that need a text and those still unwritten."""

    def required(self) -> tuple[str, ...]: ...

    def missing(self) -> tuple[str, ...]: ...


class LoopOutcome(StrEnum):
    """How a snapshot's loop ended; aborts are formatted by the trace layer."""

    DONE = "done"
    SKIPPED = "skipped"
    BUDGET_EXCEEDED = "fallback:budget_exceeded"
    TURN_CAP = "fallback:turn_cap"
    REFUSAL = "fallback:refusal"
    MAX_TOKENS = "fallback:max_tokens"
    MISSING_TEXTS = "fallback:missing_texts"
    UNEXPECTED_STOP = "fallback:unexpected_stop"


@dataclass(frozen=True)
class LoopConfig:
    max_turns: int
    prompt_token_limit: int
    max_tokens: int
    effort: Effort


@dataclass
class LoopLog:
    """Filled while the loop runs, so partial records survive an exception (E21)."""

    outcome: LoopOutcome | None = None
    model_calls: list[ModelCallRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)


_STOP_FALLBACKS = {"refusal": LoopOutcome.REFUSAL, "max_tokens": LoopOutcome.MAX_TOKENS}


class Coordinator:
    """Runs one fresh conversation per snapshot until the notice texts are written or a stop rule hits."""

    def __init__(
        self,
        model: ModelPort,
        tools: Callable[[], AbstractAsyncContextManager[ToolPort]],
        system: str,
        allowed: tuple[str, ...],
        config: LoopConfig,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._model = model
        self._tools = tools
        self._system = system
        self._allowed = allowed
        self._config = config
        self._clock = clock

    async def run(self, snapshot_id: str, brief: str, progress: TextProgress, log: LoopLog) -> LoopOutcome:
        """Run the loop for one snapshot and set 'log.outcome'."""
        async with self._model.session() as session, self._tools() as port:
            offered = await self._offered(port)
            log.outcome = await self._loop(session, port, offered, snapshot_id, brief, progress, log)
        return log.outcome

    async def _offered(self, port: ToolPort) -> tuple[ToolSpec, ...]:
        by_name = {spec.name: spec for spec in await port.list_tools()}
        absent = [name for name in self._allowed if name not in by_name]
        if absent:
            raise ValueError(f"the tool server lacks allowed tools: {', '.join(absent)}")
        return tuple(by_name[name] for name in self._allowed)

    async def _loop(
        self,
        session: ModelSession,
        port: ToolPort,
        offered: tuple[ToolSpec, ...],
        snapshot_id: str,
        brief: str,
        progress: TextProgress,
        log: LoopLog,
    ) -> LoopOutcome:
        config = self._config
        messages: tuple[Message, ...] = (Message("user", (TextBlock(brief),)),)
        reminded = False
        for turn in range(1, config.max_turns + 1):
            request = ModelRequest(self._system, offered, messages, config.max_tokens, config.effort)
            count = await session.count_tokens(request)
            if count > config.prompt_token_limit:
                logger.warning(
                    "snapshot %s turn %d: prompt of %d tokens is over the limit of %d; request not sent",
                    snapshot_id,
                    turn,
                    count,
                    config.prompt_token_limit,
                )
                return LoopOutcome.BUDGET_EXCEEDED
            started = self._clock()
            reply = await session.create(request)
            latency = self._ms_since(started)
            log.model_calls.append(ModelCallRecord(turn, reply.stop_reason, reply.usage, latency))
            log.thinking.extend(b.thinking for b in reply.content if isinstance(b, ThinkingBlock))
            messages = (*messages, Message("assistant", reply.content))
            if reply.stop_reason == "tool_use":
                results = await self._run_tools(port, offered, reply, turn, log)
                if not results:
                    return LoopOutcome.UNEXPECTED_STOP
                messages = (*messages, Message("user", results))
                if progress.required() and not progress.missing():
                    return LoopOutcome.DONE
            elif reply.stop_reason == "end_turn":
                missing = progress.missing()
                if not missing:
                    return LoopOutcome.DONE
                if reminded:
                    return LoopOutcome.MISSING_TEXTS
                reminded = True
                messages = (*messages, Message("user", (TextBlock(render_reminder(missing)),)))
            else:
                return _STOP_FALLBACKS.get(reply.stop_reason, LoopOutcome.UNEXPECTED_STOP)
        return LoopOutcome.TURN_CAP

    async def _run_tools(
        self,
        port: ToolPort,
        offered: tuple[ToolSpec, ...],
        reply: ModelReply,
        turn: int,
        log: LoopLog,
    ) -> tuple[ToolResultBlock, ...]:
        names = {spec.name for spec in offered}
        results: list[ToolResultBlock] = []
        for block in reply.content:
            if not isinstance(block, ToolUseBlock):
                continue
            started = self._clock()
            if block.name in names:
                outcome = await port.call(block.name, block.input)
            else:
                outcome = ToolOutcome(f"tool {block.name} is not available", True)
            log.tool_calls.append(
                ToolCallRecord(
                    turn=turn,
                    name=block.name,
                    arguments=block.input,
                    is_error=outcome.is_error,
                    result_chars=len(outcome.text),
                    error=outcome.text if outcome.is_error else None,
                    latency_ms=self._ms_since(started),
                )
            )
            results.append(ToolResultBlock(block.id, outcome.text, outcome.is_error))
        return tuple(results)

    def _ms_since(self, started: float) -> int:
        return round((self._clock() - started) * MS_PER_SECOND)
