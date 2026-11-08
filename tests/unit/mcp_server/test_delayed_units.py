"""006 T11: 'get_delayed_units' through the in-process client (R11, E14)."""

import json
from datetime import datetime

import pytest
from mcp_builders import frame_with, tool_context

from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, Unit, all_combinations
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import SnapshotFrame
from plant_monitor.mcp_server.server import build_server

from builders import measured, unit_payload

pytestmark = pytest.mark.anyio


def _e14_frame() -> SnapshotFrame:
    """E14 frame S003 at 2026-03-02T18:00 with the four Sedán x Local units."""
    metrics: dict[Combination, CombinationMetrics] = {
        combo: measured(combo, 0.0, 0.0, 0.0, None, Severity.NONE, Severity.NONE)
        for combo in all_combinations()
    }
    sedan_local = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
    metrics[sedan_local] = measured(sedan_local, 0.0, 0.0, 0.0, Stage.ASSEMBLY, Severity.NONE, Severity.NONE)
    units = (
        Unit(**unit_payload(unidad_id="U1", etapa="montaje", ingreso_etapa="2026-03-02T06:00")),
        Unit(
            **unit_payload(
                unidad_id="U2",
                etapa="pintura",
                ingreso_etapa="2026-03-02T16:00",
                retrabajos=1,
                embarque_asignado="LOC-0303",
            )
        ),
        Unit(**unit_payload(unidad_id="U3", etapa="montaje", ingreso_etapa="2026-03-02T15:00")),
        Unit(**unit_payload(unidad_id="U4", etapa="patio", ingreso_etapa="2026-03-02T17:00")),
    )
    return frame_with("S003", metrics, units)


async def test_e14a_delayed_units_follow_fr10_with_rework_standard_and_shipments() -> None:
    """E14a: only FR-10 units, ordered, rework standard, reachable shipment, bottleneck montaje."""
    ctx, frames = tool_context()
    with frames.entered(_e14_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_delayed_units", {"modelo": "Sedán", "mercado": "Local"})
            deviations = await client.call("get_deviations", {})
    assert not outcome.is_error
    assert not deviations.is_error
    rows = json.loads(deviations.text)["combinaciones"]
    row = next(r for r in rows if (r["modelo"], r["mercado"]) == ("Sedán", "Local"))
    assert row["etapa_cuello"] == json.loads(outcome.text)["etapa_cuello"] == "montaje"
    assert json.loads(outcome.text) == {
        "snapshot_id": "S003",
        "modelo": "Sedán",
        "mercado": "Local",
        "etapa_cuello": "montaje",
        "unidades": [
            {
                "unidad_id": "U1",
                "etapa": "montaje",
                "minutos_en_etapa": 720,
                "minutos_estandar": 600,
                "repintado": False,
                "embarque_asignado": "LOC-0302",
                "embarque_alcanzable": "LOC-0303",
                "retraso_dias": 1.0,
            },
            {
                "unidad_id": "U2",
                "etapa": "pintura",
                "minutos_en_etapa": 120,
                "minutos_estandar": 360,
                "repintado": True,
                "embarque_asignado": "LOC-0303",
                "embarque_alcanzable": "LOC-0303",
                "retraso_dias": 0.0,
            },
        ],
        "omitidas": 0,
    }


async def test_r11_order_null_delay_first_then_minutes_over_then_unit_id() -> None:
    """R11, Q-04: beyond-horizon first; equal delays by minutes over standard desc, then 'unidad_id'."""
    metrics = {
        combo: measured(combo, 0.0, 0.0, 0.0, None, Severity.NONE, Severity.NONE)
        for combo in all_combinations()
    }

    def sedan_brasil(unit_id: str, stage: str, entered: str) -> Unit:
        """Sedán x Brasil unit assigned to 'BRA-0302'."""
        return Unit(
            **unit_payload(
                unidad_id=unit_id,
                mercado="Brasil",
                etapa=stage,
                ingreso_etapa=entered,
                embarque_asignado="BRA-0302",
            )
        )

    units = (
        sedan_brasil("U1", "calidad", "2026-03-03T10:00"),
        sedan_brasil("U2", "calidad", "2026-03-03T08:00"),
        sedan_brasil("U0", "calidad", "2026-03-03T10:00"),
        sedan_brasil("U9", "carroceria", "2026-03-03T00:00"),
    )
    frame = SnapshotFrame(snapshot_id="S004", at=datetime(2026, 3, 3, 20, 0), metrics=metrics, units=units)
    ctx, frames = tool_context()
    with frames.entered(frame):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_delayed_units", {"modelo": "Sedán", "mercado": "Brasil"})
    assert not outcome.is_error
    rows = json.loads(outcome.text)["unidades"]
    assert [(r["unidad_id"], r["retraso_dias"]) for r in rows] == [
        ("U9", None),
        ("U2", 2.0),
        ("U0", 2.0),
        ("U1", 2.0),
    ]


async def test_e14b_empty_combination_has_no_bottleneck_and_no_units() -> None:
    """E14b: a combination with no units gives a null stage and an empty list."""
    ctx, frames = tool_context()
    with frames.entered(_e14_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_delayed_units", {"modelo": "Pickup", "mercado": "Europa"})
    assert not outcome.is_error
    data = json.loads(outcome.text)
    assert data["etapa_cuello"] is None
    assert data["unidades"] == []


async def test_e14c_unknown_model_is_a_schema_error() -> None:
    """E14c: a model outside the contract enum is refused by the input schema."""
    ctx, frames = tool_context()
    with frames.entered(_e14_frame()):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_delayed_units", {"modelo": "Camión", "mercado": "Local"})
    assert outcome.is_error
