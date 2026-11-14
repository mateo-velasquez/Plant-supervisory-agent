"""010 T4: the text floor hook and the post-tool floor check (R5, R6, E8, E9)."""

import re

import pytest
from hook_builders import PL, SE, SL, FakeView, hook_notice, sa, sr, view_v

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import NoticeType
from plant_monitor.hooks.chain import FloorViolation, HookContext, ToolCall
from plant_monitor.hooks.floor import FloorCheck, TextFloorHook
from plant_monitor.mcp_server.types import ToolOutcome

CTX = HookContext("coordinator", 1, view_v())
BELOW_SL = f"texto for {SL} states severidad media: below notice severity (alta)"


@pytest.mark.parametrize(
    ("case_id", "texto", "expected"),
    [
        (SL, "Estado en seguimiento, severidad media, máxima crítica.", BELOW_SL),
        (SL, "severidad media → alta, máxima crítica.", None),
        (SL, "Pasó de severidad media a alta.", None),
        (
            SL,
            "Severidad máxima: alta.",
            f"texto for {SL} states severidad maxima alta: below notice severity (critica)",
        ),
        (SL, "A media mañana se detuvo pintura; severidad alta.", None),
        (SE, "SEVERIDAD CRITICA.", None),
    ],
    ids=["a-below", "b-arrow", "c-change-phrase", "d-maxima", "e-bare-word", "g-above-record"],
)
def test_e8_text_floor_over_a_report(case_id: str, texto: str, expected: str | None) -> None:
    """010 E8a-e, g: a stated level below the notice blocks; change phrases and bare words pass."""
    hook = TextFloorHook()
    assert hook.name == "floor"
    assert hook.check(sr((case_id, texto)), CTX) == expected


def test_e8f_text_floor_on_an_alert_names_the_notice_severity() -> None:
    """010 E8f: 'severidad alta' on the critical alert for PL is blocked."""
    reason = TextFloorHook().check(sa(PL, "Pickup × Local: severidad alta por bitácora."), CTX)  # noqa: RUF001 - spec E8f uses the real sign
    assert reason == f"texto for {PL} states severidad alta: below notice severity (critica)"


def _ok() -> ToolOutcome:
    return ToolOutcome("ok", False)


def test_e9_post_floor_passes_when_every_notice_meets_its_floor() -> None:
    """010 E9a: V satisfies its floors after 'apply_proposal'."""
    FloorCheck().verify(ToolCall("apply_proposal", {}), _ok(), CTX)


def test_e9b_post_floor_raises_when_a_notice_sits_below_its_floor() -> None:
    """010 E9b: nSL at 'media' with a floor of 'alta' is a floor violation."""
    ctx = HookContext("coordinator", 1, view_v(sl=Severity.MEDIUM))
    message = (
        "S010-informe_de_turno-S008-SUV-Local: severidad media is below the computed "
        "minimum alta after apply_proposal"
    )
    with pytest.raises(FloorViolation, match=re.escape(message)):
        FloorCheck().verify(ToolCall("apply_proposal", {}), _ok(), ctx)


def test_e9c_post_floor_acts_only_on_apply_proposal() -> None:
    """010 E9c: the same violating view passes after 'emit_alert'."""
    ctx = HookContext("coordinator", 1, view_v(sl=Severity.MEDIUM))
    FloorCheck().verify(ToolCall("emit_alert", {}), _ok(), ctx)


def test_e9d_post_floor_skips_a_case_outside_the_last_delta() -> None:
    """010 E9d: a news item for a case without a floor is not checked."""
    base = view_v()
    resolved = hook_notice(
        "S004-Sedán-Europa",
        NoticeType.SHIFT_REPORT,
        Severity.NONE,
        Severity.NONE,
        CaseState.RESOLVED,
        CauseCategory.UNDECLARED,
        Stage.QUALITY,
    )
    view = FakeView(
        base.alert_notices,
        (*base.news_notices, resolved),
        base.floor_levels,
        base.missing_ids,
    )
    FloorCheck().verify(ToolCall("apply_proposal", {}), _ok(), HookContext("coordinator", 1, view))
