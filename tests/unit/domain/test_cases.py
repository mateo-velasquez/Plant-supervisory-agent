"""003 T1: case states, events, IDs, effective severity and the Case / CaseHistoryRow models."""

import pytest
from pydantic import ValidationError

from plant_monitor.domain.cases import (
    Case,
    CaseEvent,
    CaseHistoryRow,
    CaseState,
    case_id_for,
    effective_severity,
)
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination

PICKUP_BRAZIL = Combination(modelo=Model.PICKUP, mercado=Market.BRAZIL)


def case_payload(**overrides: object) -> dict[str, object]:
    """A valid `abierto` case opened at S010, before any report."""
    payload: dict[str, object] = {
        "case_id": "S010-Pickup-Brasil",
        "combination": PICKUP_BRAZIL,
        "opened_at": "S010",
        "state": CaseState.OPEN,
        "minimum_severity": Severity.MEDIUM,
        "raised": False,
        "max_severity_since_report": Severity.MEDIUM,
        "clean_streak": 0,
        "last_snapshot_id": "S010",
    }
    payload.update(overrides)
    return payload


def row_payload(**overrides: object) -> dict[str, object]:
    """A valid history row for the S010 opening of `S010-Pickup-Brasil`."""
    payload: dict[str, object] = {
        "case_id": "S010-Pickup-Brasil",
        "snapshot_id": "S010",
        "state": CaseState.OPEN,
        "minimum_severity": Severity.MEDIUM,
        "raised": False,
        "gap_units": -4.0,
        "gap_pct": -13.3,
        "delay_days": 0.0,
        "bottleneck": Stage.ASSEMBLY,
        "clean_streak": 0,
    }
    payload.update(overrides)
    return payload


# --- States, events and IDs ---


def test_case_state_values_are_the_data_contract_values() -> None:
    assert [s.value for s in CaseState] == ["abierto", "en_seguimiento", "escalado", "resuelto"]


@pytest.mark.parametrize(
    ("state", "active"),
    [
        (CaseState.OPEN, True),
        (CaseState.FOLLOW_UP, True),
        (CaseState.ESCALATED, True),
        (CaseState.RESOLVED, False),
    ],
)
def test_case_state_is_active_for_every_state_but_resuelto(state: CaseState, active: bool) -> None:
    assert state.is_active is active


def test_case_event_values_follow_emission_order() -> None:
    assert [e.value for e in CaseEvent] == ["opened", "escalated", "severity_changed", "resolved"]


def test_case_id_for_joins_snapshot_model_and_market() -> None:
    assert case_id_for("S012", PICKUP_BRAZIL) == "S012-Pickup-Brasil"


def test_case_id_for_keeps_the_accent() -> None:
    sedan_local = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
    assert case_id_for("S006", sedan_local) == "S006-Sedán-Local"


# --- E6 · Effective severity ---


@pytest.mark.parametrize("raised", [False, True])
@pytest.mark.parametrize("minimum", list(Severity))
def test_e6_effective_severity_is_critica_when_raised_else_minimum(minimum: Severity, raised: bool) -> None:
    result = effective_severity(minimum, raised)
    assert result is (Severity.CRITICAL if raised else minimum)
    assert result >= minimum


def test_e6_case_and_row_derive_critica_from_media_raised() -> None:
    case = Case.model_validate(
        case_payload(raised=True, state=CaseState.ESCALATED, max_severity_since_report=Severity.CRITICAL)
    )
    row = CaseHistoryRow.model_validate(row_payload(raised=True, state=CaseState.ESCALATED))
    assert case.current_severity is Severity.CRITICAL
    assert row.effective_severity is Severity.CRITICAL


def test_derived_severities_are_computed_fields_not_inputs() -> None:
    assert "current_severity" not in Case.model_fields
    assert "current_severity" in Case.model_computed_fields
    assert "effective_severity" not in CaseHistoryRow.model_fields
    assert "effective_severity" in CaseHistoryRow.model_computed_fields


# --- Case validators ---


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"minimum_severity": Severity.HIGH}, id="max-below-current"),
        pytest.param({"raised": True, "state": CaseState.ESCALATED}, id="max-below-raised-current"),
        pytest.param({"max_severity_since_report": None}, id="max-none-without-report"),
        pytest.param({"resolved_at": "S010"}, id="resolved-at-without-resuelto"),
        pytest.param(
            {"state": CaseState.RESOLVED, "minimum_severity": Severity.NONE, "clean_streak": 2},
            id="resuelto-without-resolved-at",
        ),
        pytest.param({"last_reported_at": "S010"}, id="partial-last-reported-at"),
        pytest.param(
            {"last_reported_state": CaseState.OPEN, "last_reported_severity": Severity.MEDIUM},
            id="partial-last-reported-without-at",
        ),
    ],
)
def test_case_rejects_inconsistent_fields(overrides: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        Case.model_validate(case_payload(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param(
            {
                "max_severity_since_report": None,
                "last_reported_at": "S010",
                "last_reported_state": CaseState.OPEN,
                "last_reported_severity": Severity.MEDIUM,
            },
            id="reported-with-empty-max",
        ),
        pytest.param(
            {
                "state": CaseState.RESOLVED,
                "minimum_severity": Severity.NONE,
                "clean_streak": 2,
                "last_snapshot_id": "S012",
                "resolved_at": "S012",
            },
            id="resolved",
        ),
    ],
)
def test_case_accepts_consistent_report_and_resolution_fields(overrides: dict[str, object]) -> None:
    """Guards against validators so strict that a marked or resolved case cannot be built."""
    Case.model_validate(case_payload(**overrides))


# --- Frozen ---


def test_case_is_frozen() -> None:
    case = Case.model_validate(case_payload())
    with pytest.raises(ValidationError):
        setattr(case, "clean_streak", 1)  # noqa: B010


def test_case_history_row_is_frozen() -> None:
    row = CaseHistoryRow.model_validate(row_payload())
    with pytest.raises(ValidationError):
        setattr(row, "clean_streak", 1)  # noqa: B010
