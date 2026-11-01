"""T7: projected yard arrival, reachable shipment and delay in days (FR-08, FR-09, Q-04, Q-09)."""

from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import Unit
from plant_monitor.ingestion.plant import load_shipments, load_standards
from plant_monitor.metrics.delay import (
    combination_delay,
    projected_yard_arrival,
    reachable_shipment,
    unit_delay_days,
)
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"


def dt(text: str) -> datetime:
    """Naive plant-local datetime from ISO text."""
    return datetime.fromisoformat(text)


def unit(
    stage: Stage,
    since: str,
    *,
    model: Model = Model.SUV,
    market: Market = Market.BRAZIL,
    rework: int = 0,
    shipment: str = "BRA-0303",
    unit_id: str = "U00001",
) -> Unit:
    """Snapshot unit varying only the fields the delay reads."""
    return Unit(
        unidad_id=unit_id,
        modelo=model,
        mercado=market,
        color="Gris Plata",
        etapa=stage,
        ingreso_etapa=dt(since),
        retrabajos=rework,
        embarque_asignado=shipment,
    )


@pytest.fixture
def standards() -> StandardsTable:
    """Fixture tiempos_estandar.csv as a lookup table."""
    return StandardsTable.from_rows(load_standards(FIXTURES / "tiempos_estandar.csv"))


@pytest.fixture
def shipments() -> ShipmentsTable:
    """Fixture embarques.csv as a lookup table; Brasil ends at BRA-0304."""
    return ShipmentsTable.from_rows(load_shipments(FIXTURES / "embarques.csv"))


E4_AT = "2026-03-02T10:00"
E13_AT = "2026-03-03T09:00"


def e4_unit() -> Unit:
    """Sedán/Local in montaje since 08:00, assigned LOC-0302."""
    return unit(
        Stage.ASSEMBLY, "2026-03-02T08:00", model=Model.SEDAN, market=Market.LOCAL, shipment="LOC-0302"
    )


def e5_unit(rework: int = 1, shipment: str = "BRA-0303", unit_id: str = "U00001") -> Unit:
    """SUV/Brasil in pintura since 09:00, assigned BRA-0303."""
    return unit(Stage.PAINT, "2026-03-02T09:00", rework=rework, shipment=shipment, unit_id=unit_id)


def e13_unit(unit_id: str = "U00013") -> Unit:
    """SUV/Brasil in calidad since 03-03 09:00, assigned BRA-0303 (already departed)."""
    return unit(Stage.QUALITY, "2026-03-03T09:00", shipment="BRA-0303", unit_id=unit_id)


def e14_unit(unit_id: str = "U00014") -> Unit:
    """SUV/Brasil in pintura since 03-03 09:00 without rework, assigned BRA-0304."""
    return unit(Stage.PAINT, "2026-03-03T09:00", shipment="BRA-0304", unit_id=unit_id)


def e7_unit() -> Unit:
    """SUV/Europa in pintura since 03-04 09:00, assigned EUR-0305; projects to 03-05 07:00."""
    return unit(Stage.PAINT, "2026-03-04T09:00", market=Market.EUROPE, shipment="EUR-0305")


# Projected yard arrival


def test_e4_projection_adds_remaining_assembly_and_quality(standards: StandardsTable) -> None:
    assert projected_yard_arrival(e4_unit(), dt(E4_AT), standards) == dt("2026-03-02T21:00")


def test_e5_repainting_unit_uses_rework_standard(standards: StandardsTable) -> None:
    assert projected_yard_arrival(e5_unit(rework=1), dt(E4_AT), standards) == dt("2026-03-03T05:00")


def test_e6_painting_unit_without_rework_uses_paint_standard(standards: StandardsTable) -> None:
    assert projected_yard_arrival(e5_unit(rework=0), dt(E4_AT), standards) == dt("2026-03-03T07:00")


