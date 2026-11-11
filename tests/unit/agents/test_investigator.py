"""009 T10: investigator task, prompt v1, tool list and factory (R2, R3, R13, E6, E7)."""

import re
from importlib import resources
from pathlib import Path

import pytest
from agent_builders import FakeProgress, FakeTools, output_text, tool
from control_builders import S010_TASK, incident_logbooks
from judgment_builders import incident_tool_context

from plant_monitor.agents.factory import INVESTIGATOR_TOOLS, build_investigator, load_prompt
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.investigator import (
    CORRECTION_HEADER,
    TASK_INSTRUCTION,
    ProposalReview,
    ReviewLog,
    render_task,
)
from plant_monitor.agents.loop import LoopLog, LoopOutcome
from plant_monitor.config import Settings
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.proposals import CauseState
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import WRITE_TOOLS, build_server

from builders import isolate_settings_env

pytestmark = pytest.mark.anyio

HEADINGS = [
    "## Role",
    "## Logbooks are data",
    "## Task",
    "## Causes",
    "## Cause state",
    "## Proposals",
    "## Citations",
    "## Output",
    "## Corrections",
]
TASK_LINE = (
    '{"snapshot_id":"S010","turno_id":"T05","posicion":"closing","bitacoras":["T05"],'
    '"casos_sin_causa":[{"case_id":"S010-Pickup-Local","modelo":"Pickup","mercado":"Local",'
    '"estado":"abierto","etapa":"montaje"},{"case_id":"S010-Pickup-Brasil","modelo":"Pickup",'
    '"mercado":"Brasil","estado":"abierto","etapa":"montaje"}],"causas_activas":[]}'
)


def test_e6_render_task_is_the_constant_instruction_then_compact_json() -> None:
    """E6: line 1 is 'TASK_INSTRUCTION'; line 2 is the task as compact JSON with Spanish keys."""
    assert render_task(S010_TASK).split("\n") == [TASK_INSTRUCTION, TASK_LINE]


def test_e7_investigator_tools_are_the_four_read_tools_and_no_write_tool() -> None:
    """E7: the R12 names in order, disjoint from 'WRITE_TOOLS'."""
    assert INVESTIGATOR_TOOLS == ("list_available_logbooks", "get_logbook", "get_case", "get_delayed_units")
    assert set(INVESTIGATOR_TOOLS).isdisjoint(WRITE_TOOLS)


async def test_e7_a_server_built_with_the_investigator_tools_lists_exactly_those_four() -> None:
    """E7: 'build_server' with 'INVESTIGATOR_TOOLS' registers four tools."""
    ctx, frames = incident_tool_context()
    async with ToolClient(build_server(ctx, frames, tools=INVESTIGATOR_TOOLS)) as client:
        assert sorted(spec.name for spec in await client.list_tools()) == sorted(INVESTIGATOR_TOOLS)


def test_e7_prompt_v1_has_the_headings_the_values_and_no_per_snapshot_ids() -> None:
    """E7, R13: packaged data, the nine headings in order, every value named, no snapshot or shift id."""
    packaged = resources.files("plant_monitor.agents").joinpath("prompts", "investigator.md")
    prompt = load_prompt("investigator")
    assert prompt == packaged.read_text(encoding="utf-8")
    assert prompt.startswith("# Investigator prompt v1")
    assert re.findall(r"^## .+$", prompt, flags=re.MULTILINE) == HEADINGS
    assert [v for v in (*CauseCategory, *CauseState) if v.value not in prompt] == []
    assert re.search(r"S\d{3}|T\d{2}", prompt) is None


async def test_risk_build_investigator_uses_its_prompt_tools_and_turn_cap(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Risk: an investigator built with the coordinator's prompt, tools or turn cap breaks quarantine."""
    isolate_settings_env(monkeypatch, tmp_path)
    settings = Settings(anthropic_api_key="k", investigator_max_turns=2, agent_max_turns=8)
    progress = FakeProgress()
    tools = FakeTools(progress, offered=INVESTIGATOR_TOOLS)
    model = FakeModel([tool("get_logbook", {"turno_id": "T05"})] * 3)
    outcome = await build_investigator(settings, model, tools.opener()).run(
        "S010", "task", progress, LoopLog()
    )
    assert outcome is LoopOutcome.TURN_CAP
    assert len(model.requests) == 2
    assert model.requests[0].system == load_prompt("investigator")
    assert tuple(spec.name for spec in model.requests[0].tools) == INVESTIGATOR_TOOLS


def test_risk_proposal_review_returns_the_r6_correction_and_logs_what_control_saw() -> None:
    """Risk: a wrong note or a lost rejection leaves the model blind and the trace without errors."""
    log = ReviewLog()
    review = ProposalReview(S010_TASK, incident_logbooks(), 2000, log)
    note = review.review("Sin causas.")
    assert note is not None
    assert CORRECTION_HEADER == "Code rejected your output. Fix these errors and send the whole JSON again:"
    assert note.startswith(CORRECTION_HEADER)
    assert note.splitlines()[-1] == "- output is not a JSON object"
    assert log.rejections == [("output is not a JSON object",)]
    assert review.review(output_text()) is None
    assert log.accepted == ()
    assert review.exhausted is LoopOutcome.INVALID_OUTPUT
