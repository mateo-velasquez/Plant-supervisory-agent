"""Per-agent tool allowlists, the excluded judgment tools and the startup check (010 R2)."""

from collections.abc import Mapping, Sequence
from typing import Final

from plant_monitor.mcp_server.types import (
    APPLY_PROPOSAL,
    EMIT_ALERT,
    EMIT_SHIFT_REPORT,
    GET_ACTIVE_CASES,
    GET_CASE,
    GET_DELAYED_UNITS,
    GET_DEVIATIONS,
    GET_LOGBOOK,
    LIFT_SEVERITY_RAISE,
    LIST_AVAILABLE_LOGBOOKS,
    RAISE_SEVERITY,
    SET_CAUSE,
)
from plant_monitor.telemetry.trace import AgentName

COORDINATOR_TOOLS: Final[tuple[str, ...]] = (
    GET_DEVIATIONS,
    GET_ACTIVE_CASES,
    GET_CASE,
    GET_DELAYED_UNITS,
    APPLY_PROPOSAL,
    EMIT_ALERT,
    EMIT_SHIFT_REPORT,
)
INVESTIGATOR_TOOLS: Final[tuple[str, ...]] = (
    LIST_AVAILABLE_LOGBOOKS,
    GET_LOGBOOK,
    GET_CASE,
    GET_DELAYED_UNITS,
)
ALLOWLISTS: Final[Mapping[AgentName, tuple[str, ...]]] = {
    "investigator": INVESTIGATOR_TOOLS,
    "coordinator": COORDINATOR_TOOLS,
}
EXCLUDED: Final[frozenset[str]] = frozenset({SET_CAUSE, RAISE_SEVERITY, LIFT_SEVERITY_RAISE})


def check_allowlists(lists: Mapping[AgentName, Sequence[str]]) -> None:
    """Raise when any agent's list offers an excluded tool, naming them in list order."""
    for agent, names in lists.items():
        offered = [name for name in names if name in EXCLUDED]
        if offered:
            raise ValueError(f"allowlist of the {agent} offers excluded tools: {', '.join(offered)}")
