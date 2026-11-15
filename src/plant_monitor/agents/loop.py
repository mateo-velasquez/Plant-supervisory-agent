"""Coordinator loop: stop rules, tool execution, append-only history and budget guard (R3-R6)."""

import logging
import time
from collections.abc import Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field, replace
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
from plant_monitor.agents.output import strict_schema
from plant_monitor.agents.prefix import PrefixMonitor, prefix_hash
from plant_monitor.hooks.allowlist import AllowlistHook
from plant_monitor.hooks.chain import HookChain, HookContext, ToolCall
from plant_monitor.hooks.view import SnapshotView
from plant_monitor.mcp_server.types import ToolOutcome, ToolSpec
from plant_monitor.telemetry.trace import (
    BUDGET_EXCEEDED_OUTCOME,
    AgentName,
    HookRecord,
    ModelCallRecord,
    ToolCallRecord,
)

logger = logging.getLogger(__name__)

MS_PER_SECOND = 1000


class ToolPort(Protocol):
    """The door to the tools; 'ToolClient' satisfies it structurally."""

    async def list_tools(self) -> tuple[ToolSpec, ...]: ...

    async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome: ...

    async def get_prompt(self, name: str) -> str: ...


def compose_system(role: str, criteria: str) -> str:
    """The role prompt followed by the criteria in a '<criterios>' block."""
    return f"{role.rstrip()}\n\n<criterios>\n{criteria.strip()}\n</criterios>"


class TextProgress(Protocol):
    """Notice ids that need a text and those still unwritten."""

    def required(self) -> tuple[str, ...]: ...

    def missing(self) -> tuple[str, ...]: ...


class LoopOutcome(StrEnum):
    """How a snapshot's loop ended; aborts are formatted by the trace layer."""

    DONE = "done"
    SKIPPED = "skipped"
    BUDGET_EXCEEDED = BUDGET_EXCEEDED_OUTCOME
    TURN_CAP = "fallback:turn_cap"
    REFUSAL = "fallback:refusal"
    MAX_TOKENS = "fallback:max_tokens"
    MISSING_TEXTS = "fallback:missing_texts"
    INVALID_OUTPUT = "fallback:invalid_output"
    UNEXPECTED_STOP = "fallback:unexpected_stop"


class EndReview(Protocol):
    """Judges the text of an 'end_turn' reply: a note to send back, or None to accept."""

    @property
    def exhausted(self) -> LoopOutcome:
        """The outcome when a note beyond 'max_notes' would be needed."""
        ...

    def review(self, text: str) -> str | None: ...


class MissingTexts:
    """The coordinator's review: remind of the notice texts still unwritten."""

    def __init__(self, progress: TextProgress) -> None:
        self._progress = progress

    @property
    def exhausted(self) -> LoopOutcome:
        return LoopOutcome.MISSING_TEXTS

    def review(self, text: str) -> str | None:
        missing = self._progress.missing()
        return render_reminder(missing) if missing else None


@dataclass(frozen=True)
class LoopConfig:
    max_turns: int
    prompt_token_limit: int
    max_tokens: int
    effort: Effort
    max_notes: int = 1


