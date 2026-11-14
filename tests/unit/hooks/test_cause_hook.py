"""010 T13: the cause hook, and lenient hooks over malformed arguments (R7, E10, E13a-c)."""

import pytest
from hook_builders import PL, SE, sa, sr, view_v

from plant_monitor.hooks.cause import CauseHook
from plant_monitor.hooks.chain import HookChain, HookContext, ToolCall
from plant_monitor.hooks.floor import TextFloorHook
from plant_monitor.hooks.novelty import NoveltyHook

CTX = HookContext("coordinator", 1, view_v())
CHAIN = HookChain(pre=(NoveltyHook(), TextFloorHook(), CauseHook()))


@pytest.mark.parametrize(
    ("case_id", "texto", "expected"),
    [
        (PL, "Causa: parada de línea, etapa montaje (bitácora T05).", None),
        (
            PL,
            "Frenada por retrabajo en pintura.",
            f"texto for {PL} names cause retrabajo; its causa is parada_de_linea",
        ),
        (
            SE,
            "Causa no declarada; posible Retención de calidad.",
            f"texto for {SE} names cause retencion_de_calidad; its causa is no_declarada",
        ),
        (SE, "Causa no declarada, etapa calidad.", None),
        (
            SE,
            "posible faltante_de_piezas",
            f"texto for {SE} names cause faltante_de_piezas; its causa is no_declarada",
        ),
        (PL, "Paradas de línea y retrabajos previos.", None),
    ],
    ids=["a-matches", "b-other-cause", "c-undeclared", "d-stage-only", "e-underscore", "f-plurals-slip"],
)
def test_e10_cause_hook_blocks_a_named_cause_that_differs(
    case_id: str, texto: str, expected: str | None
) -> None:
    """010 E10a-f: naming a category other than the notice's 'causa' blocks (X1: plurals slip)."""
    hook = CauseHook()
    assert hook.name == "cause"
    assert hook.check(sr((case_id, texto)), CTX) == expected


def test_e10g_the_floor_reason_wins_over_the_cause_in_chain_order() -> None:
    """010 E10g: a text breaking floor and cause is blocked by the floor first."""
    block = CHAIN.pre_tool(sr((PL, "severidad alta; causa retrabajo")), CTX)
    assert block is not None
    assert block.hook == "floor"
    assert block.reason == f"texto for {PL} states severidad alta: below notice severity (critica)"


def test_x9_a_data_description_with_a_category_word_is_blocked() -> None:
    """010 X9: 'unidades en retrabajo' on a notice whose causa differs is blocked (Q-55)."""
    reason = CauseHook().check(sr((PL, "Hay unidades en retrabajo.")), CTX)
    assert reason == f"texto for {PL} names cause retrabajo; its causa is parada_de_linea"


@pytest.mark.parametrize(
    "call",
    [
        ToolCall("emit_alert", {"case_id": 5}),
        ToolCall("emit_shift_report", {"textos": "x"}),
        ToolCall("emit_shift_report", {"textos": [{"case_id": PL}]}),
    ],
    ids=["a-case-id-int", "b-textos-string", "c-item-without-texto"],
)
def test_e13abc_malformed_arguments_neither_block_nor_raise(call: ToolCall) -> None:
    """010 E13a-c: novelty, floor and cause skip malformed arguments (X4)."""
    assert CHAIN.pre_tool(call, CTX) is None


def test_risk_valid_alert_text_passes_the_whole_chain() -> None:
    """Risk (R5, R7): a chain that blocks a consistent alert text would stall every real emit."""
    assert CHAIN.pre_tool(sa(PL, "Pickup × Local: severidad crítica, parada de línea."), CTX) is None  # noqa: RUF001 - real sign
