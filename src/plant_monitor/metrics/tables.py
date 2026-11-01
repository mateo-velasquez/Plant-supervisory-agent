"""Lookup tables over the standard times and the shipments, built once from the loader rows."""

from bisect import bisect_right
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import Shipment, StandardTime, Unit


def is_repainting(unit: Unit) -> bool:
    """§1: a unit in `pintura` with `retrabajos > 0` is being repainted."""
    return unit.etapa is Stage.PAINT and unit.retrabajos > 0


@dataclass(frozen=True)
class StandardsTable:
    """Standard minutes per model and stage, plus the paint rework standard per model."""

    _minutes: Mapping[tuple[Model, Stage], int]
    _rework: Mapping[Model, int]

    @classmethod
    def from_rows(cls, rows: Iterable[StandardTime]) -> StandardsTable:
        """Index `tiempos_estandar.csv` rows; rework minutes come from the `pintura` row."""
        minutes: dict[tuple[Model, Stage], int] = {}
        rework: dict[Model, int] = {}
        for row in rows:
            minutes[row.modelo, row.etapa] = row.minutos_estandar
            if row.etapa is Stage.PAINT and row.minutos_retrabajo is not None:
                rework[row.modelo] = row.minutos_retrabajo
        return cls(minutes, rework)

    def minutes(self, model: Model, stage: Stage) -> int:
        """Standard minutes of `stage` for `model`."""
        try:
            return self._minutes[model, stage]
        except KeyError:
            raise ValueError(f"no standard time for {model}/{stage} in tiempos_estandar.csv") from None

    def rework_minutes(self, model: Model) -> int:
        """Paint rework standard minutes for `model`."""
        try:
            return self._rework[model]
        except KeyError:
            raise ValueError(f"no minutos_retrabajo for {model}/pintura in tiempos_estandar.csv") from None

    def current_stage_minutes(self, unit: Unit) -> int:
        """Standard of the unit's current stage; the rework standard while repainting."""
        if is_repainting(unit):
            return self.rework_minutes(unit.modelo)
        return self.minutes(unit.modelo, unit.etapa)


@dataclass(frozen=True)
class ShipmentsTable:
    """Shipments indexed by id and, per market, sorted by `corte_en_patio`."""

    _by_market: Mapping[Market, tuple[Shipment, ...]]
    _cut_offs: Mapping[Market, tuple[datetime, ...]]
    _by_id: Mapping[str, Shipment]

    @classmethod
    def from_rows(cls, rows: Iterable[Shipment]) -> ShipmentsTable:
        """Index `embarques.csv` rows."""
        by_id = {row.embarque_id: row for row in rows}
        by_market = {
            market: tuple(
                sorted(
                    (s for s in by_id.values() if s.mercado is market),
                    key=lambda s: s.corte_en_patio,
                )
            )
            for market in Market
        }
        cut_offs = {market: tuple(s.corte_en_patio for s in group) for market, group in by_market.items()}
        return cls(by_market, cut_offs, by_id)

    def for_market(self, market: Market) -> tuple[Shipment, ...]:
        """Shipments of `market` sorted by cut-off."""
        return self._by_market[market]

    def by_id(self, embarque_id: str) -> Shipment:
        """Shipment with `embarque_id`; raises KeyError if unknown."""
        return self._by_id[embarque_id]

    def first_cut_off_after(self, market: Market, moment: datetime) -> Shipment | None:
        """First shipment of `market` whose cut-off is strictly after `moment`; None past the last."""
        index = bisect_right(self._cut_offs[market], moment)
        group = self._by_market[market]
        return group[index] if index < len(group) else None
