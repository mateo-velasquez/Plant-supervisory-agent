"""010 T1: the allowlist hook blocks tools outside the agent's list (R3, E5a)."""

import pytest

from plant_monitor.agents.allowlists import INVESTIGATOR_TOOLS
from plant_monitor.hooks.allowlist import AllowlistHook
from plant_monitor.hooks.chain import HookContext, ToolCall


@pytest.mark.parametrize(
    ("tool", "expected"),
    [
        ("emit_alert", "tool emit_alert is not allowed for the investigator"),
        ("set_cause", "tool set_cause is not allowed for the investigator"),
        ("apply_proposal", "tool apply_proposal is not allowed for the investigator"),
        ("get_logbook", None),
    ],
)
def test_e5a_allowlist_hook_blocks_tools_outside_the_investigator_list(
    tool: str, expected: str | None
) -> None:
    """010 E5a: three write tools are blocked with the R3 reason; 'get_logbook' passes."""
    hook = AllowlistHook("investigator", INVESTIGATOR_TOOLS)
    assert hook.name == "allowlist"
    assert hook.check(ToolCall(tool, {}), HookContext("investigator", 1, None)) == expected
