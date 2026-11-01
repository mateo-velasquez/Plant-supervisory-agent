"""T1: domain enums with Spanish values and ordered severity."""

import pytest

from plant_monitor.domain.enums import Market, Model, Severity, Stage


def test_severity_values_are_spanish() -> None:
    assert [s.value for s in Severity] == ["ninguna", "media", "alta", "critica"]


def test_severity_members_by_name() -> None:
    assert Severity.NONE.value == "ninguna"
    assert Severity.MEDIUM.value == "media"
    assert Severity.HIGH.value == "alta"
    assert Severity.CRITICAL.value == "critica"


def test_severity_parses_from_value() -> None:
    assert Severity("critica") is Severity.CRITICAL


def test_severity_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        Severity("baja")


def test_severity_strict_order_none_medium_high_critical() -> None:
    assert Severity.NONE < Severity.MEDIUM < Severity.HIGH < Severity.CRITICAL


def test_severity_order_is_not_alphabetical() -> None:
    # Alphabetically "media" < "ninguna" and "alta" < "media"; the domain order must win.
    assert not Severity.MEDIUM < Severity.NONE
    assert not Severity.HIGH < Severity.MEDIUM
    assert Severity.CRITICAL > Severity.MEDIUM


def test_severity_non_strict_comparisons() -> None:
    assert Severity.MEDIUM >= Severity.MEDIUM
    assert Severity.MEDIUM <= Severity.MEDIUM
    assert Severity.HIGH >= Severity.MEDIUM
    assert Severity.NONE <= Severity.CRITICAL
    assert not Severity.MEDIUM >= Severity.HIGH


def test_severity_max_picks_most_severe() -> None:
    assert max([Severity.MEDIUM, Severity.HIGH]) is Severity.HIGH
    assert max([Severity.NONE, Severity.CRITICAL, Severity.MEDIUM]) is Severity.CRITICAL
    assert max(Severity.HIGH, Severity.NONE) is Severity.HIGH


def test_severity_min_picks_least_severe() -> None:
    assert min([Severity.CRITICAL, Severity.MEDIUM, Severity.HIGH]) is Severity.MEDIUM


def test_severity_sorted_follows_domain_order() -> None:
    shuffled = [Severity.HIGH, Severity.NONE, Severity.CRITICAL, Severity.MEDIUM]
    assert sorted(shuffled) == [Severity.NONE, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]


def test_severity_compares_with_valid_value_string_in_domain_order() -> None:
    assert Severity.MEDIUM < "alta"
    assert not Severity.HIGH < "media"
    assert Severity.HIGH > "media"
    assert not Severity.MEDIUM > "alta"


def test_severity_compared_with_non_string_raises_type_error() -> None:
    with pytest.raises(TypeError):
        _ = Severity.MEDIUM < 1  # type: ignore[operator]


def test_severity_max_with_valid_value_string_follows_domain_order() -> None:
    assert max([Severity.MEDIUM, "alta"]) == Severity.HIGH


def test_severity_compared_with_unknown_string_raises() -> None:
    with pytest.raises(ValueError):
        _ = Severity.MEDIUM < "baja"


def test_unknown_string_compared_with_severity_raises() -> None:
    with pytest.raises(ValueError):
        _ = Severity.MEDIUM > "baja"


def test_stage_values_in_downstream_order() -> None:
    assert [s.value for s in Stage] == ["carroceria", "pintura", "montaje", "calidad", "patio", "despacho"]


def test_stage_members_by_name() -> None:
    assert Stage.BODY.value == "carroceria"
    assert Stage.PAINT.value == "pintura"
    assert Stage.ASSEMBLY.value == "montaje"
    assert Stage.QUALITY.value == "calidad"
    assert Stage.YARD.value == "patio"
    assert Stage.DISPATCH.value == "despacho"


def test_stage_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        Stage("horno")


def test_market_values() -> None:
    assert {m.value for m in Market} == {"Local", "Brasil", "Europa"}


def test_market_parses_from_value() -> None:
    assert Market("Brasil") == "Brasil"


def test_market_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        Market("Chile")


def test_model_values_match_data_contract() -> None:
    assert {m.value for m in Model} == {"Sedán", "SUV", "Pickup"}


def test_model_requires_accented_sedan() -> None:
    with pytest.raises(ValueError):
        Model("Sedan")


def test_nine_combinations_exist() -> None:
    assert len(list(Model)) * len(list(Market)) == 9


def test_enums_are_str_subclasses() -> None:
    assert isinstance(Severity.HIGH, str)
    assert isinstance(Stage.PAINT, str)
    assert isinstance(Market("Local"), str)
    assert isinstance(Model("SUV"), str)
