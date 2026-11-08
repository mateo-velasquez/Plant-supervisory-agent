from decimal import Decimal

import pytest

from plant_monitor.telemetry.usage import PriceCard, Usage, cost_usd

CARD = PriceCard(
    input=Decimal("0.10"),
    cache_write_5m=Decimal("0.125"),
    cache_write_1h=Decimal("0.20"),
    cache_read=Decimal("0.01"),
    output=Decimal("0.50"),
    long_context_threshold=100_000,
    long_context_multiplier=Decimal(5),
)


def _usage(
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_5m_tokens: int = 0,
    cache_write_1h_tokens: int = 0,
) -> Usage:
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_5m_tokens=cache_write_5m_tokens,
        cache_write_1h_tokens=cache_write_1h_tokens,
    )


@pytest.mark.parametrize(
    ("usage", "expected"),
    [
        (_usage(input_tokens=4_000, output_tokens=600), "0.0007"),
        (_usage(input_tokens=99_000, cache_read_tokens=1_000), "0.00991"),
        (_usage(input_tokens=99_000, cache_read_tokens=1_001), "0.04955005"),
        (_usage(input_tokens=101_000, output_tokens=1_000), "0.053"),
        (_usage(cache_write_5m_tokens=2_000, cache_write_1h_tokens=1_000), "0.00045"),
    ],
    ids=["a_base", "b_prompt_100000", "c_prompt_100001_x5", "d_long_context", "e_cache_writes"],
)
def test_e17_cost_usd_is_exact_decimal(usage: Usage, expected: str) -> None:
    """E17 (a)-(e): exact cost with the long-context multiplier above 100,000."""
    assert cost_usd(usage, CARD) == Decimal(expected)
