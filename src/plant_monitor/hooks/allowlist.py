"""Allowlist hook: a tool outside the agent's list is refused (R3)."""

from collections.abc import Sequence

from plant_monitor.hooks.chain import HookContext, ToolCall


class AllowlistHook:
    """Blocks any tool whose name is not in the agent's list; the caller supplies the list."""

    name = "allowlist"

    def __init__(self, agent: str, tools: Sequence[str]) -> None:
        self._agent = agent
        self._tools = frozenset(tools)

    def check(self, call: ToolCall, ctx: HookContext) -> str | None:
        """The R3 reason when the tool is not allowed, else None."""
        if call.name in self._tools:
            return None
        return f"tool {call.name} is not allowed for the {self._agent}"
