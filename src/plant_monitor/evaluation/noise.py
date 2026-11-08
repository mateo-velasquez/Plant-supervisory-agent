"""Noise re-derived from the run's reports and alerts, without golden data (005, ADR-0011, Q-33)."""

from collections import Counter
from dataclasses import dataclass
from itertools import pairwise

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.evaluation.output import RunOutput


@dataclass(frozen=True)
class RepeatedNews:
    """A news item that repeats the case's row of the previous report unchanged."""

    turno_id: str
    case_id: str
    previous_turno_id: str


@dataclass(frozen=True)
class NoiseScore:
    """Repeated news (gating) and duplicate alerts (reported only, already counted as 'duplicates')."""

    repeats: tuple[RepeatedNews, ...]
    duplicate_alerts: tuple[tuple[str, int], ...]

    @property
    def errors(self) -> int:
        """Number of repeats; duplicate alerts never gate here."""
        return len(self.repeats)


def count_noise(run: RunOutput) -> NoiseScore:
    """Repeats between consecutive reports and the alerts repeated per case, in run order."""
    repeats = tuple(
        RepeatedNews(current.turno_id, news.case_id, previous.turno_id)
        for previous, current in pairwise(run.reports)
        for news in current.novedades
        if _is_repeat(previous, news)
    )
    counts = Counter(alert.case_id for alert in run.alerts)
    duplicate_alerts = tuple((case_id, count) for case_id, count in counts.items() if count >= 2)
    return NoiseScore(repeats=repeats, duplicate_alerts=duplicate_alerts)


def _is_repeat(previous: ShiftReport, news: Notice) -> bool:
    """True when 'news' keeps its case's state and severity from 'previous' with no peak (§4 'Sin aviso')."""
    if news.estado is CaseState.RESOLVED:
        return False
    row = next((r for r in previous.casos_activos if r.case_id == news.case_id), None)
    return (
        row is not None
        and _norm(row.estado) is _norm(news.estado)
        and row.severidad == news.severidad
        and news.severidad_maxima == news.severidad
    )


def _norm(state: CaseState) -> CaseState:
    """'abierto' and 'en_seguimiento' are one state for noise; every other state is itself."""
    return CaseState.FOLLOW_UP if state is CaseState.OPEN else state
