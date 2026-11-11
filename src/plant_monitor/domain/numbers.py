"""Display rounding shared by the views and the perspectives (006 R12, 009 R10)."""

from typing import Final

DECIMALS: Final = 1
"""Decimal places of every float shown to the model."""


def round_display(value: float) -> float:
    """'value' rounded to 'DECIMALS' places."""
    return round(value, DECIMALS)


def round_optional(value: float | None) -> float | None:
    """'value' rounded to 'DECIMALS' places, or None."""
    return None if value is None else round_display(value)
