"""MCP server: async tool wrappers over the sync read tools, refusals mapped to ToolError (R13)."""

from collections.abc import Callable
from typing import Final

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.mcp_server import read_tools
from plant_monitor.mcp_server.context import FrameHolder, ToolContext

READ_TOOLS: Final[tuple[str, ...]] = (
    "list_available_logbooks",
    "get_logbook",
    "get_deviations",
    "get_active_cases",
    "get_case",
    "get_delayed_units",
)


def _refusals(call: Callable[[], str]) -> str:
    """Run a sync tool; a refusal becomes a ToolError the SDK prefixes with the tool name."""
    try:
        return call()
    except RejectedRequest as error:
        raise ToolError(str(error)) from error


def build_server(ctx: ToolContext, frames: FrameHolder) -> MCPServer:
    """MCP server with the six read tools; none takes a snapshot argument (R7)."""
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

    server.add_tool(list_available_logbooks, name="list_available_logbooks")
    server.add_tool(get_logbook, name="get_logbook")
    server.add_tool(get_deviations, name="get_deviations")
    server.add_tool(get_active_cases, name="get_active_cases")
    server.add_tool(get_case, name="get_case")
    server.add_tool(get_delayed_units, name="get_delayed_units")
    return server
