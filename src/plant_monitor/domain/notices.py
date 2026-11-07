"""Notice and shift report contract (FR-25, FR-22); JSON keys keep the Spanish names (ADR-0005)."""

from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Self

from pydantic import model_validator

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, Evidence
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import FrozenModel


class NoticeType(StrEnum):
    """Notice types of the contract (FR-25, Q-14)."""

    ALERT = "alerta_inmediata"
    SHIFT_REPORT = "informe_de_turno"
    NO_NOTICE = "sin_aviso"


class Origin(StrEnum):
    """Who set the notice's severity: the thresholds or the agent."""

    THRESHOLD = "umbral"
    AGENT = "agente"


class Reason(StrEnum):
    """'motivo' values; declaration order is list order (Q-31)."""

    GAP = "gap"
    DELAY = "retraso"
    LOGBOOK = "bitacora"


def notice_id_for(snapshot_id: str, tipo: NoticeType, case_id: str) -> str:
    """'<snapshot_id>-<tipo>-<case_id>', e.g. 'S003-alerta_inmediata-S001-Sedán-Local'."""
    return f"{snapshot_id}-{tipo}-{case_id}"


def report_id_for(turno_id: str) -> str:
    """'<turno_id>-informe', e.g. 'T01-informe'."""
    return f"{turno_id}-informe"


class Notice(FrozenModel):
    """One per-case notice decision in the output contract (FR-25); never model_copy(update=...)."""

    notice_id: str
    snapshot_id: str
    case_id: str
    modelo: Model
    mercado: Market
    tipo: NoticeType
    severidad: Severity
    severidad_maxima: Severity
    estado: CaseState
    origen: Origin
    motivo: tuple[Reason, ...]
    causa: Cause
    evidencia: tuple[Evidence, ...]
    texto: str

    @model_validator(mode="after")
    def _check_contract(self) -> Self:
        expected_id = notice_id_for(self.snapshot_id, self.tipo, self.case_id)
        if self.notice_id != expected_id:
            raise ValueError(f"notice_id {self.notice_id} must be {expected_id}")
        ranks = [list(Reason).index(reason) for reason in self.motivo]
        if any(a >= b for a, b in pairwise(ranks)):
            raise ValueError(f"{self.notice_id}: motivo must be unique and ordered gap, retraso, bitacora")
        if (self.origen is Origin.AGENT) != (Reason.LOGBOOK in self.motivo):
            raise ValueError(f"{self.notice_id}: origen is agente exactly when motivo has bitacora")
        if bool(self.motivo) == (self.severidad is Severity.NONE):
            raise ValueError(f"{self.notice_id}: motivo must be empty exactly when severidad is ninguna")
        if self.severidad_maxima < self.severidad:
            raise ValueError(f"{self.notice_id}: severidad_maxima is below severidad")
        if self.tipo is NoticeType.ALERT and (
            self.estado is not CaseState.ESCALATED or self.severidad is not Severity.CRITICAL
        ):
            raise ValueError(f"{self.notice_id}: an alert is escalado and critica")
        return self


class ActiveCaseRow(FrozenModel):
    """One row of a report's 'casos_activos' (FR-23); values of the current snapshot."""

    case_id: str
    modelo: Model
    mercado: Market
    gap_unidades: float
    gap_pct: float | None
    retraso_dias: float | None
    severidad: Severity
    severidad_maxima: Severity
    estado: CaseState
    etapa_cuello: Stage | None

    @model_validator(mode="after")
    def _check_active(self) -> Self:
        if not self.estado.is_active:
            raise ValueError(f"{self.case_id}: a resolved case is never in casos_activos")
        return self


class ShiftReport(FrozenModel):
    """End-of-shift report (FR-22); its JSON is the contract spec 011 validates."""

    turno_id: str
    snapshot_id: str
    novedades: tuple[Notice, ...]
    casos_activos: tuple[ActiveCaseRow, ...]

    @model_validator(mode="after")
    def _check_items(self) -> Self:
        for news in self.novedades:
            if news.tipo is not NoticeType.SHIFT_REPORT or news.snapshot_id != self.snapshot_id:
                raise ValueError(
                    f"{news.notice_id}: a news item must be informe_de_turno of {self.snapshot_id}"
                )
        news_ids = [news.case_id for news in self.novedades]
        row_ids = [row.case_id for row in self.casos_activos]
        if len(set(news_ids)) != len(news_ids) or len(set(row_ids)) != len(row_ids):
            raise ValueError(f"{self.turno_id}: case_id must be unique within novedades and casos_activos")
        return self


@dataclass(frozen=True)
class PendingDelivery:
    """A stored notice waiting for delivery."""

    notice_id: str
    item: Notice | ShiftReport
