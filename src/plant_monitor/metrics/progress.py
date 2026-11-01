"""Actual progress: distinct released units per combination (FR-05, criterio §1)."""

from collections.abc import Iterable

from plant_monitor.domain.models import Combination, ReleasedUnit, all_combinations


def count_progress(released: Iterable[ReleasedUnit]) -> dict[Combination, int]:
    """Distinct `unidad_id` per combination over every release so far; all 9 combinations present."""
    seen: dict[Combination, set[str]] = {combo: set() for combo in all_combinations()}
    for unit in released:
        seen[Combination(modelo=unit.modelo, mercado=unit.mercado)].add(unit.unidad_id)
    return {combo: len(ids) for combo, ids in seen.items()}
