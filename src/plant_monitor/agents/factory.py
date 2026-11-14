"""Builds the coordinator from settings; the prompt is packaged data (R15)."""

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from importlib import resources
from typing import Literal

from plant_monitor.agents.allowlists import ALLOWLISTS
from plant_monitor.agents.brief import render_reminder
from plant_monitor.agents.loop import Coordinator, LoopConfig, ToolPort
from plant_monitor.agents.model import ModelPort
from plant_monitor.agents.output import investigator_output_schema
from plant_monitor.agents.prefix import PrefixMonitor
from plant_monitor.config import Settings
from plant_monitor.hooks.cause import CauseHook
from plant_monitor.hooks.chain import HookChain
from plant_monitor.hooks.completeness import CompletenessHook
from plant_monitor.hooks.floor import FloorCheck, TextFloorHook
from plant_monitor.hooks.novelty import NoveltyHook
from plant_monitor.mcp_server.types import CRITERIA_PROMPT


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


def coordinator_hooks() -> HookChain:
    """The coordinator chain: novelty, floor, cause before; floor check after; completeness at stop."""
    return HookChain(
        pre=(NoveltyHook(), TextFloorHook(), CauseHook()),
        post=(FloorCheck(),),
        stop=(CompletenessHook(render_reminder),),
    )


def build_coordinator(
    settings: Settings,
    model: ModelPort,
    tools: Callable[[], AbstractAsyncContextManager[ToolPort]],
    *,
    hooks: HookChain,
) -> Coordinator:
    """A coordinator with the packaged prompt and the loop limits from 'settings'."""
    config = _config(settings, settings.agent_max_turns)
    return Coordinator(
        model,
        tools,
        load_prompt(),
        ALLOWLISTS["coordinator"],
        config,
        hooks=hooks,
        criteria_prompt=CRITERIA_PROMPT,
        prefix_monitor=PrefixMonitor(),
    )


def build_investigator(
    settings: Settings,
    model: ModelPort,
    tools: Callable[[], AbstractAsyncContextManager[ToolPort]],
) -> Coordinator:
    """The read-only investigator: its own prompt, tools and turn cap."""
    config = replace(
        _config(settings, settings.investigator_max_turns), max_notes=settings.investigator_output_corrections
    )
    return Coordinator(
        model,
        tools,
        load_prompt("investigator"),
        ALLOWLISTS["investigator"],
        config,
        agent="investigator",
        criteria_prompt=CRITERIA_PROMPT,
        output_schema=investigator_output_schema(),
        prefix_monitor=PrefixMonitor(),
    )