@dataclass
class LoopLog:
    """Filled while the loop runs, so partial records survive an exception (E21)."""

    outcome: LoopOutcome | None = None
    model_calls: list[ModelCallRecord] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    thinking: list[str] = field(default_factory=list)
    hooks: list[HookRecord] = field(default_factory=list)


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
        *,
        agent: AgentName = "coordinator",
        hooks: HookChain | None = None,
        criteria_prompt: str | None = None,
        output_schema: Mapping[str, object] | None = None,
        prefix_monitor: PrefixMonitor | None = None,
    ) -> None:
        self._model = model
        self._tools = tools
        self._system = system
        self._allowed = allowed
        self._config = config
        self._clock = clock
        self._agent = agent
        self._criteria_prompt = criteria_prompt
        self._output_schema = output_schema
        self._prefix_monitor = prefix_monitor
        self._hooks = (hooks or HookChain()).with_first(AllowlistHook(agent, allowed))

    async def run(
        self,
        snapshot_id: str,
        brief: str,
        progress: TextProgress,
        log: LoopLog,
        review: EndReview | None = None,
        *,
        view: SnapshotView | None = None,
    ) -> LoopOutcome:
        """Run the loop for one snapshot and set 'log.outcome'; no 'review' means 'MissingTexts'."""
        end_review = MissingTexts(progress) if review is None else review
        async with self._model.session() as session, self._tools() as port:
            offered = await self._offered(port)
            system = self._system
            if self._criteria_prompt is not None:
                system = compose_system(system, await port.get_prompt(self._criteria_prompt))
            digest = prefix_hash(system, offered, self._output_schema)
            if self._prefix_monitor is not None:
                self._prefix_monitor.on_run(self._agent, snapshot_id, digest)
            log.outcome = await self._loop(
                session, port, offered, system, snapshot_id, brief, progress, log, end_review, view, digest
            )
        return log.outcome

    async def _offered(self, port: ToolPort) -> tuple[ToolSpec, ...]:
        by_name = {spec.name: spec for spec in await port.list_tools()}
        absent = [name for name in self._allowed if name not in by_name]
        if absent:
            raise ValueError(f"the tool server lacks allowed tools: {', '.join(absent)}")
        return tuple(
            replace(by_name[name], input_schema=strict_schema(by_name[name].input_schema))
            for name in self._allowed
        )

    async def _loop(
        self,
        session: ModelSession,
        port: ToolPort,
        offered: tuple[ToolSpec, ...],
        system: str,
        snapshot_id: str,
        brief: str,
        progress: TextProgress,
        log: LoopLog,
        end_review: EndReview,
        view: SnapshotView | None,
        digest: str,
    ) -> LoopOutcome:
        config = self._config
        messages: tuple[Message, ...] = (Message("user", (TextBlock(brief),)),)
        notes_sent = 0
        for turn in range(1, config.max_turns + 1):
            request = ModelRequest(
                system, offered, messages, config.max_tokens, config.effort, self._output_schema
            )
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
            ctx = HookContext(self._agent, turn, view)
            started = self._clock()
            reply = await session.create(request)
            latency = self._ms_since(started)
            log.model_calls.append(ModelCallRecord(turn, reply.stop_reason, reply.usage, latency, digest))
            if self._prefix_monitor is not None:
                self._prefix_monitor.on_call(self._agent, snapshot_id, turn, reply.usage, digest)
            log.thinking.extend(b.thinking for b in reply.content if isinstance(b, ThinkingBlock))
            messages = (*messages, Message("assistant", reply.content))
            if reply.stop_reason == "tool_use":
                results = await self._run_tools(port, reply, ctx, log)
                if not results:
                    return LoopOutcome.UNEXPECTED_STOP
                messages = (*messages, Message("user", results))
                if progress.required() and not progress.missing():
                    return LoopOutcome.DONE
            elif reply.stop_reason == "end_turn":
                text = "\n".join(b.text for b in reply.content if isinstance(b, TextBlock))
                block = self._hooks.on_stop(text, ctx)
                if block is not None:
                    log.hooks.append(HookRecord(self._agent, "on_stop", block.hook, None, turn, block.reason))
                    note: str | None = block.reason
                else:
                    note = end_review.review(text)
                if note is None:
                    return LoopOutcome.DONE
                if notes_sent >= config.max_notes:
                    return end_review.exhausted
                notes_sent += 1
                messages = (*messages, Message("user", (TextBlock(note),)))
            else:
                return _STOP_FALLBACKS.get(reply.stop_reason, LoopOutcome.UNEXPECTED_STOP)
        return LoopOutcome.TURN_CAP

    async def _run_tools(
        self,
        port: ToolPort,
        reply: ModelReply,
        ctx: HookContext,
        log: LoopLog,
    ) -> tuple[ToolResultBlock, ...]:
        results: list[ToolResultBlock] = []
        for block in reply.content:
            if not isinstance(block, ToolUseBlock):
                continue
            started = self._clock()
            call = ToolCall(block.name, block.input)
            refusal = self._hooks.pre_tool(call, ctx)
            if refusal is None:
                outcome = await port.call(block.name, block.input)
            else:
                outcome = ToolOutcome(refusal.reason, True)
                log.hooks.append(
                    HookRecord(self._agent, "pre_tool", refusal.hook, block.name, ctx.turn, refusal.reason)
                )
            log.tool_calls.append(
                ToolCallRecord(
                    turn=ctx.turn,
                    name=block.name,
                    arguments=block.input,
                    is_error=outcome.is_error,
                    result_chars=len(outcome.text),
                    error=outcome.text if outcome.is_error else None,
                    latency_ms=self._ms_since(started),
                )
            )
            if refusal is None:
                self._hooks.post_tool(call, outcome, ctx)
            results.append(ToolResultBlock(block.id, outcome.text, outcome.is_error))
        return tuple(results)

    def _ms_since(self, started: float) -> int:
        return round((self._clock() - started) * MS_PER_SECOND)
