"""Cause types of the output contract; values keep the data contract's Spanish spelling (ADR-0005)."""

from enum import StrEnum
from typing import Self

from pydantic import model_validator

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import FrozenModel


class CauseCategory(StrEnum):
    """Cause catalog of §6; values are the data contract's."""

    LINE_STOP = "parada_de_linea"
    MISSING_PARTS = "faltante_de_piezas"
    REWORK = "retrabajo"
    QUALITY_HOLD = "retencion_de_calidad"
    ABSENTEEISM = "ausentismo"
    UNDECLARED = "no_declarada"


class Cause(FrozenModel):
    """Category and stage of a cause; stage is None when the data show none (Q-17)."""

    categoria: CauseCategory
    etapa: Stage | None


class Evidence(FrozenModel):
    """A logbook citation: logbook id and verbatim fragment."""

    bitacora: str
    fragmento: str


class CauseScope(FrozenModel):
    """Model, stage and optional market a raise reaches; 'mercado' None means any market."""

    modelo: Model
    etapa: Stage
    mercado: Market | None

    def describe(self) -> str:
        market = "any market" if self.mercado is None else str(self.mercado)
        return f"{self.modelo} in {self.etapa}, {market}"


class CitedCause(FrozenModel):
    """A cause cited from a logbook for one case, with its stage."""

    categoria: CauseCategory
    etapa: Stage
    evidence: Evidence
    set_at: str
    active_cause_id: str | None = None

    @model_validator(mode="after")
    def _declared(self) -> Self:
        if self.categoria is CauseCategory.UNDECLARED:
            raise ValueError("a cited cause cannot be 'no_declarada'")
        return self

    @property
    def cause(self) -> Cause:
        return Cause(categoria=self.categoria, etapa=self.etapa)


class ActiveCause(FrozenModel):
    """A cause in force over a scope until a logbook lifts it."""

    active_cause_id: str
    categoria: CauseCategory
    scope: CauseScope
    opened_at: str
    opened_by: Evidence
    lifted_at: str | None = None
    lifted_by: Evidence | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.categoria is CauseCategory.UNDECLARED:
            raise ValueError("an active cause cannot be 'no_declarada'")
        if (self.lifted_at is None) != (self.lifted_by is None):
            raise ValueError("'lifted_at' and 'lifted_by' are set together or not at all")
        return self

    @property
    def in_force(self) -> bool:
        return self.lifted_at is None


def active_cause_id_for(snapshot_id: str, n: int) -> str:
    """Id of the n-th cause opened at a snapshot."""
    return f"{snapshot_id}-causa-{n}"
