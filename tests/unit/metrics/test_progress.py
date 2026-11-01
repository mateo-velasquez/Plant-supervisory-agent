"""T5: count_progress counts distinct released units per combination (FR-05, §1)."""

from datetime import datetime

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import Combination, ReleasedUnit
from plant_monitor.metrics.progress import count_progress

SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_BRAZIL = Combination(modelo=Model.SUV, mercado=Market.BRAZIL)
ALL_COMBINATIONS = {Combination(modelo=m, mercado=k) for m in Model for k in Market}


def released(
    unit_id: str, model: Model = Model.SEDAN, market: Market = Market.LOCAL, hour: int = 7
) -> ReleasedUnit:
    """Released unit as listed in a snapshot's liberadas."""
    return ReleasedUnit(unidad_id=unit_id, modelo=model, mercado=market, hora=datetime(2026, 3, 2, hour, 0))


def test_e3_unit_released_in_two_snapshots_counted_once() -> None:
    s001 = [released("U1", hour=7)]
    s002 = [released("U1", hour=13)]
    assert count_progress([*s001, *s002])[SEDAN_LOCAL] == 1


def test_distinct_units_counted_per_combination() -> None:
    s001 = [released("U1"), released("U2")]
    s002 = [released("U2", hour=13), released("U3", hour=13)]
    assert count_progress([*s001, *s002])[SEDAN_LOCAL] == 3


def test_units_counted_only_in_their_own_combination() -> None:
    progress = count_progress(
        [released("U1"), released("U2", Model.SUV, Market.BRAZIL), released("U3", Model.SUV, Market.BRAZIL)]
    )
    assert progress[SEDAN_LOCAL] == 1
    assert progress[SUV_BRAZIL] == 2
    assert sum(progress.values()) == 3


def test_every_combination_present_with_zero_when_nothing_released() -> None:
    assert count_progress([]) == dict.fromkeys(ALL_COMBINATIONS, 0)


def test_combinations_without_releases_are_zero() -> None:
    progress = count_progress([released("U1")])
    assert set(progress) == ALL_COMBINATIONS
    assert all(count == 0 for combo, count in progress.items() if combo != SEDAN_LOCAL)
