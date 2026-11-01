"""T7 support: StandardsTable and ShipmentsTable lookups built from loader rows."""

from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import Shipment, StandardTime
from plant_monitor.ingestion.plant import load_shipments, load_standards
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"


@pytest.fixture
def shipment_rows() -> list[Shipment]:
    """Fixture embarques.csv rows."""
    return load_shipments(FIXTURES / "embarques.csv")


@pytest.fixture
def standards() -> StandardsTable:
    """Fixture tiempos_estandar.csv as a lookup table."""
    return StandardsTable.from_rows(load_standards(FIXTURES / "tiempos_estandar.csv"))


@pytest.mark.parametrize(
    ("model", "stage", "minutes"),
    [
        (Model.SEDAN, Stage.BODY, 360),
        (Model.SEDAN, Stage.ASSEMBLY, 600),
        (Model.SUV, Stage.PAINT, 480),
        (Model.SUV, Stage.ASSEMBLY, 660),
        (Model.PICKUP, Stage.ASSEMBLY, 540),
        (Model.PICKUP, Stage.QUALITY, 180),
    ],
)
def test_standard_minutes_per_model_and_stage(
    standards: StandardsTable, model: Model, stage: Stage, minutes: int
) -> None:
    assert standards.minutes(model, stage) == minutes


@pytest.mark.parametrize("model", list(Model))
def test_rework_minutes_come_from_paint_row(standards: StandardsTable, model: Model) -> None:
    assert standards.rework_minutes(model) == 360


def test_missing_standard_minutes_raise_naming_model_and_stage() -> None:
    partial = StandardsTable.from_rows(
        [StandardTime(modelo=Model.SUV, etapa=Stage.BODY, minutos_estandar=360)]
    )
    with pytest.raises(ValueError, match=r"SUV/montaje"):
        partial.minutes(Model.SUV, Stage.ASSEMBLY)


def test_missing_rework_minutes_raise_naming_model() -> None:
    no_rework = StandardsTable.from_rows(
        [StandardTime(modelo=Model.PICKUP, etapa=Stage.PAINT, minutos_estandar=480)]
    )
    with pytest.raises(ValueError, match="Pickup"):
        no_rework.rework_minutes(Model.PICKUP)


def test_rework_minutes_outside_paint_row_are_ignored() -> None:
    odd = StandardsTable.from_rows(
        [StandardTime(modelo=Model.SEDAN, etapa=Stage.ASSEMBLY, minutos_estandar=600, minutos_retrabajo=90)]
    )
    with pytest.raises(ValueError, match="Sedán"):
        odd.rework_minutes(Model.SEDAN)


def test_shipments_indexed_per_market_and_sorted_by_cut_off(shipment_rows: list[Shipment]) -> None:
    table = ShipmentsTable.from_rows(list(reversed(shipment_rows)))
    assert [s.embarque_id for s in table.for_market(Market.BRAZIL)] == ["BRA-0302", "BRA-0303", "BRA-0304"]
    assert [s.embarque_id for s in table.for_market(Market.EUROPE)] == ["EUR-0305", "EUR-0312"]
    local = table.for_market(Market.LOCAL)
    assert [s.corte_en_patio for s in local] == sorted(s.corte_en_patio for s in local)
    assert all(s.mercado is Market.LOCAL for s in local)


def test_shipment_looked_up_by_id(shipment_rows: list[Shipment]) -> None:
    table = ShipmentsTable.from_rows(shipment_rows)
    shipment = table.by_id("EUR-0305")
    assert shipment.salida == datetime(2026, 3, 5, 14, 0)
    assert shipment.corte_en_patio == datetime(2026, 3, 4, 20, 0)
