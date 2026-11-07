"""Cumulative plan and gap % (FR-06, FR-07)."""

from collections.abc import Iterable, Sequence

from plant_monitor.domain.models import Combination, PlanRow, Shift, all_combinations

MID_SHIFT_SHARE = 0.5
"""The plan is spread evenly within a shift, so half is due at its mid snapshot."""
CLOSING_SHIFT_SHARE = 1.0
SHIFTS_PER_DAY = 3
"""Q-06: the daily plan is literally the current shift plan times 3."""
PERCENT = 100


# We provide: the plan rows, the shifts, the current shift, and whether the photo is the closing one.
def cumulative_plan(
    plan: Iterable[PlanRow], shifts: Sequence[Shift], shift_id: str, is_closing: bool
) -> dict[Combination, float]:
    """Full plan of every shift starting before 'shift_id', plus its mid or closing share."""
    ordered = [shift.turno_id for shift in sorted(shifts, key=lambda shift: shift.inicio)]
    if shift_id not in ordered:
        raise ValueError(f"shift {shift_id} is not in turnos.csv")
    previous = set(ordered[: ordered.index(shift_id)])
    current_share = CLOSING_SHIFT_SHARE if is_closing else MID_SHIFT_SHARE
    totals = dict.fromkeys(all_combinations(), 0.0)
    for row in plan:
        combo = Combination(modelo=row.modelo, mercado=row.mercado)
        if row.turno_id in previous:
            totals[combo] += row.unidades_plan
        elif row.turno_id == shift_id:
            totals[combo] += row.unidades_plan * current_share

    # It returns: for each of the 9 combinations, how many units should be included.
    return totals


# the gap in % terms
def gap_pct(gap_units: float, shift_plan: int) -> float | None:
    """Gap as % of the daily plan; None when the daily plan is 0 (Q-16)."""
    daily_plan = shift_plan * SHIFTS_PER_DAY
    if daily_plan == 0:
        return None
    return gap_units / daily_plan * PERCENT
