"""Frozen domain models; input fields keep the data contract's Spanish names (ADR-0005)."""

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, NaiveDatetime, NonNegativeInt

from plant_monitor.domain.enums import AnomalyKind, Market, Model, Severity, Stage


class FrozenModel(BaseModel):
    """Immutable base for every domain model."""

    model_config = ConfigDict(frozen=True)


class Unit(FrozenModel):
    """Unit in process, as listed in a snapshot's `unidades`."""

    unidad_id: str
    modelo: Model
    mercado: Market
    color: str
    etapa: Stage
    ingreso_etapa: NaiveDatetime
    retrabajos: NonNegativeInt
    embarque_asignado: str


class ReleasedUnit(FrozenModel):
    """Unit released from quality, as listed in a snapshot's `liberadas`."""

    unidad_id: str
    modelo: Model
    mercado: Market
    hora: NaiveDatetime


class Snapshot(FrozenModel):
    snapshot_id: str
    timestamp: NaiveDatetime
    turno: str
    unidades: tuple[Unit, ...]
    liberadas: tuple[ReleasedUnit, ...]


class PlanRow(FrozenModel):
    """Row of `plan_produccion.csv`."""

    turno_id: str
    modelo: Model
    mercado: Market
    unidades_plan: NonNegativeInt
    fecha: str | None = None
    turno: str | None = None


class StandardTime(FrozenModel):
    """Row of `tiempos_estandar.csv`; `minutos_retrabajo` only applies to `pintura`."""

    modelo: Model
    etapa: Stage
    minutos_estandar: NonNegativeInt
    minutos_retrabajo: NonNegativeInt | None = None


class Shipment(FrozenModel):
    """Row of `embarques.csv`."""

    embarque_id: str
    mercado: Market
    medio: str
    corte_en_patio: NaiveDatetime
    salida: NaiveDatetime


class Shift(FrozenModel):
    """Row of `turnos.csv`; `fecha` (M/D/YYYY) is kept raw and never used for time."""

    turno_id: str
    inicio: NaiveDatetime
    fin: NaiveDatetime
    snapshot_medio: str
    snapshot_cierre: str
    fecha: str | None = None
    turno: str | None = None


class Combination(FrozenModel):
    """Model and market key; hashable so it can index dicts."""

    modelo: Model
    mercado: Market


class Anomaly(FrozenModel):
    """Non-fatal data anomaly found while processing a snapshot."""

    kind: AnomalyKind
    snapshot_id: str
    detail: str


@dataclass(frozen=True)
class SnapshotCommit:
    """Everything the store records atomically when a snapshot's unit of work succeeds."""

    snapshot_id: str
    content_hash: str
    anomalies: tuple[Anomaly, ...]
    new_units: Mapping[str, Combination]


def all_combinations() -> tuple[Combination, ...]:
    """Every model and market combination."""
    return tuple(Combination(modelo=model, mercado=market) for model in Model for market in Market)


class CombinationMetrics(FrozenModel):
    """Deterministic metrics of one combination at one snapshot."""

    combination: Combination
    progress: NonNegativeInt
    cumulative_plan: float
    gap_units: float
    gap_pct: float | None
    delay_days: float | None
    delay_beyond_horizon: bool
    bottleneck: Stage | None
    gap_severity: Severity
    delay_severity: Severity
    minimum_severity: Severity

    @property
    def has_deviation(self) -> bool:
        """A deviation exists when the minimum severity is at least `media`."""
        return self.minimum_severity >= Severity.MEDIUM
