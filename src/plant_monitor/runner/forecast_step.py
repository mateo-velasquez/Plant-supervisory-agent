"""Forecast step of the snapshot pipeline: computes and saves the gap forecast, never failing the snapshot."""

import logging
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Protocol

from plant_monitor.domain.calendar import HeldOutPolicy, calendar_order
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import Combination, CombinationMetrics, ReleasedUnit, Shift
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.forecast import ForecastConfig, WindowBase, forecast_snapshot
from plant_monitor.metrics.progress import count_progress

__all__ = [
    "ForecastSink",
    "ForecastSource",
    "ForecastStep",
    "forecast_snapshot",
]  # the last is patched in tests

logger = logging.getLogger(__name__)


class ForecastSource(Protocol):
    """Reads the forecast needs; 'SqliteRegistry.forecasts' satisfies it."""

    def open_seq(self, snapshot_id: str) -> int: ...

    def released_through(self, seq: int) -> tuple[ReleasedUnit, ...]: ...

    def snapshot_at(self, seq: int) -> str: ...


class ForecastSink(Protocol):
    """Where forecast rows are saved, inside a savepoint."""

    def savepoint(self) -> AbstractContextManager[None]: ...

    def save(self, snapshot_id: str, rows: Sequence[ForecastRow]) -> None: ...


@dataclass(frozen=True)
class ForecastStep:
    """Computes and stores one snapshot's forecast; a failure is logged and leaves no rows (R9)."""

    config: ForecastConfig
    source: ForecastSource
    sink: ForecastSink
    calendar: tuple[Shift, ...]  # forecast calendar, fixed at wiring (R4)
    ctx: PlantContext

    @classmethod
    def build(
        cls,
        config: ForecastConfig,
        source: ForecastSource,
        sink: ForecastSink,
        ctx: PlantContext,
        policy: HeldOutPolicy,
    ) -> ForecastStep:
        """The forecast calendar is the plant's shifts without the refused ones."""
        kept = tuple(s for s in calendar_order(ctx.shifts) if s.turno_id not in policy.refused_shifts)
        return cls(config, source, sink, kept, ctx)

    def run(
        self,
        snapshot_id: str,
        metrics: Mapping[Combination, CombinationMetrics],
        raised: frozenset[Combination],
    ) -> None:
        """Forecast inside a savepoint; any exception rolls it back and is logged, not raised."""
        try:
            with self.sink.savepoint():
                self._compute_and_save(snapshot_id, metrics, raised)
        except Exception as exc:
            logger.warning("forecast skipped for %s (%s)", snapshot_id, type(exc).__name__)

    def _compute_and_save(
        self,
        sid: str,
        metrics: Mapping[Combination, CombinationMetrics],
        raised: frozenset[Combination],
    ) -> None:
        n = self.source.open_seq(sid)
        window = self.config.window
        base: WindowBase | None = None
        if n >= window:
            base = WindowBase(
                progress=count_progress(self.source.released_through(n - window)),
                first_snapshot_id=self.source.snapshot_at(n - window + 1),
            )
        rows = forecast_snapshot(
            snapshot_id=sid,
            seq=n,
            metrics=metrics,
            raised=raised,
            base=base,
            calendar=self.calendar,
            ctx=self.ctx,
            config=self.config,
        )
        self.sink.save(sid, rows)
