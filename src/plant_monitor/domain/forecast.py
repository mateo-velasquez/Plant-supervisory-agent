"""Stored gap forecast rows (016 R8): a persisted contract, so a field added later needs a default."""

from __future__ import annotations

from typing import Literal

from pydantic import NaiveDatetime, PositiveInt, model_validator

from plant_monitor.domain.enums import Severity
from plant_monitor.domain.models import Combination, FrozenModel

type ForecastStatus = Literal["warm_up", "no_target", "suppressed", "no_crossing", "warning"]


class Thresholds3(FrozenModel):
    """Units behind that reach each gap level, positive."""

    media: float
    alta: float
    critica: float


class ForecastPoint(FrozenModel):
    snapshot_id: str
    scheduled_at: NaiveDatetime
    gap_units: float
    thresholds: Thresholds3 | None  # None when that shift's plan is 0


class ForecastBasis(FrozenModel):
    rate: float
    plan_per_snapshot: float | None
    window_first: str
    window_last: str
    points: PositiveInt  # W
    horizon: PositiveInt  # H


class ForecastWarning(FrozenModel):
    target_level: Severity
    crossing_snapshot_id: str
    crossing_at: NaiveDatetime
    hours: float


class ForecastRow(FrozenModel):
    seq: PositiveInt
    snapshot_id: str
    combination: Combination
    scheduled_at: NaiveDatetime
    gap_units: float
    gap_severity: Severity
    effective_severity: Severity
    status: ForecastStatus
    target_level: Severity | None
    thresholds: Thresholds3 | None
    points: tuple[ForecastPoint, ...]
    basis: ForecastBasis | None
    warning: ForecastWarning | None

    @model_validator(mode="after")
    def _consistent(self) -> ForecastRow:
        warm_up = self.status == "warm_up"
        if warm_up != (self.basis is None):
            raise ValueError("'basis' is None exactly when the status is 'warm_up'")
        if warm_up and self.points:
            raise ValueError("a 'warm_up' row has no points")
        if (self.warning is not None) != (self.status == "warning"):
            raise ValueError("'warning' is set exactly when the status is 'warning'")
        if (self.target_level is None) != (self.gap_severity is Severity.CRITICAL):
            raise ValueError("'target_level' is None exactly when the gap severity is 'critica'")
        if self.target_level is Severity.NONE:
            raise ValueError("'target_level' is never 'ninguna'")
        return self
