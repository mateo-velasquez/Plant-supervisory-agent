"""008 T1: cited and active cause invariants (E1)."""

from typing import Any

import pytest

from plant_monitor.domain.causes import (
    ActiveCause,
    CauseCategory,
    CauseScope,
    CitedCause,
    Evidence,
    active_cause_id_for,
)
from plant_monitor.domain.enums import Market, Model, Stage

F2 = "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
F4 = "La auditoría de homologación terminó a las 8:30"
T02_F2 = Evidence(bitacora="T02", fragmento=F2)
T04_F4 = Evidence(bitacora="T04", fragmento=F4)
SCOPE_SE = CauseScope(modelo=Model.SUV, etapa=Stage.QUALITY, mercado=Market.EUROPE)


def active_cause(**overrides: Any) -> ActiveCause:
    """AC1 of the incident fixture, with field overrides."""
    fields: dict[str, Any] = {
        "active_cause_id": "S004-causa-1",
        "categoria": CauseCategory.QUALITY_HOLD,
        "scope": SCOPE_SE,
        "opened_at": "S004",
        "opened_by": T02_F2,
    }
    return ActiveCause.model_validate(fields | overrides)


@pytest.mark.parametrize(
    "overrides",
    [{"categoria": "no_declarada"}, {"etapa": None}],
    ids=["no_declarada", "etapa_null"],
)
def test_e1a_cited_cause_rejects_undeclared_category_and_null_stage(overrides: dict[str, Any]) -> None:
    fields: dict[str, Any] = {
        "categoria": "retencion_de_calidad",
        "etapa": "calidad",
        "evidence": T02_F2,
        "set_at": "S005",
    }
    with pytest.raises(ValueError):
        CitedCause.model_validate(fields | overrides)


def test_e1b_lifted_at_without_lifted_by_is_rejected() -> None:
    with pytest.raises(ValueError):
        active_cause(lifted_at="S008")


def test_e1c_active_cause_is_in_force_until_lifted_and_null_market_scope_is_valid() -> None:
    cause = active_cause()
    lifted = active_cause(lifted_at="S008", lifted_by=T04_F4)
    any_market = CauseScope(modelo=Model.SUV, etapa=Stage.QUALITY, mercado=None)
    assert cause.in_force is True
    assert lifted.in_force is False
    assert any_market.describe() == "SUV in calidad, any market"
    assert SCOPE_SE.describe() == "SUV in calidad, Europa"
    assert active_cause_id_for("S010", 1) == "S010-causa-1"
