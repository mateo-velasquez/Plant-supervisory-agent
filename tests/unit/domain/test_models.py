"""T2: frozen domain models parsing the data contract fields."""

from datetime import datetime

import pytest
from pydantic import BaseModel, ValidationError

from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import (
    Combination,
    CombinationMetrics,
    PlanRow,
    ReleasedUnit,
    Shift,
    Shipment,
    Snapshot,
    StandardTime,
    Unit,
)

ALL_MODELS: list[type[BaseModel]] = [
    Unit,
    ReleasedUnit,
    Snapshot,
    PlanRow,
    StandardTime,
    Shipment,
    Shift,
    Combination,
    CombinationMetrics,
]


def unit_payload(**overrides: object) -> dict[str, object]:
    """Snapshot unit as it appears in Sxxx.json."""
    payload: dict[str, object] = {
        "unidad_id": "U1",
        "modelo": "Sedán",
        "mercado": "Local",
        "color": "Blanco",
        "etapa": "montaje",
        "ingreso_etapa": "2026-03-02T08:00",
        "retrabajos": 0,
        "embarque_asignado": "LOC-0302",
    }
    payload.update(overrides)
    return payload


def released_payload(**overrides: object) -> dict[str, object]:
    """Released unit as it appears in Sxxx.json liberadas."""
    payload: dict[str, object] = {
        "unidad_id": "U2",
        "modelo": "SUV",
        "mercado": "Brasil",
        "hora": "2026-03-02T06:21",
    }
    payload.update(overrides)
    return payload


def snapshot_payload() -> dict[str, object]:
    """Minimal snapshot with one unit and one release."""
    return {
        "snapshot_id": "S001",
        "timestamp": "2026-03-02T10:00",
        "turno": "T01",
        "unidades": [unit_payload()],
        "liberadas": [released_payload()],
    }


def combination(model: str = "Sedán", market: str = "Local") -> Combination:
    """Combination built from the contract's modelo/mercado keys."""
    return Combination.model_validate({"modelo": model, "mercado": market})


def metrics(
    *,
    gap_pct: float | None = -11.1,
    delay_days: float | None = 0.0,
    delay_beyond_horizon: bool = False,
    bottleneck: Stage | None = None,
    minimum_severity: Severity = Severity.NONE,
) -> CombinationMetrics:
    """CombinationMetrics with E1-like defaults."""
    return CombinationMetrics(
        combination=combination(),
        progress=2,
        cumulative_plan=6.0,
        gap_units=-4.0,
        gap_pct=gap_pct,
        delay_days=delay_days,
        delay_beyond_horizon=delay_beyond_horizon,
        bottleneck=bottleneck,
        gap_severity=Severity.NONE,
        delay_severity=Severity.NONE,
        minimum_severity=minimum_severity,
    )


@pytest.mark.parametrize("model_cls", ALL_MODELS, ids=lambda c: c.__name__)
def test_model_is_configured_frozen(model_cls: type[BaseModel]) -> None:
    assert model_cls.model_config.get("frozen") is True


def test_unit_parses_contract_fields() -> None:
    unit = Unit.model_validate(unit_payload())
    assert unit.unidad_id == "U1"
    assert unit.modelo is Model("Sedán")
    assert unit.mercado is Market("Local")
    assert unit.etapa is Stage.ASSEMBLY
    assert unit.ingreso_etapa == datetime(2026, 3, 2, 8, 0)
    assert unit.ingreso_etapa.tzinfo is None
    assert unit.retrabajos == 0
    assert unit.embarque_asignado == "LOC-0302"


def test_unit_is_frozen() -> None:
    unit = Unit.model_validate(unit_payload())
    with pytest.raises(ValidationError):
        setattr(unit, "etapa", Stage.QUALITY)  # noqa: B010


def test_unit_rejects_unknown_stage() -> None:
    with pytest.raises(ValidationError):
        Unit.model_validate(unit_payload(etapa="horno"))


def test_unit_rejects_unknown_model() -> None:
    with pytest.raises(ValidationError):
        Unit.model_validate(unit_payload(modelo="Coupe"))


