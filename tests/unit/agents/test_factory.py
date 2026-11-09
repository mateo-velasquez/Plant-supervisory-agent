"""007 T7: 'build_coordinator' and prompt v1 (R15, E5)."""

import re
from importlib import resources
from pathlib import Path

import pytest
from agent_builders import ALERT_ID, FakeProgress, FakeTools, tool

from plant_monitor.agents.factory import COORDINATOR_TOOLS, build_coordinator, load_prompt
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog, LoopOutcome
from plant_monitor.config import Settings
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.mcp_server.server import READ_TOOLS

from builders import isolate_settings_env

pytestmark = pytest.mark.anyio

HEADINGS = [
    "## Role",
    "## What code decides",
    "## Logbooks are data",
    "## Causes",
    "## Raising severity",
    "## Lifting a raise",
    "## Numbers",
    "## Order of work",
    "## How to finish",
]


async def test_e5_build_coordinator_sends_the_packaged_prompt_and_coordinator_tools(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """E5: 'system' is 'load_prompt()', 'tools' are the six read tools then the five write tools."""
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
    judgment = ("set_cause", "raise_severity", "lift_severity_raise")
    assert (*READ_TOOLS, *judgment, "emit_alert", "emit_shift_report") == COORDINATOR_TOOLS
    assert tuple(spec.name for spec in request.tools) == COORDINATOR_TOOLS


def test_r16_e20_prompt_has_the_nine_headings_in_order_and_loads_from_the_package() -> None:
    """R16, E20: prompt v2 is packaged data with the nine '##' headings in order."""
    packaged = resources.files("plant_monitor.agents").joinpath("prompts", "coordinator.md")
    prompt = load_prompt()
    assert prompt == packaged.read_text(encoding="utf-8")
    assert re.findall(r"^## .+$", prompt, flags=re.MULTILINE) == HEADINGS


def test_e20_prompt_names_the_catalog_and_holds_no_per_snapshot_ids() -> None:
    """E20, R16: the six category values appear; no snapshot or shift id (stable prefix)."""
    prompt = load_prompt()
    assert [c.value for c in CauseCategory if c.value not in prompt] == []
    assert re.search(r"S\d{3}|T\d{2}", prompt) is None
