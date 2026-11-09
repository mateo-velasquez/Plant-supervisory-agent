"""Builds the coordinator from settings; the prompt is packaged data (R15)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from importlib import resources
from typing import Final

from plant_monitor.agents.loop import Coordinator, LoopConfig, ToolPort
from plant_monitor.agents.model import ModelPort
from plant_monitor.config import Settings

# Copied as literals so 'agents' never imports 'mcp_server.server'; a test checks they match.
COORDINATOR_TOOLS: Final[tuple[str, ...]] = (
    "list_available_logbooks",
    "get_logbook",
    "get_deviations",
    "get_active_cases",
    "get_case",
    "get_delayed_units",
    "set_cause",
    "raise_severity",
    "lift_severity_raise",
    "emit_alert",
    "emit_shift_report",
)


def load_prompt() -> str:
    """Prompt v1 from the package data."""
    return resources.files("plant_monitor.agents").joinpath("prompts", "coordinator.md").read_text("utf-8")


def build_coordinator(
    settings: Settings,
    model: ModelPort,
    tools: Callable[[], AbstractAsyncContextManager[ToolPort]],
) -> Coordinator:
    """A coordinator with the packaged prompt and the loop limits from 'settings'."""
    config = LoopConfig(
        max_turns=settings.agent_max_turns,
        prompt_token_limit=settings.prompt_token_limit,
        max_tokens=settings.anthropic_max_tokens,
        effort=settings.anthropic_effort,
    )
    return Coordinator(model, tools, load_prompt(), COORDINATOR_TOOLS, config)
