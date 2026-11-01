"""T6: snapshot position in turnos.csv, cumulative plan and gap % of the daily plan (FR-04, FR-06, FR-07)."""

from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import Combination, PlanRow, Shift
from plant_monitor.ingestion.plant import load_plan, load_shifts
from plant_monitor.metrics.plan import cumulative_plan, gap_pct, snapshot_position

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_BRAZIL = Combination(modelo=Model.SUV, mercado=Market.BRAZIL)
SUV_EUROPE = Combination(modelo=Model.SUV, mercado=Market.EUROPE)
ALL_COMBINATIONS = {Combination(modelo=m, mercado=k) for m in Model for k in Market}


@pytest.fixture
def shifts() -> list[Shift]:
    """Fixture turnos.csv (T01 to T03)."""
    return load_shifts(FIXTURES / "turnos.csv")


@pytest.fixture
def plan(shifts: list[Shift]) -> list[PlanRow]:
    """Fixture plan_produccion.csv (Sedán/Local is 12 per shift)."""
    return load_plan(FIXTURES / "plan_produccion.csv", shifts)


def with_plan(plan: list[PlanRow], shift_id: str, combo: Combination, units: int) -> list[PlanRow]:
    """Copy of the plan with one shift and combination row changed."""
    return [
        row.model_copy(update={"unidades_plan": units})
        if (row.turno_id, row.modelo, row.mercado) == (shift_id, combo.modelo, combo.mercado)
        else row
        for row in plan
    ]


def test_s001_is_t01_mid_snapshot(shifts: list[Shift]) -> None:
    assert snapshot_position(shifts, "S001") == ("T01", False)


def test_s002_is_t01_closing_snapshot(shifts: list[Shift]) -> None:
    assert snapshot_position(shifts, "S002") == ("T01", True)


@pytest.mark.parametrize(
    ("snapshot_id", "expected"),
    [("S003", ("T02", False)), ("S004", ("T02", True)), ("S005", ("T03", False)), ("S006", ("T03", True))],
)
def test_snapshot_position_for_every_fixture_snapshot(
    shifts: list[Shift], snapshot_id: str, expected: tuple[str, bool]
) -> None:
    assert snapshot_position(shifts, snapshot_id) == expected


def test_e17_unknown_snapshot_raises_naming_it(shifts: list[Shift]) -> None:
    with pytest.raises(ValueError, match="S999"):
        snapshot_position(shifts, "S999")


def test_e1_mid_snapshot_takes_half_of_current_shift_plan(plan: list[PlanRow], shifts: list[Shift]) -> None:
    assert cumulative_plan(plan, shifts, "T01", False)[SEDAN_LOCAL] == 6.0


def test_closing_snapshot_takes_full_current_shift_plan(plan: list[PlanRow], shifts: list[Shift]) -> None:
    assert cumulative_plan(plan, shifts, "T01", True)[SEDAN_LOCAL] == 12.0


def test_previous_shifts_summed_in_full_at_mid(plan: list[PlanRow], shifts: list[Shift]) -> None:
    result = cumulative_plan(plan, shifts, "T02", False)
    assert result[SEDAN_LOCAL] == 18.0
    assert result[SUV_BRAZIL] == 9.0


def test_previous_shifts_summed_in_full_at_closing(plan: list[PlanRow], shifts: list[Shift]) -> None:
    result = cumulative_plan(plan, shifts, "T03", True)
    assert result[SEDAN_LOCAL] == 36.0
    assert result[SUV_BRAZIL] == 18.0


def test_fractional_half_of_odd_shift_plan(plan: list[PlanRow], shifts: list[Shift]) -> None:
    odd = with_plan(plan, "T01", SUV_EUROPE, 5)
    assert cumulative_plan(odd, shifts, "T01", False)[SUV_EUROPE] == 2.5


def test_every_combination_has_a_cumulative_plan(plan: list[PlanRow], shifts: list[Shift]) -> None:
    result = cumulative_plan(plan, shifts, "T01", False)
    assert set(result) == ALL_COMBINATIONS
    expected = {
        Combination(modelo=r.modelo, mercado=r.mercado): r.unidades_plan * 0.5
        for r in plan
        if r.turno_id == "T01"
    }
    assert result == expected


def test_e15_zero_current_shift_plan_keeps_previous_plan(plan: list[PlanRow], shifts: list[Shift]) -> None:
    zero = with_plan(with_plan(plan, "T01", SEDAN_LOCAL, 6), "T02", SEDAN_LOCAL, 0)
    assert cumulative_plan(zero, shifts, "T02", False)[SEDAN_LOCAL] == 6.0
    assert cumulative_plan(zero, shifts, "T02", True)[SEDAN_LOCAL] == 6.0


@pytest.mark.parametrize("is_closing", [False, True])
def test_cumulative_plan_for_unknown_shift_raises_naming_it(
    plan: list[PlanRow], shifts: list[Shift], is_closing: bool
) -> None:
    with pytest.raises(ValueError, match="T99"):
        cumulative_plan(plan, shifts, "T99", is_closing)


def test_e1_gap_pct_is_share_of_three_times_shift_plan() -> None:
    assert gap_pct(-4.0, 12) == pytest.approx(-4 / 36 * 100)


def test_gap_pct_positive_when_ahead_of_plan() -> None:
    assert gap_pct(3.0, 10) == pytest.approx(10.0)


def test_e15_gap_pct_is_none_when_shift_plan_is_zero() -> None:
    assert gap_pct(-6.0, 0) is None
