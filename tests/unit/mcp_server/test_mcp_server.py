"""006 T7: no frame, tool listing and nested frames through the in-process client (R7, R13, E11)."""

import pytest
from mcp_builders import frame_at, tool_context

from plant_monitor.mcp_server.client import ToolClient, ToolSpec
from plant_monitor.mcp_server.server import READ_TOOLS, build_server

pytestmark = pytest.mark.anyio


async def test_e11a_no_frame_is_refused_with_full_text() -> None:
    """E11a: a tool call outside a frame is a refusal."""
    ctx, frames = tool_context()
    async with ToolClient(build_server(ctx, frames)) as client:
        outcome = await client.call("get_deviations", {})
    assert outcome.is_error
    assert outcome.text == "Error executing tool get_deviations: no snapshot is being processed"


async def test_e11b_lists_exactly_the_six_read_tools_without_snapshot_argument() -> None:
    """E11b: six ToolSpecs, none with a snapshot parameter."""
    ctx, frames = tool_context()
    async with ToolClient(build_server(ctx, frames)) as client:
        specs = await client.list_tools()
    assert all(isinstance(spec, ToolSpec) for spec in specs)
    assert sorted(spec.name for spec in specs) == sorted(READ_TOOLS)
    assert len(specs) == 6
    forbidden = {"snapshot_id", "at", "snapshot"}
    for spec in specs:
        properties = spec.input_schema.get("properties", {})
        assert isinstance(properties, dict)
        assert not forbidden & set(properties)


def test_e11c_nested_frame_raises_value_error() -> None:
    """E11c: entering a frame while one is entered raises to the code."""
    _, frames = tool_context()
    with frames.entered(frame_at("S003")), pytest.raises(ValueError), frames.entered(frame_at("S004")):
        pass
