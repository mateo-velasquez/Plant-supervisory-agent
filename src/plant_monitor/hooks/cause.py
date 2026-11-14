"""Cause hook: a text may not name a category other than the notice's 'causa' (R7)."""

from plant_monitor.hooks.calls import EMIT_TOOLS, targets
from plant_monitor.hooks.chain import HookContext, ToolCall, require_view
from plant_monitor.hooks.texts import fold, named_categories


class CauseHook:
    """Blocks a text naming a cause category that differs from its notice's."""

    name = "cause"

    def check(self, call: ToolCall, ctx: HookContext) -> str | None:
        """The R7 reason for the first differing category named, else None."""
        if call.name not in EMIT_TOOLS:
            return None
        for case_id, notice, texto in targets(call, require_view(ctx, self.name)):
            for named in named_categories(fold(texto)):
                if named != notice.causa.categoria:
                    return f"texto for {case_id} names cause {named}; its causa is {notice.causa.categoria}"
        return None
