"""Output budgets for tool results: compact JSON and a refusal when over the limit (R12)."""

import json
from collections.abc import Callable

from pydantic import BaseModel

from plant_monitor.domain.errors import RejectedRequest


class OverBudget(RejectedRequest):
    """A tool output does not fit its character budget."""

    def __init__(self, tool: str, size: int, max_chars: int) -> None:
        super().__init__(f"{tool} output is {size} characters, over the budget of {max_chars}")


def to_text(view: BaseModel) -> str:
    """Compact JSON of 'view', non-ASCII kept as is (R12)."""
    return json.dumps(view.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def fit_list(
    full: BaseModel, rebuild: Callable[[int | None], BaseModel], total: int, tool: str, max_chars: int
) -> str:
    """'full' view if it fits, else the view keeping the most leading items that fit (R12)."""
    text = to_text(full)
    kept = total - 1
    while len(text) > max_chars and kept >= 0:
        text = to_text(rebuild(kept))
        kept -= 1
    if len(text) > max_chars:
        raise OverBudget(tool, len(text), max_chars)
    return text


def check_budget(text: str, tool: str, max_chars: int) -> str:
    """'text' unchanged if it fits in 'max_chars'; OverBudget otherwise."""
    if len(text) > max_chars:
        raise OverBudget(tool, len(text), max_chars)
    return text
