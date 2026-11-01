"""Actual progress: distinct released units per combination (FR-05, criterio §1)."""

from collections.abc import Iterable

from plant_monitor.domain.models import Combination, ReleasedUnit, all_combinations


def count_progress(released: Iterable[ReleasedUnit]) -> dict[Combination, int]:
    """Each `unidad_id` counts once, in the combination of its first occurrence (Q-20, order-dependent)."""
    seen: dict[Combination, set[str]] = {combo: set() for combo in all_combinations()}
    counted: set[str] = set()
    for unit in released:
        if unit.unidad_id in counted:
            continue
        counted.add(unit.unidad_id)
        seen[Combination(modelo=unit.modelo, mercado=unit.mercado)].add(unit.unidad_id)
    return {combo: len(ids) for combo, ids in seen.items()}
