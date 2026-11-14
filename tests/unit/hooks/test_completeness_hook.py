"""010 T6: the completeness hook refuses a stop while texts are missing (R8, E11)."""

import pytest
from hook_builders import view_v

from plant_monitor.agents.brief import render_reminder
from plant_monitor.hooks.chain import HookBlock, HookChain, HookContext, MissingView
from plant_monitor.hooks.completeness import CompletenessHook

MISSING = "S010-informe_de_turno-S005-SUV-Europa"
CHAIN = HookChain(stop=(CompletenessHook(render_reminder),))


def test_e11a_missing_texts_block_the_stop_with_the_reminder() -> None:
    """010 E11a: the block carries the 'render_reminder' text naming the ids."""
    ctx = HookContext("coordinator", 1, view_v(missing=(MISSING,)))
    assert CHAIN.on_stop("Listo.", ctx) == HookBlock(
        "completeness",
        f"Texts are still missing for these notice ids; write them with the write tools: {MISSING}",
    )


def test_e11b_nothing_missing_lets_the_stop_pass() -> None:
    """010 E11b: with no missing ids the stop passes."""
    assert CHAIN.on_stop("Listo.", HookContext("coordinator", 1, view_v())) is None


def test_e11c_completeness_without_a_view_raises_missing_view() -> None:
    """010 E11c: a stop check with no view is an internal error."""
    with pytest.raises(MissingView, match="hook completeness needs a snapshot view"):
        CHAIN.on_stop("Listo.", HookContext("coordinator", 1, None))
