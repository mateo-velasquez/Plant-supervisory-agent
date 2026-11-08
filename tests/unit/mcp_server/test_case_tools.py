"""006 T9, T10: deviations, active cases and case tools through the in-process client (R8-R10, E12, E13)."""

import json

import pytest
from mcp_builders import StaticCases, frame_with, tool_context

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, all_combinations
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import FrameHolder, SnapshotFrame, ToolContext
from plant_monitor.mcp_server.server import build_server

from builders import case_with, history_row, measured

pytestmark = pytest.mark.anyio

CASE_ID = "S002-Sedán-Local"
SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)


def _e12_frame() -> SnapshotFrame:
    """E12 frame: Sedán x Local is 6 units behind; the other 8 combinations are all zero."""
    metrics: dict[Combination, CombinationMetrics] = {
        combo: measured(combo, 0.0, 0.0, 0.0, None, Severity.NONE, Severity.NONE)
        for combo in all_combinations()
    }
    metrics[SEDAN_LOCAL] = measured(
        SEDAN_LOCAL, -6.0, -25.0, 0.0, Stage.ASSEMBLY, Severity.HIGH, Severity.NONE
    ).model_copy(update={"progress": 10, "cumulative_plan": 16.0})
    return frame_with("S003", metrics)


def _e13_context() -> tuple[ToolContext, FrameHolder]:
    """E13 case 'S002-Sedán-Local' with its two history rows."""
    case = case_with(
        CASE_ID,
        CaseState.FOLLOW_UP,
        Severity.HIGH,
        Severity.HIGH,
        at="S003",
        reported=(CaseState.OPEN, Severity.MEDIUM, "S002"),
    )
    first = history_row(
        CASE_ID, "S002", Stage.ASSEMBLY, minimum=Severity.MEDIUM, state=CaseState.OPEN
    ).model_copy(update={"gap_units": -3.0, "gap_pct": -12.5})
    second = history_row(CASE_ID, "S003", Stage.ASSEMBLY, minimum=Severity.HIGH).model_copy(
        update={"gap_units": -6.0, "gap_pct": -25.0}
    )
    return tool_context(cases=StaticCases([case], {CASE_ID: (first, second)}))


async def test_e12_deviations_lists_nine_rows_with_the_active_case() -> None:
    """E12: nine rows in combination order; the first carries the case and the code's values."""
    ctx, frames = _e13_context()
    with frames.entered(_e12_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_deviations", {})
    assert not outcome.is_error
    first = (
        '{"modelo":"Sedán","mercado":"Local","case_id":"S002-Sedán-Local","avance":10,"plan_acumulado":16.0,'
        '"gap_unidades":-6.0,"gap_pct":-25.0,"retraso_dias":0.0,"etapa_cuello":"montaje",'
        '"severidad_gap":"alta","severidad_retraso":"ninguna","severidad_minima":"alta"}'
    )
    assert outcome.text.startswith('{"snapshot_id":"S003","combinaciones":[' + first)
    rows = json.loads(outcome.text)["combinaciones"]
    assert len(rows) == 9
    assert [row["case_id"] for row in rows[1:]] == [None] * 8


async def test_e13a_active_cases_use_the_report_row_shape() -> None:
    """E13a: 'get_active_cases' returns the active_rows of the current snapshot."""
    ctx, frames = _e13_context()
    with frames.entered(_e12_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_active_cases", {})
    assert outcome.text == (
        '{"snapshot_id":"S003","casos":[{"case_id":"S002-Sedán-Local","modelo":"Sedán","mercado":"Local",'
        '"gap_unidades":-6.0,"gap_pct":-25.0,"retraso_dias":0.0,"severidad":"alta","severidad_maxima":"alta",'
        '"estado":"en_seguimiento","etapa_cuello":"montaje"}]}'
    )


async def test_e13b_get_case_returns_state_last_report_and_history_newest_first() -> None:
    """E13b: one case with 'ultimo_informe' and history newest first."""
    ctx, frames = _e13_context()
    with frames.entered(_e12_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_case", {"case_id": CASE_ID})
    assert not outcome.is_error
    data = json.loads(outcome.text)
    assert data["abierto_en"] == "S002"
    assert data["estado"] == "en_seguimiento"
    assert data["severidad"] == "alta"
    assert data["subida_por_agente"] is False
    assert data["severidad_maxima"] == "alta"
    assert data["resuelto_en"] is None
    assert data["ultimo_informe"] == {"snapshot_id": "S002", "estado": "abierto", "severidad": "media"}
    assert [row["snapshot_id"] for row in data["historial"]] == ["S003", "S002"]
    assert data["historial"][1] == {
        "snapshot_id": "S002",
        "estado": "abierto",
        "severidad": "media",
        "severidad_minima": "media",
        "gap_unidades": -3.0,
        "gap_pct": -12.5,
        "retraso_dias": 0.0,
        "etapa_cuello": "montaje",
    }
    assert data["historial_omitido"] == 0


async def test_e13c_unknown_case_is_refused() -> None:
    """E13c: an unknown case id is a refusal with the full text."""
    ctx, frames = _e13_context()
    with frames.entered(_e12_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_case", {"case_id": "S001-SUV-Local"})
    assert outcome.is_error
    assert outcome.text == "Error executing tool get_case: unknown case S001-SUV-Local"


async def test_risk_deviations_over_budget_is_refused_not_cut() -> None:
    """Risk: a deviations view over the budget is silently truncated instead of refused (R12)."""
    ctx, frames = _e13_context()
    small = ToolContext(
        plant=ctx.plant,
        cases=ctx.cases,
        logbooks=ctx.logbooks,
        view_max_chars=200,
        logbook_max_chars=ctx.logbook_max_chars,
    )
    with frames.entered(_e12_frame()):
        async with ToolClient(build_server(small, frames)) as client:
            outcome = await client.call("get_deviations", {})
    assert outcome.is_error
    assert outcome.text.startswith("Error executing tool get_deviations: get_deviations output is ")
    assert outcome.text.endswith(" characters, over the budget of 200")
