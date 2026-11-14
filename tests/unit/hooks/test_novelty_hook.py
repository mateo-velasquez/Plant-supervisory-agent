"""010 T5: the novelty hook blocks emits for cases that are not news (R4, E7)."""

import pytest
from hook_builders import PL, SE, SEDAN_LOCAL, SL, sa, sr, view_v

from plant_monitor.hooks.chain import HookContext, MissingView, ToolCall
from plant_monitor.hooks.novelty import NoveltyHook

CTX = HookContext("coordinator", 1, view_v())


@pytest.mark.parametrize(
    ("call", "expected"),
    [
        (
            sr((PL, "t"), (SL, "t"), (SE, "t"), (SEDAN_LOCAL, "t")),
            f"{SEDAN_LOCAL}: no news since last report",
        ),
        (sa(SEDAN_LOCAL, "t"), f"{SEDAN_LOCAL}: no news since last report"),
        (sa(SL, "t"), None),
        (ToolCall("apply_proposal", {"propuesta": "S010-p1"}), None),
        (ToolCall("get_case", {"case_id": SEDAN_LOCAL}), None),
    ],
    ids=["a-report", "b-alert", "c-news-only-case", "d-apply", "d-get-case"],
)
def test_e7_novelty_blocks_the_first_case_without_news(call: ToolCall, expected: str | None) -> None:
    """010 E7a-d: a case outside alerts and news is blocked; other calls pass."""
    hook = NoveltyHook()
    assert hook.name == "novelty"
    assert hook.check(call, CTX) == expected


def test_e7e_novelty_without_a_view_raises_missing_view() -> None:
    """010 E7e: a novelty check with no view is an internal error."""
    with pytest.raises(MissingView, match="hook novelty needs a snapshot view"):
        NoveltyHook().check(sa(SEDAN_LOCAL, "t"), HookContext("coordinator", 1, None))
