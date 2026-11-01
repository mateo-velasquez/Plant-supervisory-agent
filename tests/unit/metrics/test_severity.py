"""T9: gap, delay and minimum severity read from the fixture umbrales.yaml (FR-11, §2, Q-07, Q-16)."""

from pathlib import Path

import pytest

from plant_monitor.domain.enums import Market, Severity
from plant_monitor.metrics.plan import gap_pct
from plant_monitor.metrics.severity import delay_severity, gap_severity, minimum_severity
from plant_monitor.metrics.thresholds import Thresholds, load_thresholds

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"

STRICTER_YAML = """\
gap:
  minimo_unidades: 5
  media: 15
  alta: 25
  critica: 40
retraso_dias:
  Local:  {media: 2, alta: 4, critica: 6}
  Brasil: {media: 1, alta: 2, critica: 5}
  Europa: {alta: 7, critica: 14}
demora:
  tolerancia_minutos: 60
resolucion:
  snapshots_sin_desvio: 2
"""


@pytest.fixture
def thresholds() -> Thresholds:
    """Fixture umbrales.yaml."""
    return load_thresholds(FIXTURES / "umbrales.yaml")


@pytest.fixture
def stricter(tmp_path: Path) -> Thresholds:
    """Thresholds with different values, to prove they are read rather than hard-coded."""
    path = tmp_path / "umbrales.yaml"
    path.write_text(STRICTER_YAML, encoding="utf-8")
    return load_thresholds(path)


# Gap severity


def test_e1_four_units_eleven_percent_behind_is_media(thresholds: Thresholds) -> None:
    assert gap_severity(-4.0, -4 / 36 * 100, thresholds) is Severity.MEDIUM


def test_e2_below_minimum_units_gives_no_gap_severity(thresholds: Thresholds) -> None:
    assert gap_severity(-2.0, -2 / 36 * 100, thresholds) is Severity.NONE


def test_minimum_units_gate_applies_even_with_high_pct(thresholds: Thresholds) -> None:
    assert gap_severity(-2.5, -50.0, thresholds) is Severity.NONE


def test_exactly_minimum_units_behind_passes_the_gate(thresholds: Thresholds) -> None:
    assert gap_severity(-3.0, -25.0, thresholds) is Severity.HIGH


def test_e12_exactly_ten_percent_behind_is_media_inclusive(thresholds: Thresholds) -> None:
    assert gap_severity(-3.6, -10.0, thresholds) is Severity.MEDIUM


def test_e12_three_behind_on_daily_plan_thirty_is_media_end_to_end(thresholds: Thresholds) -> None:
    assert gap_severity(-3.0, gap_pct(-3.0, 10), thresholds) is Severity.MEDIUM


@pytest.mark.parametrize(
    ("pct", "expected"),
    [
        (-9.99, Severity.NONE),
        (-19.99, Severity.MEDIUM),
        (-20.0, Severity.HIGH),
        (-34.99, Severity.HIGH),
        (-35.0, Severity.CRITICAL),
        (-80.0, Severity.CRITICAL),
    ],
)
def test_gap_levels_are_inclusive(thresholds: Thresholds, pct: float, expected: Severity) -> None:
    assert gap_severity(-10.0, pct, thresholds) is expected


def test_e15_gap_pct_none_gives_no_gap_severity(thresholds: Thresholds) -> None:
    assert gap_severity(-6.0, None, thresholds) is Severity.NONE


@pytest.mark.parametrize(("units", "pct"), [(5.0, 13.9), (0.0, 0.0), (36.0, 100.0)])
def test_ahead_or_on_plan_gives_no_gap_severity(thresholds: Thresholds, units: float, pct: float) -> None:
    assert gap_severity(units, pct, thresholds) is Severity.NONE


def test_gap_severity_reads_thresholds(stricter: Thresholds) -> None:
    assert gap_severity(-4.0, -11.1, stricter) is Severity.NONE
    assert gap_severity(-5.0, -14.99, stricter) is Severity.NONE
    assert gap_severity(-5.0, -15.0, stricter) is Severity.MEDIUM


# Delay severity


