"""Novelty hook: an emit for a case without news is refused (R4)."""

from plant_monitor.hooks.calls import emitted_case_ids
from plant_monitor.hooks.chain import HookContext, ToolCall, require_view


class NoveltyHook:
    """Blocks the first emitted case outside the snapshot's alerts and news."""

    name = "novelty"

    def check(self, call: ToolCall, ctx: HookContext) -> str | None:
        """The R4 reason for the first case without news, else None."""
        case_ids = emitted_case_ids(call)
        if not case_ids:
            return None
        view = require_view(ctx, self.name)
        known = {notice.case_id for notice in (*view.alerts(), *view.news())}
        for case_id in case_ids:
            if case_id not in known:
                return f"{case_id}: no news since last report"
        return None
