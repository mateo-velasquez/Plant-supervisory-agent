"""MCP server: async tool wrappers over the sync read tools, refusals mapped to ToolError (R13)."""

from collections.abc import Awaitable, Callable, Collection
from typing import Final

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.mcp_server import read_tools, write_tools
from plant_monitor.mcp_server.context import FrameHolder, ToolContext
from plant_monitor.mcp_server.write_tools import NewsText

READ_TOOLS: Final[tuple[str, ...]] = (
    "list_available_logbooks",
    "get_logbook",
    "get_deviations",
    "get_active_cases",
    "get_case",
    "get_delayed_units",
)
WRITE_TOOLS: Final[tuple[str, ...]] = (
    "set_cause",
    "raise_severity",
    "lift_severity_raise",
    "apply_proposal",
    "emit_alert",
    "emit_shift_report",
)


def _refusals(call: Callable[[], str]) -> str:
    """Run a sync tool; a refusal becomes a ToolError the SDK prefixes with the tool name."""
    try:
        return call()
    except RejectedRequest as error:
        raise ToolError(str(error)) from error


def build_server(ctx: ToolContext, frames: FrameHolder, tools: Collection[str] = READ_TOOLS) -> MCPServer:
    """MCP server with the named tools (default the six read tools); none takes a snapshot (R7)."""
    unknown = sorted(set(tools) - {*READ_TOOLS, *WRITE_TOOLS})
    if unknown:
        raise ValueError(f"unknown tools: {', '.join(unknown)}")
    server = MCPServer("plant-monitor")

    async def list_available_logbooks() -> str:
        """List the logbooks closed at the current snapshot."""
        return _refusals(lambda: read_tools.list_available_logbooks(ctx, frames))

    async def get_logbook(turno_id: str) -> str:
        """Return the delimited logbook of one shift closed at the current snapshot."""
        return _refusals(lambda: read_tools.get_logbook(ctx, frames, turno_id))

    async def get_deviations() -> str:
        """Return the deviation of every model and market at the current snapshot."""
        return _refusals(lambda: read_tools.get_deviations(ctx, frames))

    async def get_active_cases() -> str:
        """Return the active cases at the current snapshot."""
        return _refusals(lambda: read_tools.get_active_cases(ctx, frames))

    async def get_case(case_id: str) -> str:
        """Return one case with its history."""
        return _refusals(lambda: read_tools.get_case(ctx, frames, case_id))

    async def get_delayed_units(modelo: Model, mercado: Market) -> str:
        """Return the delayed units of one model and market at the current snapshot."""
        return _refusals(lambda: read_tools.get_delayed_units(ctx, frames, modelo, mercado))

    async def set_cause(
        case_id: str, categoria: CauseCategory, etapa: Stage, bitacora: str, fragmento: str
    ) -> str:
        """Record the cause a logbook fragment gives for one case, with its stage."""
        return _refusals(
            lambda: write_tools.set_cause(ctx, frames, case_id, categoria, etapa, bitacora, fragmento)
        )

    async def raise_severity(
        categoria: CauseCategory,
        etapa: Stage,
        modelo: Model,
        bitacora: str,
        fragmento: str,
        mercado: Market | None = None,
    ) -> str:
        """Raise severity over a model and stage (any market when 'mercado' is omitted) from a fragment."""
        return _refusals(
            lambda: write_tools.raise_severity(
                ctx, frames, categoria, etapa, modelo, mercado, bitacora, fragmento
            )
        )

    async def lift_severity_raise(active_cause_id: str, bitacora: str, fragmento: str) -> str:
        """Lift an active cause with a fragment of a later logbook."""
        return _refusals(
            lambda: write_tools.lift_severity_raise(ctx, frames, active_cause_id, bitacora, fragmento)
        )

    async def apply_proposal(propuesta: str) -> str:
        """Apply one validated proposal of this snapshot by its id."""
        return _refusals(lambda: write_tools.apply_proposal(ctx, frames, propuesta))

    async def emit_alert(case_id: str, texto: str) -> str:
        """Write the text of this snapshot's immediate alert for one case."""
        return _refusals(lambda: write_tools.emit_alert(ctx, frames, case_id, texto))

    async def emit_shift_report(textos: list[NewsText]) -> str:
        """Write the text of every news item of the shift report, one entry per case."""
        return _refusals(lambda: write_tools.emit_shift_report(ctx, frames, textos))

    available: dict[str, Callable[..., Awaitable[str]]] = {
        "list_available_logbooks": list_available_logbooks,
        "get_logbook": get_logbook,
        "get_deviations": get_deviations,
        "get_active_cases": get_active_cases,
        "get_case": get_case,
        "get_delayed_units": get_delayed_units,
        "set_cause": set_cause,
        "raise_severity": raise_severity,
        "lift_severity_raise": lift_severity_raise,
        "apply_proposal": apply_proposal,
        "emit_alert": emit_alert,
        "emit_shift_report": emit_shift_report,
    }
    for name in (*READ_TOOLS, *WRITE_TOOLS):
        if name in tools:
            server.add_tool(available[name], name=name)
    return server
