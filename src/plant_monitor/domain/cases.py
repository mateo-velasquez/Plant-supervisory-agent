"""Case types: lifecycle states, events, IDs, effective severity and the case models."""

from enum import StrEnum
from typing import Self

from pydantic import NonNegativeInt, computed_field, model_validator

from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.models import Combination, FrozenModel


class CaseState(StrEnum):
    """Case lifecycle states (§3); values are the data contract's."""

    OPEN = "abierto"
    FOLLOW_UP = "en_seguimiento"
    ESCALATED = "escalado"
    RESOLVED = "resuelto"

    @property
    def is_active(self) -> bool:
        """Every state but RESOLVED."""
        return self is not CaseState.RESOLVED


class CaseEvent(StrEnum):
    """What happened to a case at one snapshot; declaration order is emission order."""

    OPENED = "opened"
    ESCALATED = "escalated"
    SEVERITY_CHANGED = "severity_changed"
    RESOLVED = "resolved"


def effective_severity(minimum: Severity, raised: bool) -> Severity:
    """max(minimum, critica if raised); the only place this is computed (FR-15)."""
    return max(minimum, Severity.CRITICAL) if raised else minimum


def case_id_for(snapshot_id: str, combination: Combination) -> str:
    """`<snapshot_id>-<modelo>-<mercado>`, e.g. `S012-Pickup-Brasil`."""
    return f"{snapshot_id}-{combination.modelo}-{combination.mercado}"


class Case(FrozenModel):
    """One case as of its last evaluated snapshot."""

    case_id: str
    combination: Combination
    opened_at: str
    state: CaseState
    minimum_severity: Severity
    raised: bool
    max_severity_since_report: Severity | None
    clean_streak: NonNegativeInt
    last_snapshot_id: str
    last_reported_at: str | None = None
    last_reported_state: CaseState | None = None
    last_reported_severity: Severity | None = None
    resolved_at: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def current_severity(self) -> Severity:
        """Effective severity at the last evaluated snapshot (Q-26)."""
        return effective_severity(self.minimum_severity, self.raised)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        peak = self.max_severity_since_report
        if peak is not None and peak < self.current_severity:
            raise ValueError(f"{self.case_id}: max severity {peak} is below current {self.current_severity}")
        if peak is None and self.last_reported_at is None:
            raise ValueError(f"{self.case_id}: max severity is empty but the case was never reported")
        if (self.resolved_at is not None) != (self.state is CaseState.RESOLVED):
            raise ValueError(f"{self.case_id}: resolved_at must be set exactly when the state is resuelto")
        reported = (self.last_reported_at, self.last_reported_state, self.last_reported_severity)
        if any(v is None for v in reported) and any(v is not None for v in reported):
            raise ValueError(f"{self.case_id}: the last_reported fields must be all set or all None")
        return self


class CaseHistoryRow(FrozenModel):
    """A case evaluated at one snapshot."""

    case_id: str
    snapshot_id: str
    state: CaseState
    minimum_severity: Severity
    raised: bool
    gap_units: float
    gap_pct: float | None
    delay_days: float | None
    bottleneck: Stage | None
    clean_streak: NonNegativeInt

    @computed_field  # type: ignore[prop-decorator]
    @property
    def effective_severity(self) -> Severity:
        """Effective severity at this snapshot."""
        return effective_severity(self.minimum_severity, self.raised)