def test_e13_quality_unit_projects_remaining_quality_only(standards: StandardsTable) -> None:
    assert projected_yard_arrival(e13_unit(), dt(E13_AT), standards) == dt("2026-03-03T12:00")


def test_e14_painting_unit_projects_past_last_brazil_cut_off(standards: StandardsTable) -> None:
    assert projected_yard_arrival(e14_unit(), dt(E13_AT), standards) == dt("2026-03-04T07:00")


def test_body_stage_sums_every_downstream_standard(standards: StandardsTable) -> None:
    body = unit(Stage.BODY, E4_AT, model=Model.SEDAN, market=Market.LOCAL, shipment="LOC-0303")
    assert projected_yard_arrival(body, dt(E4_AT), standards) == dt("2026-03-03T13:00")


def test_remaining_time_floored_at_zero_when_over_standard(standards: StandardsTable) -> None:
    late = unit(
        Stage.QUALITY, "2026-03-02T05:00", model=Model.SEDAN, market=Market.LOCAL, shipment="LOC-0302"
    )
    assert projected_yard_arrival(late, dt(E4_AT), standards) == dt(E4_AT)


def test_rework_standard_applies_only_in_paint(standards: StandardsTable) -> None:
    assembly = unit(Stage.ASSEMBLY, E4_AT, rework=1)
    assert projected_yard_arrival(assembly, dt(E4_AT), standards) == dt("2026-03-03T00:00")


# Reachable shipment


def test_e5_projection_one_hour_before_cut_off_reaches_it(shipments: ShipmentsTable) -> None:
    reachable = reachable_shipment(Market.BRAZIL, dt("2026-03-03T05:00"), shipments)
    assert reachable is not None
    assert reachable.embarque_id == "BRA-0303"


def test_arrival_exactly_at_cut_off_misses_it(shipments: ShipmentsTable) -> None:
    reachable = reachable_shipment(Market.BRAZIL, dt("2026-03-03T06:00"), shipments)
    assert reachable is not None
    assert reachable.embarque_id == "BRA-0304"


def test_e7_projection_after_europe_cut_off_reaches_next_week_ship(shipments: ShipmentsTable) -> None:
    reachable = reachable_shipment(Market.EUROPE, dt("2026-03-05T00:00"), shipments)
    assert reachable is not None
    assert reachable.embarque_id == "EUR-0312"


def test_reachable_shipment_only_considers_the_unit_market(shipments: ShipmentsTable) -> None:
    reachable = reachable_shipment(Market.LOCAL, dt("2026-03-02T21:00"), shipments)
    assert reachable is not None
    assert reachable.embarque_id == "LOC-0303"


@pytest.mark.parametrize("projected", ["2026-03-04T06:00", "2026-03-04T07:00"])
def test_no_shipment_after_last_cut_off_returns_none(shipments: ShipmentsTable, projected: str) -> None:
    assert reachable_shipment(Market.BRAZIL, dt(projected), shipments) is None


# Unit delay in days


def test_e4_missed_local_truck_costs_one_day(standards: StandardsTable, shipments: ShipmentsTable) -> None:
    assert unit_delay_days(e4_unit(), dt(E4_AT), standards, shipments) == 1.0


