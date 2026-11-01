"""Delayed units and the bottleneck stage (FR-10, Q-03)."""

from collections import Counter
from collections.abc import Iterable
from datetime import datetime, timedelta

from plant_monitor.domain.enums import PRODUCTION_STAGES, Stage
from plant_monitor.domain.models import Unit
from plant_monitor.metrics.tables import StandardsTable, is_repainting


def is_delayed(unit: Unit, at: datetime, standards: StandardsTable, tolerance: int) -> bool:
    """Repainting, or longer in its production stage than standard plus `tolerance` minutes."""
    if unit.etapa not in PRODUCTION_STAGES:
        return False
    if is_repainting(unit):
        return True
    limit = timedelta(minutes=standards.minutes(unit.modelo, unit.etapa) + tolerance)
    return at - unit.ingreso_etapa > limit


def bottleneck_stage(
    units: Iterable[Unit], at: datetime, standards: StandardsTable, tolerance: int
) -> Stage | None:
    """Stage with the most delayed units; ties go to the most downstream stage (Q-03)."""
    counts = Counter(unit.etapa for unit in units if is_delayed(unit, at, standards, tolerance))
    if not counts:
        return None
    return max(counts, key=lambda stage: (counts[stage], stage.rank))
