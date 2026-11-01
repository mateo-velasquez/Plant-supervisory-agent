"""T8: delayed units and the bottleneck stage (FR-10, Q-03)."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import Unit
from plant_monitor.ingestion.plant import load_standards
from plant_monitor.metrics.bottleneck import bottleneck_stage, is_delayed
from plant_monitor.metrics.tables import StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
AT = datetime(2026, 3, 2, 22, 0)


def unit(stage: Stage, minutes_in_stage: int, *, rework: int = 0, unit_id: str = "U00001") -> Unit:
    """SUV/Brasil unit that has spent the given minutes in its stage at AT."""
    return Unit(
        unidad_id=unit_id,
        modelo=Model.SUV,
        mercado=Market.BRAZIL,
        color="Gris Plata",
        etapa=stage,
        ingreso_etapa=AT - timedelta(minutes=minutes_in_stage),
        retrabajos=rework,
        embarque_asignado="BRA-0303",
    )


def delayed(stage: Stage, count: int, prefix: str) -> list[Unit]:
    """Units well past standard plus tolerance in a stage (SUV standards max 660)."""
    return [unit(stage, 2000, unit_id=f"{prefix}{i}") for i in range(count)]


@pytest.fixture
def standards() -> StandardsTable:
    """Fixture tiempos_estandar.csv as a lookup table."""
    return StandardsTable.from_rows(load_standards(FIXTURES / "tiempos_estandar.csv"))


@pytest.fixture
def tolerance() -> int:
    """Tolerance minutes from the fixture umbrales.yaml."""
    return load_thresholds(FIXTURES / "umbrales.yaml").demora.tolerancia_minutos


# is_delayed


def test_unit_over_standard_plus_tolerance_is_delayed(standards: StandardsTable, tolerance: int) -> None:
    assert is_delayed(unit(Stage.ASSEMBLY, 721), AT, standards, tolerance)


def test_boundary_standard_plus_tolerance_is_not_delayed(standards: StandardsTable, tolerance: int) -> None:
    assert not is_delayed(unit(Stage.ASSEMBLY, 660 + 60), AT, standards, tolerance)


def test_over_standard_within_tolerance_is_not_delayed(standards: StandardsTable, tolerance: int) -> None:
    assert not is_delayed(unit(Stage.ASSEMBLY, 700), AT, standards, tolerance)


def test_tolerance_comes_from_the_argument(standards: StandardsTable) -> None:
    assert is_delayed(unit(Stage.ASSEMBLY, 661), AT, standards, 0)
    assert not is_delayed(unit(Stage.ASSEMBLY, 661), AT, standards, 60)


def test_repainting_unit_with_zero_elapsed_is_delayed(standards: StandardsTable, tolerance: int) -> None:
    assert is_delayed(unit(Stage.PAINT, 0, rework=1), AT, standards, tolerance)


def test_painting_unit_without_rework_and_zero_elapsed_is_not_delayed(
    standards: StandardsTable, tolerance: int
) -> None:
    assert not is_delayed(unit(Stage.PAINT, 0), AT, standards, tolerance)


E16_AT = datetime(2026, 3, 3, 2, 0)
E16_FUTURE_ENTRY = datetime(2026, 3, 3, 3, 0)


def e16_unit(stage: Stage, *, rework: int = 0) -> Unit:
    """SUV/Brasil unit whose `ingreso_etapa` is one hour after the S005 timestamp (Q-19)."""
    return unit(stage, 0, rework=rework, unit_id="U00051").model_copy(
        update={"ingreso_etapa": E16_FUTURE_ENTRY}
    )


def test_e16_characterization_future_stage_entry_is_not_delayed(
    standards: StandardsTable, tolerance: int
) -> None:
    """Characterization: a negative elapsed already counts as not delayed."""
    assert not is_delayed(e16_unit(Stage.QUALITY), E16_AT, standards, tolerance)


def test_e16b_characterization_repainting_unit_with_future_entry_is_delayed(
    standards: StandardsTable, tolerance: int
) -> None:
    """Characterization: repainting stays delayed regardless of elapsed time."""
    assert is_delayed(e16_unit(Stage.PAINT, rework=1), E16_AT, standards, tolerance)


@pytest.mark.parametrize("stage", [Stage.YARD, Stage.DISPATCH])
def test_yard_and_dispatch_units_are_never_delayed(
    standards: StandardsTable, tolerance: int, stage: Stage
) -> None:
    assert not is_delayed(unit(stage, 10_000, rework=1), AT, standards, tolerance)


# bottleneck_stage


def test_e9_three_delayed_in_assembly_beat_one_repainting(standards: StandardsTable, tolerance: int) -> None:
    units = [*delayed(Stage.ASSEMBLY, 3, "M"), unit(Stage.PAINT, 30, rework=1, unit_id="P0")]
    assert bottleneck_stage(units, AT, standards, tolerance) is Stage.ASSEMBLY


def test_e16_tie_goes_to_most_downstream_stage(standards: StandardsTable, tolerance: int) -> None:
    paint = [unit(Stage.PAINT, 1, rework=1, unit_id="P0"), unit(Stage.PAINT, 600, unit_id="P1")]
    units = [*paint, *delayed(Stage.ASSEMBLY, 2, "M")]
    assert bottleneck_stage(units, AT, standards, tolerance) is Stage.ASSEMBLY


def test_tie_between_body_and_quality_goes_to_quality(standards: StandardsTable, tolerance: int) -> None:
    units = [*delayed(Stage.QUALITY, 1, "Q"), *delayed(Stage.BODY, 1, "B")]
    assert bottleneck_stage(units, AT, standards, tolerance) is Stage.QUALITY


def test_more_delayed_units_beat_a_downstream_stage(standards: StandardsTable, tolerance: int) -> None:
    units = [*delayed(Stage.PAINT, 2, "P"), *delayed(Stage.QUALITY, 1, "Q")]
    assert bottleneck_stage(units, AT, standards, tolerance) is Stage.PAINT


def test_only_delayed_units_count_toward_bottleneck(standards: StandardsTable, tolerance: int) -> None:
    on_time = [unit(Stage.QUALITY, 10, unit_id=f"Q{i}") for i in range(3)]
    units = [*on_time, *delayed(Stage.BODY, 1, "B")]
    assert bottleneck_stage(units, AT, standards, tolerance) is Stage.BODY


def test_no_delayed_units_gives_no_bottleneck(standards: StandardsTable, tolerance: int) -> None:
    units = [unit(Stage.ASSEMBLY, 100, unit_id="M0"), unit(Stage.PAINT, 100, unit_id="P0")]
    assert bottleneck_stage(units, AT, standards, tolerance) is None


def test_no_units_gives_no_bottleneck(standards: StandardsTable, tolerance: int) -> None:
    assert bottleneck_stage([], AT, standards, tolerance) is None


def test_yard_and_dispatch_never_become_bottleneck(standards: StandardsTable, tolerance: int) -> None:
    units = [unit(Stage.YARD, 10_000, unit_id="Y0"), unit(Stage.DISPATCH, 10_000, unit_id="D0")]
    assert bottleneck_stage(units, AT, standards, tolerance) is None