def test_e5_repainting_unit_still_reaches_assigned_truck(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    assert unit_delay_days(e5_unit(rework=1), dt(E4_AT), standards, shipments) == 0.0


def test_e6_unit_without_rework_misses_brazil_truck_by_one_day(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    assert unit_delay_days(e5_unit(rework=0), dt(E4_AT), standards, shipments) == 1.0


def test_e7_missed_europe_ship_costs_seven_days(standards: StandardsTable, shipments: ShipmentsTable) -> None:
    assert unit_delay_days(e7_unit(), dt("2026-03-04T09:00"), standards, shipments) == 7.0


def test_e13_assigned_truck_already_departed_costs_one_day(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    assert unit_delay_days(e13_unit(), dt(E13_AT), standards, shipments) == 1.0


def test_e14_no_reachable_shipment_gives_none(standards: StandardsTable, shipments: ShipmentsTable) -> None:
    assert unit_delay_days(e14_unit(), dt(E13_AT), standards, shipments) is None


def test_unit_arriving_exactly_at_cut_off_misses_its_truck(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    exact = unit(Stage.PAINT, E4_AT, rework=1, shipment="BRA-0303")
    assert projected_yard_arrival(exact, dt(E4_AT), standards) == dt("2026-03-03T06:00")
    assert unit_delay_days(exact, dt(E4_AT), standards, shipments) == 1.0


def test_q09_reaching_earlier_shipment_floors_delay_at_zero(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    early = e5_unit(rework=1, shipment="BRA-0304")
    assert unit_delay_days(early, dt(E4_AT), standards, shipments) == 0.0


# Combination delay


def test_e8_units_in_yard_and_dispatch_only_give_zero_delay(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    yard = unit(Stage.YARD, "2026-03-01T08:00", shipment="BRA-0302", unit_id="U1")
    dispatch = unit(Stage.DISPATCH, "2026-03-01T08:00", shipment="BRA-0302", unit_id="U2")
    assert combination_delay([yard, dispatch], dt(E4_AT), standards, shipments) == (0.0, False)


def test_no_units_give_zero_delay(standards: StandardsTable, shipments: ShipmentsTable) -> None:
    assert combination_delay([], dt(E4_AT), standards, shipments) == (0.0, False)


def test_combination_delay_is_max_over_units(standards: StandardsTable, shipments: ShipmentsTable) -> None:
    units = [e5_unit(rework=1, unit_id="U1"), e5_unit(rework=0, unit_id="U2")]
    assert combination_delay(units, dt(E4_AT), standards, shipments) == (1.0, False)


def test_yard_and_dispatch_units_excluded_from_max(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    yard = unit(Stage.YARD, "2026-03-01T08:00", shipment="BRA-0302", unit_id="U1")
    dispatch = unit(Stage.DISPATCH, "2026-03-01T08:00", shipment="BRA-0302", unit_id="U2")
    units = [yard, dispatch, e5_unit(rework=1, unit_id="U3")]
    assert combination_delay(units, dt(E4_AT), standards, shipments) == (0.0, False)


def test_e14_combination_beyond_horizon(standards: StandardsTable, shipments: ShipmentsTable) -> None:
    assert combination_delay([e14_unit()], dt(E13_AT), standards, shipments) == (None, True)


def test_e14b_worst_unit_beyond_horizon_dominates(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    units = [e13_unit(), e14_unit()]
    assert combination_delay(units, dt(E13_AT), standards, shipments) == (None, True)


# Error paths


@pytest.mark.parametrize("stage", [Stage.YARD, Stage.DISPATCH])
def test_projection_of_yard_or_dispatch_unit_raises(standards: StandardsTable, stage: Stage) -> None:
    with pytest.raises(ValueError, match="U00001"):
        projected_yard_arrival(unit(stage, "2026-03-01T08:00"), dt(E4_AT), standards)


@pytest.mark.parametrize("stage", [Stage.YARD, Stage.DISPATCH])
def test_unit_delay_of_yard_or_dispatch_unit_raises(
    standards: StandardsTable, shipments: ShipmentsTable, stage: Stage
) -> None:
    with pytest.raises(ValueError, match="U00001"):
        unit_delay_days(unit(stage, "2026-03-01T08:00"), dt(E4_AT), standards, shipments)


def test_unknown_assigned_shipment_raises_naming_unit_and_shipment(
    standards: StandardsTable, shipments: ShipmentsTable
) -> None:
    lost = e5_unit(shipment="BRA-9999", unit_id="U00042")
    with pytest.raises(ValueError) as excinfo:
        unit_delay_days(lost, dt(E4_AT), standards, shipments)
    assert "U00042" in str(excinfo.value)
    assert "BRA-9999" in str(excinfo.value)
