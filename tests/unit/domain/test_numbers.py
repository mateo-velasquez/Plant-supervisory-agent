"""009 T12: display rounding shared by the views and the perspectives (R10)."""

import pytest

from plant_monitor.domain.numbers import DECIMALS, round_display, round_optional


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-13.3333, -13.3), (0.04, 0.0), (None, None)],
)
def test_risk_rounding_keeps_one_decimal_and_passes_none_through(
    value: float | None, expected: float | None
) -> None:
    """Risk: a drifting helper changes the 006 view numbers or turns a missing gap into a number."""
    assert DECIMALS == 1
    assert round_optional(value) == expected
    if value is not None:
        assert round_display(value) == expected
