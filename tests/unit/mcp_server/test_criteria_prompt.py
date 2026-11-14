"""010 T8: criteria MCP prompt served in-process, with error mapping (R11, E17)."""

from dataclasses import replace

import pytest
from mcp_builders import tool_context

from plant_monitor.agents.allowlists import COORDINATOR_TOOLS
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import build_server
from plant_monitor.mcp_server.types import CRITERIA_PROMPT

from builders import CRIT

pytestmark = pytest.mark.anyio


async def test_e17a_prompt_returns_criteria_unchanged_and_tools_stay_seven() -> None:
    """E17a: 'get_prompt' returns exactly CRIT (trailing newline kept); seven tools still listed."""
    ctx, frames = tool_context()
    server = build_server(replace(ctx, criteria=CRIT), frames, tools=COORDINATOR_TOOLS)
    async with ToolClient(server) as client:
        text = await client.get_prompt(CRITERIA_PROMPT)
        specs = await client.list_tools()
    assert CRITERIA_PROMPT == "criteria"
    assert text == CRIT
    assert sorted(spec.name for spec in specs) == sorted(COORDINATOR_TOOLS)
    assert len(specs) == 7


async def test_e17b_no_criteria_means_prompt_is_not_available() -> None:
    """E17b: a context with 'criteria' None raises ValueError with the mapped text."""
    ctx, frames = tool_context()
    unset = replace(ctx, criteria=None)  # the builder's context sets CRIT since 010 T14
    async with ToolClient(build_server(unset, frames, tools=COORDINATOR_TOOLS)) as client:
        with pytest.raises(ValueError) as raised:
            await client.get_prompt("criteria")
    assert str(raised.value) == "prompt criteria is not available"


async def test_e17c_unknown_prompt_name_is_not_available() -> None:
    """E17c: another name raises ValueError naming it, even when criteria is set."""
    ctx, frames = tool_context()
    server = build_server(replace(ctx, criteria=CRIT), frames, tools=COORDINATOR_TOOLS)
    async with ToolClient(server) as client:
        with pytest.raises(ValueError) as raised:
            await client.get_prompt("other")
    assert str(raised.value) == "prompt other is not available"
