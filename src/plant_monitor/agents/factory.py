"""Builds the coordinator from settings; the prompt is packaged data (R15)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from importlib import resources
from typing import Final, Literal

from plant_monitor.agents.loop import Coordinator, LoopConfig, ToolPort
from plant_monitor.agents.model import ModelPort
from plant_monitor.config import Settings

# Copied as literals so 'agents' never imports 'mcp_server.server'; a test checks they match.
COORDINATOR_TOOLS: Final[tuple[str, ...]] = (
    "get_deviations",
    "get_active_cases",
    "get_case",
    "get_delayed_units",
    "apply_proposal",
    "emit_alert",
    "emit_shift_report",
)
INVESTIGATOR_TOOLS: Final[tuple[str, ...]] = (
    "list_available_logbooks",
    "get_logbook",
    "get_case",
    "get_delayed_units",
)


def load_prompt(name: Literal["coordinator", "investigator"] = "coordinator") -> str:
    """The named agent's prompt from the package data."""
    return resources.files("plant_monitor.agents").joinpath("prompts", f"{name}.md").read_text("utf-8")


def _config(settings: Settings, max_turns: int) -> LoopConfig:
    return LoopConfig(
        max_turns=max_turns,
        prompt_token_limit=settings.prompt_token_limit,
        max_tokens=settings.anthropic_max_tokens,
        effort=settings.anthropic_effort,
    )


def build_coordinator(
    settings: Settings,
    model: ModelPort,
    tools: Callable[[], AbstractAsyncContextManager[ToolPort]],
) -> Coordinator:
    """A coordinator with the packaged prompt and the loop limits from 'settings'."""
    config = _config(settings, settings.agent_max_turns)
    return Coordinator(model, tools, load_prompt(), COORDINATOR_TOOLS, config)


def build_investigator(
    settings: Settings,
    model: ModelPort,
    tools: Callable[[], AbstractAsyncContextManager[ToolPort]],
) -> Coordinator:
    """The read-only investigator: its own prompt, tools and turn cap."""
    config = _config(settings, settings.investigator_max_turns)
    return Coordinator(model, tools, load_prompt("investigator"), INVESTIGATOR_TOOLS, config)
