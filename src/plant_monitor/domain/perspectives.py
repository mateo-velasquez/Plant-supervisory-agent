"""Per-case perspectives shown in the coordinator brief (009 R10); Spanish field names (ADR-0005)."""

from plant_monitor.domain.enums import Stage
from plant_monitor.domain.models import FrozenModel


class GapAtReport(FrozenModel):
    """The gap a case had at its last report."""

    snapshot_id: str
    unidades: float
    pct_plan_diario: float | None


class GapPerspective(FrozenModel):
    """The gap now and at the last report."""

    unidades: float
    pct_plan_diario: float | None
    en_ultimo_informe: GapAtReport | None


class ShipmentPerspective(FrozenModel):
    """Delayed units and the shipments of the unit that sets the combination's delay."""

    unidades_demoradas: int
    retraso_dias: float | None
    embarque_asignado: str | None
    embarque_alcanzable: str | None


class BottleneckPerspective(FrozenModel):
    """The combination's bottleneck stage."""

    etapa: Stage | None


class CasePerspective(FrozenModel):
    """Everything the coordinator sees about one required case."""

    case_id: str
    gap: GapPerspective
    embarque: ShipmentPerspective
    cuello: BottleneckPerspective
