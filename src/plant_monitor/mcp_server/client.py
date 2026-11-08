"""In-process MCP client: the only door 'agents' uses; returns plain dataclasses, no 'mcp' types (D4)."""

from collections.abc import Mapping
from types import TracebackType
from typing import Self

from mcp import Client
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent

from plant_monitor.mcp_server.types import ToolOutcome as ToolOutcome
from plant_monitor.mcp_server.types import ToolSpec as ToolSpec


class ToolClient:
    """Async context manager over an in-process MCP server."""

    def __init__(self, server: MCPServer) -> None:
        self._client = Client(server)

    async def __aenter__(self) -> Self:
        """Connect to the server in-process."""
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Disconnect from the server."""
        await self._client.__aexit__(exc_type, exc, traceback)

    async def list_tools(self) -> tuple[ToolSpec, ...]:
        """Every tool the server offers, as plain specs."""
        result = await self._client.list_tools()
        return tuple(
            ToolSpec(name=tool.name, description=tool.description or "", input_schema=tool.input_schema)
            for tool in result.tools
        )

    async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome:
        """Call 'name' with 'arguments' and return its text; refusals come back with 'is_error'."""
        result = await self._client.call_tool(name, dict(arguments))
        text = "".join(block.text for block in result.content if isinstance(block, TextContent))
        return ToolOutcome(text=text, is_error=result.is_error)