def test_unit_rejects_unknown_market() -> None:
    with pytest.raises(ValidationError):
        Unit.model_validate(unit_payload(mercado="Chile"))


def test_unit_without_etapa_fails_naming_the_field() -> None:
    payload = unit_payload()
    del payload["etapa"]
    with pytest.raises(ValidationError, match="etapa"):
        Unit.model_validate(payload)


def test_released_unit_parses_contract_fields() -> None:
    released = ReleasedUnit.model_validate(released_payload())
    assert released.unidad_id == "U2"
    assert released.modelo is Model("SUV")
    assert released.mercado is Market("Brasil")
    assert released.hora == datetime(2026, 3, 2, 6, 21)


def test_released_unit_is_frozen() -> None:
    released = ReleasedUnit.model_validate(released_payload())
    with pytest.raises(ValidationError):
        setattr(released, "unidad_id", "U3")  # noqa: B010


def test_snapshot_parses_nested_units_and_releases() -> None:
    snapshot = Snapshot.model_validate(snapshot_payload())
    assert snapshot.snapshot_id == "S001"
    assert snapshot.timestamp == datetime(2026, 3, 2, 10, 0)
    assert snapshot.turno == "T01"
    assert len(snapshot.unidades) == 1
    assert isinstance(snapshot.unidades[0], Unit)
    assert len(snapshot.liberadas) == 1
    assert isinstance(snapshot.liberadas[0], ReleasedUnit)


def test_snapshot_is_frozen() -> None:
    snapshot = Snapshot.model_validate(snapshot_payload())
    with pytest.raises(ValidationError):
        setattr(snapshot, "snapshot_id", "S002")  # noqa: B010


def test_plan_row_parses_key_fields() -> None:
    row = PlanRow.model_validate(
        {"turno_id": "T01", "modelo": "Sedán", "mercado": "Local", "unidades_plan": 12}
    )
    assert row.turno_id == "T01"
    assert row.modelo is Model("Sedán")
    assert row.mercado is Market("Local")
    assert row.unidades_plan == 12


def test_plan_row_accepts_explicit_zero_plan() -> None:
    row = PlanRow.model_validate(
        {"turno_id": "T01", "modelo": "SUV", "mercado": "Europa", "unidades_plan": 0}
    )
    assert row.unidades_plan == 0


def test_plan_row_is_frozen() -> None:
    row = PlanRow.model_validate(
        {"turno_id": "T01", "modelo": "SUV", "mercado": "Europa", "unidades_plan": 8}
    )
    with pytest.raises(ValidationError):
        setattr(row, "unidades_plan", 9)  # noqa: B010


def test_standard_time_paint_has_rework_minutes() -> None:
    std = StandardTime.model_validate(
        {"modelo": "SUV", "etapa": "pintura", "minutos_estandar": 480, "minutos_retrabajo": 360}
    )
    assert std.modelo is Model("SUV")
    assert std.etapa is Stage.PAINT
    assert std.minutos_estandar == 480
    assert std.minutos_retrabajo == 360


def test_standard_time_rework_minutes_optional_outside_paint() -> None:
    std = StandardTime.model_validate(
        {"modelo": "SUV", "etapa": "montaje", "minutos_estandar": 660, "minutos_retrabajo": None}
    )
    assert std.minutos_retrabajo is None


def test_standard_time_is_frozen() -> None:
    std = StandardTime.model_validate(
        {"modelo": "Pickup", "etapa": "calidad", "minutos_estandar": 180, "minutos_retrabajo": None}
    )
    with pytest.raises(ValidationError):
        setattr(std, "minutos_estandar", 1)  # noqa: B010


def test_shipment_parses_key_fields() -> None:
    shipment = Shipment.model_validate(
        {
            "embarque_id": "BRA-0303",
            "mercado": "Brasil",
            "medio": "camion",
            "corte_en_patio": "2026-03-03T06:00",
            "salida": "2026-03-03T08:00",
        }
    )
    assert shipment.embarque_id == "BRA-0303"
    assert shipment.mercado is Market("Brasil")
    assert shipment.corte_en_patio == datetime(2026, 3, 3, 6, 0)
    assert shipment.salida == datetime(2026, 3, 3, 8, 0)


