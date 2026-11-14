"""Hook protocols, the call and context types, and the chain that runs them (R1, R9)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from plant_monitor.hooks.view import SnapshotView
from plant_monitor.mcp_server.types import ToolOutcome


@dataclass(frozen=True)
class ToolCall:
    """A tool call the model asked for."""

    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class HookContext:
    """Who is running, in which turn, over which snapshot view."""

    agent: str
    turn: int
    view: SnapshotView | None


@dataclass(frozen=True)
class HookBlock:
    """A hook's refusal: its name and the reason handed back to the model."""

    hook: str
    reason: str


class HookViolation(RuntimeError):
    """A hook found a broken invariant; it is never caught by the chain or the loop."""


class FloorViolation(HookViolation):
    """A notice sits below its computed minimum severity."""


class MissingView(HookViolation):
    """A hook that needs the snapshot view ran without one."""


def require_view(ctx: HookContext, name: str) -> SnapshotView:
    """The context's view, or 'MissingView' naming the hook."""
    if ctx.view is None:
        raise MissingView(f"hook {name} needs a snapshot view")
    return ctx.view


class PreToolHook(Protocol):
    """Runs before a tool call; a reason blocks it."""

    @property
    def name(self) -> str:
        """Hook name as written in the trace."""
        ...

    def check(self, call: ToolCall, ctx: HookContext) -> str | None:
        """A reason to block the call, or None."""
        ...


class PostToolHook(Protocol):
    """Runs after a tool call; raises on a violation."""

    @property
    def name(self) -> str:
        """Hook name as written in the trace."""
        ...

    def verify(self, call: ToolCall, outcome: ToolOutcome, ctx: HookContext) -> None:
        """Raise a 'HookViolation' when the outcome breaks an invariant."""
        ...


class StopHook(Protocol):
    """Runs when the model ends its turn; a reason sends it back to work."""

    @property
    def name(self) -> str:
        """Hook name as written in the trace."""
        ...

    def check(self, text: str, ctx: HookContext) -> str | None:
        """A reason to refuse the stop, or None."""
        ...


class HookChain:
    """Ordered hooks per phase; it catches nothing."""

    def __init__(
        self,
        pre: Sequence[PreToolHook] = (),
        post: Sequence[PostToolHook] = (),
        stop: Sequence[StopHook] = (),
    ) -> None:
        self._pre = tuple(pre)
        self._post = tuple(post)
        self._stop = tuple(stop)

    def pre_tool(self, call: ToolCall, ctx: HookContext) -> HookBlock | None:
        """The first pre hook that blocks wins; later ones are not called."""
        for hook in self._pre:
            reason = hook.check(call, ctx)
            if reason is not None:
                return HookBlock(hook.name, reason)
        return None

    def post_tool(self, call: ToolCall, outcome: ToolOutcome, ctx: HookContext) -> None:
        """Every post hook runs, in order."""
        for hook in self._post:
            hook.verify(call, outcome, ctx)

    def on_stop(self, text: str, ctx: HookContext) -> HookBlock | None:
        """The first stop hook that blocks wins; later ones are not called."""
        for hook in self._stop:
            reason = hook.check(text, ctx)
            if reason is not None:
                return HookBlock(hook.name, reason)
        return None

    def with_first(self, hook: PreToolHook) -> HookChain:
        """A new chain with 'hook' ahead of the pre hooks."""
        return HookChain((hook, *self._pre), self._post, self._stop)
