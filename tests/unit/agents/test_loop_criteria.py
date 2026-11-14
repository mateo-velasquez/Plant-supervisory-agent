"""010 T14: criteria composed into the system prompt (R11, R12, E18, X11)."""

import pytest
from agent_builders import FakeProgress, FakeTools, end, make_coordinator, tool

from plant_monitor.agents.factory import load_prompt
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import LoopLog, LoopOutcome

pytestmark = pytest.mark.anyio

COMPOSED = (
    "ROLE\n\n<criterios>\n# Criterio de prueba\n\n"
    "La severidad mínima es un piso: se puede subir, nunca bajar.\n</criterios>"
)


async def test_e18a_criteria_prompt_is_fetched_once_and_composed_into_every_request() -> None:
    """E18a: both requests carry the composed system; 'get_prompt' is called once."""
    tools = FakeTools(FakeProgress())
    model = FakeModel([tool("get_deviations", {}), end("Listo.")])
    coordinator = make_coordinator(model, tools, system="ROLE\n", criteria_prompt="criteria")
    outcome = await coordinator.run("S001", "brief", FakeProgress(), LoopLog())
    assert outcome is LoopOutcome.DONE
    assert [request.system for request in model.requests] == [COMPOSED, COMPOSED]
    assert tools.prompt_calls == ["criteria"]


async def test_e18b_without_criteria_prompt_the_system_is_the_role_and_nothing_is_fetched() -> None:
    """E18b: 'system' stays 'ROLE' with a trailing newline; no 'get_prompt' call."""
    tools = FakeTools(FakeProgress())
    model = FakeModel([tool("get_deviations", {}), end("Listo.")])
    coordinator = make_coordinator(model, tools, system="ROLE\n")
    await coordinator.run("S001", "brief", FakeProgress(), LoopLog())
    assert [request.system for request in model.requests] == ["ROLE\n", "ROLE\n"]
    assert tools.prompt_calls == []


def test_e18c_packaged_prompts_point_to_the_criterios_block() -> None:
    """E18c, R12: both packaged prompts mention the '<criterios>' block."""
    assert "<criterios>" in load_prompt("coordinator")
    assert "<criterios>" in load_prompt("investigator")
