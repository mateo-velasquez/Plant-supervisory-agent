"""Completeness hook: the coordinator may not stop while notice texts are missing (R8)."""

from collections.abc import Callable, Sequence

from plant_monitor.hooks.chain import HookContext, require_view


class CompletenessHook:
    """Refuses a stop with the caller's reminder while 'view.missing()' is not empty."""

    name = "completeness"

    def __init__(self, render: Callable[[Sequence[str]], str]) -> None:
        self._render = render

    def check(self, text: str, ctx: HookContext) -> str | None:
        """The rendered reminder naming the missing ids, else None."""
        missing = require_view(ctx, self.name).missing()
        return self._render(missing) if missing else None