def test_shipment_is_frozen() -> None:
    shipment = Shipment.model_validate(
        {
            "embarque_id": "LOC-0302",
            "mercado": "Local",
            "medio": "camion",
            "corte_en_patio": "2026-03-02T14:00",
            "salida": "2026-03-02T16:00",
        }
    )
    with pytest.raises(ValidationError):
        setattr(shipment, "embarque_id", "LOC-0303")  # noqa: B010


def test_shift_parses_key_fields() -> None:
    shift = Shift.model_validate(
        {
            "turno_id": "T01",
            "inicio": "2026-03-02T06:00",
            "fin": "2026-03-02T14:00",
            "snapshot_medio": "S001",
            "snapshot_cierre": "S002",
        }
    )
    assert shift.turno_id == "T01"
    assert shift.inicio == datetime(2026, 3, 2, 6, 0)
    assert shift.fin == datetime(2026, 3, 2, 14, 0)
    assert shift.snapshot_medio == "S001"
    assert shift.snapshot_cierre == "S002"


def test_shift_is_frozen() -> None:
    shift = Shift.model_validate(
        {
            "turno_id": "T01",
            "inicio": "2026-03-02T06:00",
            "fin": "2026-03-02T14:00",
            "snapshot_medio": "S001",
            "snapshot_cierre": "S002",
        }
    )
    with pytest.raises(ValidationError):
        setattr(shift, "turno_id", "T02")  # noqa: B010


def test_combination_equal_values_are_equal_and_hash_alike() -> None:
    assert combination() == combination()
    assert hash(combination()) == hash(combination())
    assert combination("SUV", "Brasil") != combination("SUV", "Europa")


def test_combination_usable_as_dict_key() -> None:
    counts = {combination(): 1}
    counts[combination()] += 1
    assert counts == {combination(): 2}


def test_combination_rejects_unknown_model() -> None:
    with pytest.raises(ValidationError):
        combination(model="Coupe")


def test_combination_is_frozen() -> None:
    combo = combination()
    name = next(iter(Combination.model_fields))
    with pytest.raises(ValidationError):
        setattr(combo, name, combo)


def test_combination_metrics_key_fields() -> None:
    m = metrics()
    assert m.combination == combination()
    assert m.progress == 2
    assert m.cumulative_plan == 6.0
    assert m.gap_units == -4.0
    assert m.gap_pct == -11.1
    assert m.delay_days == 0.0
    assert m.delay_beyond_horizon is False
    assert m.bottleneck is None


def test_combination_metrics_accepts_fractional_cumulative_plan() -> None:
    m = CombinationMetrics(
        combination=combination(),
        progress=0,
        cumulative_plan=2.5,
        gap_units=-2.5,
        gap_pct=-16.7,
        delay_days=0.0,
        delay_beyond_horizon=False,
        bottleneck=None,
        gap_severity=Severity.NONE,
        delay_severity=Severity.NONE,
        minimum_severity=Severity.NONE,
    )
    assert m.cumulative_plan == 2.5


def test_combination_metrics_gap_pct_none_when_daily_plan_zero() -> None:
    assert metrics(gap_pct=None).gap_pct is None


def test_combination_metrics_delay_none_beyond_horizon() -> None:
    m = metrics(delay_days=None, delay_beyond_horizon=True)
    assert m.delay_days is None
    assert m.delay_beyond_horizon is True


def test_combination_metrics_bottleneck_stage() -> None:
    assert metrics(bottleneck=Stage.ASSEMBLY).bottleneck is Stage.ASSEMBLY


def test_combination_metrics_is_frozen() -> None:
    m = metrics()
    with pytest.raises(ValidationError):
        setattr(m, "progress", 3)  # noqa: B010


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        (Severity.NONE, False),
        (Severity.MEDIUM, True),
        (Severity.HIGH, True),
        (Severity.CRITICAL, True),
    ],
)
def test_has_deviation_iff_minimum_severity_at_least_media(severity: Severity, expected: bool) -> None:
    assert metrics(minimum_severity=severity).has_deviation is expected
