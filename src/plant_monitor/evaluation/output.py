"""Run output: what a run emitted, in processing order (Q-33)."""

from collections import Counter
from collections.abc import Iterable
from typing import Self

from pydantic import model_validator

from plant_monitor.domain.models import FrozenModel
from plant_monitor.domain.notices import Notice, NoticeType, ShiftReport


class RunOutput(FrozenModel):
    """What a run emitted, in processing order (Q-33); one alert per notice_id, a case may repeat."""

    alerts: tuple[Notice, ...]
    reports: tuple[ShiftReport, ...]

    @model_validator(mode="after")
    def _check_items(self) -> Self:
        for alert in self.alerts:
            if alert.tipo is not NoticeType.ALERT:
                raise ValueError(f"{alert.notice_id}: an alert must be alerta_inmediata")
        if repeated := _repeated(alert.notice_id for alert in self.alerts):
            raise ValueError(f"duplicate alert {repeated[0]}")
        if repeated := _repeated(report.turno_id for report in self.reports):
            raise ValueError(f"duplicate report for {repeated[0]}")
        return self


def _repeated(ids: Iterable[str]) -> list[str]:
    """Ids that occur more than once, sorted."""
    return sorted(key for key, count in Counter(ids).items() if count > 1)
