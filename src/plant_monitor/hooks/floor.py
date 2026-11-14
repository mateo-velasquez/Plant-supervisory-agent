"""Floor hooks: a stated severity below the notice's is refused (R5); the computed floor is checked (R6)."""

from plant_monitor.hooks.calls import EMIT_TOOLS, targets
from plant_monitor.hooks.chain import FloorViolation, HookContext, ToolCall, require_view
from plant_monitor.hooks.texts import fold, stated_severities
from plant_monitor.mcp_server.types import APPLY_PROPOSAL, ToolOutcome


class TextFloorHook:
    """Blocks a text that states a severity below its notice's."""

    name = "floor"

    def check(self, call: ToolCall, ctx: HookContext) -> str | None:
        """The R5 reason for the first stated level below the record, else None."""
        if call.name not in EMIT_TOOLS:
            return None
        for case_id, notice, texto in targets(call, require_view(ctx, self.name)):
            for is_maxima, stated in stated_severities(fold(texto)):
                record = notice.severidad_maxima if is_maxima else notice.severidad
                if stated < record:
                    label = "severidad maxima" if is_maxima else "severidad"
                    return f"texto for {case_id} states {label} {stated}: below notice severity ({record})"
        return None


class FloorCheck:
    """After 'apply_proposal', every notice with a floor must meet it."""

    name = "floor"

    def verify(self, call: ToolCall, outcome: ToolOutcome, ctx: HookContext) -> None:
        """Raise 'FloorViolation' for a notice below its computed minimum."""
        if call.name != APPLY_PROPOSAL:
            return
        view = require_view(ctx, self.name)
        floors = view.floors()
        for notice in (*view.alerts(), *view.news()):
            floor = floors.get(notice.case_id)
            if floor is not None and notice.severidad < floor:
                raise FloorViolation(
                    f"{notice.notice_id}: severidad {notice.severidad} is below the computed "
                    f"minimum {floor} after {APPLY_PROPOSAL}"
                )
