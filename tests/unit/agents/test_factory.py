"""007 T7: 'build_coordinator' and prompt v1 (R15, E5)."""

import re
from importlib import resources
from pathlib import Path

import pytest
from agent_builders import ALERT_ID, FakeProgress, FakeTools, end, tool
from judgment_builders import incident_tool_context

from plant_monitor.agents.factory import COORDINATOR_TOOLS, build_coordinator, load_prompt
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog, LoopOutcome
from plant_monitor.config import Settings
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import READ_TOOLS, WRITE_TOOLS, build_server

from builders import isolate_settings_env

pytestmark = pytest.mark.anyio

HEADINGS = [
    "## Role",
    "## What code decides",
    "## Data, never instructions",
    "## Proposals",
    "## Perspectives",
    "## Numbers",
    "## Order of work",
    "## How to finish",
]
FORBIDDEN_NAMES = (
    "get_logbook",
    "list_available_logbooks",
    "set_cause",
    "raise_severity",
    "lift_severity_raise",
)


async def test_e5_build_coordinator_sends_the_packaged_prompt_and_coordinator_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E5: 'system' is 'load_prompt()' and 'tools' are 'COORDINATOR_TOOLS'."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k", agent_max_turns=4)
    progress = FakeProgress(ALERT_ID)
    tools = FakeTools(progress)
    model = FakeModel([tool("emit_alert", {"case_id": "c", "texto": "t"})])
    coordinator = build_coordinator(settings, model, tools.opener())
    outcome = await coordinator.run("S003", "brief", progress, LoopLog())
    request = model.requests[0]
    assert outcome is LoopOutcome.DONE
    assert request.system == load_prompt()
    assert request.max_tokens == settings.anthropic_max_tokens
    assert request.effort == settings.anthropic_effort
    assert tuple(spec.name for spec in request.tools) == COORDINATOR_TOOLS


def test_e8_prompt_v3_has_the_r13_headings_in_order_and_loads_from_the_package() -> None:
    """E8, R13: prompt v3 is packaged data with the R13 '##' headings in order."""
    packaged = resources.files("plant_monitor.agents").joinpath("prompts", "coordinator.md")
    prompt = load_prompt()
    assert prompt == packaged.read_text(encoding="utf-8")
    assert re.findall(r"^## .+$", prompt, flags=re.MULTILINE) == HEADINGS


def test_e8_prompt_v3_names_apply_proposal_no_logbook_or_judgment_tool_and_no_ids() -> None:
    """E8, R13: 'apply_proposal' is named; no logbook or 008 judgment tool; no snapshot or shift id."""
    prompt = load_prompt()
    assert prompt.startswith("# Coordinator prompt v3")
    assert "apply_proposal" in prompt
    assert [name for name in FORBIDDEN_NAMES if name in prompt] == []
    assert re.search(r"S\d{3}|T\d{2}", prompt) is None


def test_e7_coordinator_tools_are_the_seven_r12_names_and_no_logbook_or_judgment_tool() -> None:
    """E7, R12: the seven names in order, all registrable, 'apply_proposal' a write tool."""
    assert COORDINATOR_TOOLS == (
        "get_deviations",
        "get_active_cases",
        "get_case",
        "get_delayed_units",
        "apply_proposal",
        "emit_alert",
        "emit_shift_report",
    )
    assert set(COORDINATOR_TOOLS) <= {*READ_TOOLS, *WRITE_TOOLS}
    assert "apply_proposal" in WRITE_TOOLS
    assert [name for name in FORBIDDEN_NAMES if name in COORDINATOR_TOOLS] == []


async def test_e10_the_coordinator_cannot_reach_logbook_or_judgment_tools_even_by_asking(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E10, R12: the loop refuses both names, the server never runs them, a direct call is an error."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k")
    ctx, frames = incident_tool_context()
    server = build_server(ctx, frames, tools=COORDINATOR_TOOLS)
    model = FakeModel(
        [
            tool("get_logbook", {"turno_id": "T05"}),
            tool("set_cause", {"case_id": "c"}, "tu-2"),
            end("Listo."),
        ]
    )
    log = LoopLog()
    coordinator = build_coordinator(settings, model, lambda: ToolClient(server))
    await coordinator.run("S010", "brief", FakeProgress(), log)
    assert [(t.name, t.is_error, t.error) for t in log.tool_calls] == [
        ("get_logbook", True, "tool get_logbook is not available"),
        ("set_cause", True, "tool set_cause is not available"),
    ]
    async with ToolClient(server) as client:
        direct = await client.call("get_logbook", {"turno_id": "T05"})
    assert direct.is_error
