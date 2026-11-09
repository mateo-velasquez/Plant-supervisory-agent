"""008 T8: the three judgment tools through the in-process client (E5, E7, E20)."""

import json
from collections.abc import Mapping
from dataclasses import replace

import pytest
from incident_runs import EV_T05, EV_T06, F2, F3, F5, F6, PICKUP_ANY
from judgment_builders import (
    AC2,
    PB_CASE,
    PL_CASE,
    FakeJudgment,
    bare_frame,
    incident_tool_context,
    result_of,
)

from plant_monitor.agents.factory import COORDINATOR_TOOLS
from plant_monitor.domain.causes import Cause, CauseCategory, Evidence
from plant_monitor.domain.enums import Stage
from plant_monitor.domain.notices import notice_brief_item
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import SnapshotFrame
from plant_monitor.mcp_server.server import READ_TOOLS, WRITE_TOOLS, build_server

from notice_builders import alert_notice

pytestmark = pytest.mark.anyio

SE_CASE = "S005-SUV-Europa"
QUALITY_HOLD = "retencion_de_calidad"


def err(tool: str, message: str) -> str:
    """The text a refusal arrives with."""
    return f"Error executing tool {tool}: {message}"


async def call_in(frame: SnapshotFrame, name: str, arguments: Mapping[str, object]) -> tuple[str, bool]:
    """Call one coordinator tool inside 'frame'; return '(text, is_error)'."""
    ctx, frames = incident_tool_context()
    with frames.entered(frame):
        async with ToolClient(build_server(ctx, frames, tools=COORDINATOR_TOOLS)) as client:
            outcome = await client.call(name, arguments)
    return outcome.text, outcome.is_error


def cause_args(
    categoria: str = QUALITY_HOLD, bitacora: str = "T02", fragmento: str = F2
) -> dict[str, object]:
    """Arguments of 'set_cause' for SE@S005."""
    return {
        "case_id": SE_CASE,
        "categoria": categoria,
        "etapa": "calidad",
        "bitacora": bitacora,
        "fragmento": fragmento,
    }


def raise_args(
    bitacora: str = "T05", fragmento: str = F5, categoria: str = "parada_de_linea"
) -> dict[str, object]:
    """Arguments of 'raise_severity' for {Pickup, montaje, any market}."""
    return {
        "categoria": categoria,
        "etapa": "montaje",
        "modelo": "Pickup",
        "bitacora": bitacora,
        "fragmento": fragmento,
    }


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        pytest.param(
            cause_args(categoria="no_declarada"),
            "no_declarada cannot be set: it is the default when no logbook names a cause",
            id="a-no-declarada",
        ),
        pytest.param(
            cause_args(fragmento="se detuvo la auditoría"), "fragment not found in T02", id="b-fragment"
        ),
        pytest.param(
            cause_args(bitacora="T03", fragmento=F3),
            "logbook T03 is not available at S004: it closes at S006",
            id="c-not-readable",
        ),
        pytest.param(cause_args(bitacora="T09"), "unknown logbook T09", id="d-unknown-logbook"),
    ],
)
async def test_e5_set_cause_refusals_reach_no_writer(arguments: dict[str, object], message: str) -> None:
    """E5 (a)-(d): each refusal carries its full text and the writer is never called."""
    writer = FakeJudgment()
    frame = replace(bare_frame("S004"), causes=writer)
    assert await call_in(frame, "set_cause", arguments) == (err("set_cause", message), True)
    assert writer.calls == []


async def test_e5e_a_valid_set_cause_calls_the_writer_once_and_returns_its_result() -> None:
    """E5 (e): one call with the cause and the fragment as sent; the result is the fake's as JSON."""
    changed = alert_notice("S004", SE_CASE)
    writer = FakeJudgment(result_of(case_ids=(SE_CASE,), changed=(changed,), pending=("n-1", "n-2")))
    sent = F2.replace(" ", "  ", 1)
    text, is_error = await call_in(
        replace(bare_frame("S004"), causes=writer), "set_cause", cause_args(fragmento=sent)
    )
    assert not is_error
    assert writer.calls == [
        (
            "set_cause",
            SE_CASE,
            Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY),
            Evidence(bitacora="T02", fragmento=sent),
        )
    ]
    result = json.loads(text)
    assert set(result) == {"caso", "causa", "avisos", "pendientes"}
    assert result["caso"] == SE_CASE
    assert result["avisos"] == [json.loads(json.dumps(notice_brief_item(changed)))]
    assert result["pendientes"] == ["n-1", "n-2"]


