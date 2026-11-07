"""Cause types of the output contract; values keep the data contract's Spanish spelling (ADR-0005)."""

from enum import StrEnum

from plant_monitor.domain.enums import Stage
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
