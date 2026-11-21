"""016 T1: the 'ForecastRow' invariants that the dashboard relies on (R6, R8; I3)."""

from datetime import datetime
from typing import Any

import pytest

from plant_monitor.domain.enums import Market, Model, Severity
from plant_monitor.domain.forecast import (
    ForecastBasis,
    ForecastPoint,
    ForecastRow,
    ForecastWarning,
)
from plant_monitor.domain.models import Combination

AT = datetime(2026, 3, 2, 14, 0)
BASIS = ForecastBasis(
    rate=1.0, plan_per_snapshot=None, window_first="S001", window_last="S004", points=4, horizon=3
)
POINT = ForecastPoint(snapshot_id="S005", scheduled_at=AT, gap_units=0.0, thresholds=None)
WARNING = ForecastWarning(
    target_level=Severity.MEDIUM, crossing_snapshot_id="S005", crossing_at=AT, hours=4.0
)


def row(**overrides: Any) -> ForecastRow:
    """A valid 'no_crossing' row at gap severity 'ninguna', with 'overrides'."""
    fields: dict[str, Any] = {
        "seq": 4,
        "snapshot_id": "S004",
        "combination": Combination(modelo=Model.PICKUP, mercado=Market.LOCAL),
        "scheduled_at": AT,
        "gap_units": 0.0,
        "gap_severity": Severity.NONE,
        "effective_severity": Severity.NONE,
        "status": "no_crossing",
        "target_level": Severity.MEDIUM,
        "thresholds": None,
        "points": (POINT,),
        "basis": BASIS,
        "warning": None,
    }
    return ForecastRow(**{**fields, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"status": "warm_up", "points": ()}, id="warm_up_with_basis"),
        pytest.param({"status": "warm_up", "basis": None}, id="warm_up_with_points"),
        pytest.param({"basis": None}, id="basis_missing_outside_warm_up"),
        pytest.param({"status": "warning", "warning": None}, id="warning_status_without_warning"),
        pytest.param({"warning": WARNING}, id="warning_without_warning_status"),
        pytest.param({"target_level": None}, id="no_target_below_critical"),
        pytest.param({"gap_severity": Severity.CRITICAL}, id="target_with_critical_gap"),
        pytest.param({"target_level": Severity.NONE}, id="target_ninguna"),
    ],
)
def test_risk_inconsistent_rows_are_refused(overrides: dict[str, Any]) -> None:
    """Risk: a row that contradicts its status reaches the registry and the window explains it wrongly."""
    with pytest.raises(ValueError):
        row(**overrides)
