"""'CaseFacts': what a case's notices need, with the Q-32 cause row; imports only 'domain'."""

from dataclasses import dataclass

from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.enums import Stage, is_deviation
from plant_monitor.domain.models import CombinationMetrics


@dataclass(frozen=True)
class CaseFacts:
    """A case with what its notices need: current metrics and the cause row of Q-32."""

    case: Case
    current: CombinationMetrics | None  # this snapshot's metrics; None for a case not evaluated at it
    cause_row: CaseHistoryRow  # the case's last history row with a deviation (Q-32)

    def __post_init__(self) -> None:
        case_id = self.case.case_id
        if self.cause_row.case_id != case_id:
            raise ValueError(f"{case_id}: cause row belongs to {self.cause_row.case_id}")
        if not is_deviation(self.cause_row.minimum_severity):
            raise ValueError(f"{case_id}: cause row at {self.cause_row.snapshot_id} has no deviation")
        if self.current is not None and self.current.combination != self.case.combination:
            raise ValueError(f"{case_id}: metrics are for another combination")

    @property
    def cause_stage(self) -> Stage | None:
        """Bottleneck of the cause row."""
        return self.cause_row.bottleneck

    @property
    def cause_gap_only(self) -> bool:
        """Known only when the cause row is this snapshot's; history rows keep no gap/delay severities."""
        current = self.current
        if current is None or self.cause_row.snapshot_id != self.case.last_snapshot_id:
            return False
        return is_deviation(current.gap_severity) and not is_deviation(current.delay_severity)
