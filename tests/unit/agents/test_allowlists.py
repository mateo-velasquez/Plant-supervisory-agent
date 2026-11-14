"""010 T3: allowlists, excluded tools and the three barriers (R2, E6, E24)."""

from pathlib import Path

import pytest
from agent_builders import FakeProgress, FakeTools, end
from judgment_builders import incident_tool_context

from plant_monitor.agents.allowlists import (
    ALLOWLISTS,
    COORDINATOR_TOOLS,
    EXCLUDED,
    INVESTIGATOR_TOOLS,
    check_allowlists,
)
from plant_monitor.agents.factory import build_coordinator, build_investigator
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import Settings
from plant_monitor.hooks.chain import HookChain
from plant_monitor.mcp_server import types
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import build_server
from plant_monitor.runner import agent_pipeline
from plant_monitor.telemetry.trace import AgentName, TraceWriter

from builders import CRIT, held_out_policy, isolate_settings_env
from notice_builders import plant_context

pytestmark = pytest.mark.anyio

OFFENDING: dict[AgentName, tuple[str, ...]] = {
    "investigator": INVESTIGATOR_TOOLS,
    "coordinator": (*COORDINATOR_TOOLS, "set_cause", "raise_severity"),
}
MESSAGE = "allowlist of the coordinator offers excluded tools: set_cause, raise_severity"


def test_e6a_no_list_meets_excluded_and_every_listed_name_is_registrable() -> None:
    """E6 (a): 'EXCLUDED' is the three judgment tools, disjoint from both lists, all registrable."""
    registrable = {*types.READ_TOOLS, *types.WRITE_TOOLS}
    assert {"set_cause", "raise_severity", "lift_severity_raise"} == EXCLUDED
    for names in ALLOWLISTS.values():
        assert EXCLUDED.isdisjoint(names)
        assert set(names) <= registrable
    check_allowlists(ALLOWLISTS)


def test_e6b_check_allowlists_names_the_excluded_tools_in_list_order() -> None:
    """E6 (b): an excluded tool in the coordinator list raises the R2 'ValueError'."""
    with pytest.raises(ValueError, match=MESSAGE):
        check_allowlists(OFFENDING)


def test_e6c_build_agent_pipeline_checks_the_lists_before_building_any_server(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E6 (c): the composition root raises the same error before any server is built."""
    built: list[object] = []
    monkeypatch.setattr(agent_pipeline, "ALLOWLISTS", OFFENDING)
    monkeypatch.setattr(agent_pipeline, "build_server", lambda *a, **k: built.append(a))
    isolate_settings_env(monkeypatch, tmp_path)
    with SqliteRegistry(":memory:") as registry, pytest.raises(ValueError, match=MESSAGE):
        agent_pipeline.build_agent_pipeline(
            Settings(anthropic_api_key="k"),
            registry,
            plant_context(),
            held_out_policy(is_open=True),
            FakeModel([]),
            TraceWriter(tmp_path / "trace.jsonl"),
            criteria=CRIT,
        )
    assert built == []


async def test_e6d_a_server_can_still_register_the_judgment_tools() -> None:
    """E6 (d): the server is not the barrier; 'WRITE_TOOLS' still lists 'set_cause'."""
    ctx, frames = incident_tool_context()
    async with ToolClient(build_server(ctx, frames, tools=types.WRITE_TOOLS)) as client:
        names = [spec.name for spec in await client.list_tools()]
    assert "set_cause" in names


def test_e24_allowlists_and_excluded_are_built_from_the_types_constants() -> None:
    """E24: the lists keep their order and every name is one of the 'types' constants."""
    assert COORDINATOR_TOOLS == (
        types.GET_DEVIATIONS,
        types.GET_ACTIVE_CASES,
        types.GET_CASE,
        types.GET_DELAYED_UNITS,
        types.APPLY_PROPOSAL,
        types.EMIT_ALERT,
        types.EMIT_SHIFT_REPORT,
    )
    assert INVESTIGATOR_TOOLS == (
        types.LIST_AVAILABLE_LOGBOOKS,
        types.GET_LOGBOOK,
        types.GET_CASE,
        types.GET_DELAYED_UNITS,
    )
    assert ALLOWLISTS == {"investigator": INVESTIGATOR_TOOLS, "coordinator": COORDINATOR_TOOLS}
    assert {types.SET_CAUSE, types.RAISE_SEVERITY, types.LIFT_SEVERITY_RAISE} == EXCLUDED


@pytest.mark.parametrize("agent", ["investigator", "coordinator"])
async def test_e24_built_agents_offer_exactly_their_allowlist(
    agent: AgentName, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E24: 'build_coordinator' and 'build_investigator' send exactly 'ALLOWLISTS[agent]'."""
    isolate_settings_env(monkeypatch, tmp_path)
    progress = FakeProgress()
    model = FakeModel([end("Listo.")])
    opener = FakeTools(progress).opener()
    settings = Settings(anthropic_api_key="k")
    if agent == "coordinator":
        loop = build_coordinator(settings, model, opener, hooks=HookChain())
    else:
        loop = build_investigator(settings, model, opener)
    await loop.run("S010", "brief", progress, LoopLog())
    assert tuple(spec.name for spec in model.requests[0].tools) == ALLOWLISTS[agent]