def test_e11_brazil_zero_delay_gives_no_delay_severity(thresholds: Thresholds) -> None:
    assert delay_severity(Market.BRAZIL, 0.0, False, thresholds) is Severity.NONE


def test_e13_brazil_one_day_is_alta(thresholds: Thresholds) -> None:
    assert delay_severity(Market.BRAZIL, 1.0, False, thresholds) is Severity.HIGH


def test_e14_beyond_horizon_is_critica(thresholds: Thresholds) -> None:
    assert delay_severity(Market.BRAZIL, None, True, thresholds) is Severity.CRITICAL


def test_e4_local_one_day_is_media(thresholds: Thresholds) -> None:
    assert delay_severity(Market.LOCAL, 1.0, False, thresholds) is Severity.MEDIUM


def test_e7_europe_seven_days_is_critica(thresholds: Thresholds) -> None:
    assert delay_severity(Market.EUROPE, 7.0, False, thresholds) is Severity.CRITICAL


@pytest.mark.parametrize(
    ("market", "days", "expected"),
    [
        (Market.LOCAL, 0.0, Severity.NONE),
        (Market.LOCAL, 0.99, Severity.NONE),
        (Market.LOCAL, 2.0, Severity.HIGH),
        (Market.LOCAL, 3.0, Severity.CRITICAL),
        (Market.BRAZIL, 0.99, Severity.NONE),
        (Market.BRAZIL, 2.0, Severity.HIGH),
        (Market.BRAZIL, 3.0, Severity.CRITICAL),
        (Market.EUROPE, 0.0, Severity.NONE),
        (Market.EUROPE, 1.0, Severity.HIGH),
        (Market.EUROPE, 3.0, Severity.CRITICAL),
    ],
)
def test_delay_levels_per_market_are_inclusive(
    thresholds: Thresholds, market: Market, days: float, expected: Severity
) -> None:
    assert delay_severity(market, days, False, thresholds) is expected


def test_delay_severity_reads_per_market_thresholds(stricter: Thresholds) -> None:
    assert delay_severity(Market.LOCAL, 1.0, False, stricter) is Severity.NONE
    assert delay_severity(Market.BRAZIL, 1.0, False, stricter) is Severity.MEDIUM
    assert delay_severity(Market.EUROPE, 7.0, False, stricter) is Severity.HIGH


def test_beyond_horizon_is_critica_whatever_the_thresholds(stricter: Thresholds) -> None:
    assert delay_severity(Market.EUROPE, None, True, stricter) is Severity.CRITICAL


def test_missing_delay_within_horizon_raises(thresholds: Thresholds) -> None:
    with pytest.raises(ValueError):
        delay_severity(Market.BRAZIL, None, False, thresholds)


@pytest.mark.parametrize("days", [0.0, 1.0, 7.0])
def test_known_delay_beyond_horizon_is_inconsistent_and_raises(thresholds: Thresholds, days: float) -> None:
    with pytest.raises(ValueError):
        delay_severity(Market.BRAZIL, days, True, thresholds)


# Minimum severity


def test_e10_minimum_is_max_of_gap_and_delay_and_a_deviation() -> None:
    result = minimum_severity(Severity.MEDIUM, Severity.HIGH)
    assert result is Severity.HIGH
    assert result >= Severity.MEDIUM


@pytest.mark.parametrize(
    ("gap", "delay", "expected"),
    [
        (Severity.NONE, Severity.NONE, Severity.NONE),
        (Severity.HIGH, Severity.MEDIUM, Severity.HIGH),
        (Severity.NONE, Severity.CRITICAL, Severity.CRITICAL),
        (Severity.CRITICAL, Severity.NONE, Severity.CRITICAL),
        (Severity.MEDIUM, Severity.MEDIUM, Severity.MEDIUM),
    ],
)
def test_minimum_severity_is_the_max(gap: Severity, delay: Severity, expected: Severity) -> None:
    assert minimum_severity(gap, delay) is expected


def test_no_gap_or_delay_severity_is_not_a_deviation() -> None:
    assert minimum_severity(Severity.NONE, Severity.NONE) < Severity.MEDIUM