async def test_e5f_a_frame_without_a_cause_writer_refuses_every_judgment_tool() -> None:
    """E5 (f): no writer on the frame is the same refusal for the three tools."""
    message = "no judgment is being recorded at this snapshot"
    frame = bare_frame("S010")
    lift = {"active_cause_id": AC2, "bitacora": "T06", "fragmento": F6}
    assert await call_in(frame, "set_cause", cause_args()) == (err("set_cause", message), True)
    assert await call_in(frame, "raise_severity", raise_args()) == (err("raise_severity", message), True)
    assert await call_in(frame, "lift_severity_raise", lift) == (err("lift_severity_raise", message), True)


async def test_e7_refusals_reach_no_writer() -> None:
    """E7 (a)-(c): raise and lift refusals carry their full text and the writer is never called."""
    writer = FakeJudgment()
    s010 = replace(bare_frame("S010"), raises=writer)
    s011 = replace(bare_frame("S011"), raises=writer)
    lift = {"active_cause_id": AC2, "bitacora": "T06", "fragmento": F6}
    assert await call_in(s010, "raise_severity", raise_args(categoria="no_declarada")) == (
        err("raise_severity", "no_declarada cannot be raised: a raise needs a cause a logbook names"),
        True,
    )
    assert await call_in(s010, "raise_severity", raise_args(fragmento="se detuvo la línea")) == (
        err("raise_severity", "fragment not found in T05"),
        True,
    )
    assert await call_in(s011, "lift_severity_raise", lift) == (
        err("lift_severity_raise", "logbook T06 is not available at S011: it closes at S012"),
        True,
    )
    assert writer.calls == []


async def test_e7d_a_raise_without_market_calls_the_writer_with_a_null_market_scope() -> None:
    """E7 (d): one call, scope 'mercado' None; the result keys are the R5 ones."""
    writer = FakeJudgment(result_of(case_ids=(PL_CASE, PB_CASE), active_cause_id=AC2))
    text, is_error = await call_in(replace(bare_frame("S010"), raises=writer), "raise_severity", raise_args())
    assert not is_error
    assert writer.calls == [("raise_severity", CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05)]
    result = json.loads(text)
    assert set(result) == {"causa_activa", "casos", "avisos", "pendientes"}
    assert (result["causa_activa"], result["casos"]) == (AC2, [PL_CASE, PB_CASE])


async def test_e20_tools_are_the_read_tools_then_the_five_write_tools_and_the_default_stays_six() -> None:
    """E20: the offered order, the constant equal to the server's names, six tools by default."""
    expected = ("set_cause", "raise_severity", "lift_severity_raise", "emit_alert", "emit_shift_report")
    assert expected == WRITE_TOOLS
    assert (*READ_TOOLS, *WRITE_TOOLS) == COORDINATOR_TOOLS
    ctx, frames = incident_tool_context()
    async with ToolClient(build_server(ctx, frames)) as client:
        assert [spec.name for spec in await client.list_tools()] == list(READ_TOOLS)
    async with ToolClient(build_server(ctx, frames, tools=COORDINATOR_TOOLS)) as client:
        assert sorted(spec.name for spec in await client.list_tools()) == sorted(COORDINATOR_TOOLS)


async def test_risk_a_lift_passes_the_stripped_fragment_and_returns_its_keys() -> None:
    """Risk: a fragment sent with padding reaches the ledger unstripped and fails its later match."""
    writer = FakeJudgment(result_of(active_cause_id=AC2, lifted_at="S012"))
    arguments = {"active_cause_id": AC2, "bitacora": "T06", "fragmento": f"  {F6}\n"}
    text, is_error = await call_in(
        replace(bare_frame("S012"), raises=writer), "lift_severity_raise", arguments
    )
    assert not is_error
    assert writer.calls == [("lift", AC2, EV_T06)]
    assert json.loads(text) == {"causa_activa": AC2, "levantada_en": "S012", "avisos": [], "pendientes": []}


def test_risk_with_writer_wires_one_object_into_the_three_frame_slots() -> None:
    """Risk: a frame built with two different writers would split one snapshot's draft and ledger."""
    writer = FakeJudgment()
    base = bare_frame("S010")
    frame = SnapshotFrame.with_writer(base.snapshot_id, base.at, base.metrics, base.units, writer)
    slots: tuple[object, ...] = (frame.notices, frame.causes, frame.raises)
    assert all(slot is writer for slot in slots)
