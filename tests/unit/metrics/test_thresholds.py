"""T2: Thresholds loaded from a synthetic umbrales.yaml."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from plant_monitor.metrics.thresholds import Thresholds, load_thresholds

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "plant" / "umbrales.yaml"

EXPECTED: dict[str, Any] = {
    "gap": {"minimo_unidades": 3, "media": 10, "alta": 20, "critica": 35},
    "retraso_dias": {
        "Local": {"media": 1, "alta": 2, "critica": 3},
        "Brasil": {"alta": 1, "critica": 3},
        "Europa": {"alta": 1, "critica": 3},
    },
    "demora": {"tolerancia_minutos": 60},
    "resolucion": {"snapshots_sin_desvio": 2},
}

CUSTOM_YAML = """\
gap:
  minimo_unidades: 5
  media: 12
  alta: 25
  critica: 40
retraso_dias:
  Local:  {media: 2, alta: 4, critica: 6}
  Brasil: {alta: 2, critica: 5}
  Europa: {alta: 7, critica: 14}
demora:
  tolerancia_minutos: 45
resolucion:
  snapshots_sin_desvio: 3
"""


def as_contract(thresholds: Thresholds) -> dict[str, Any]:
    """Thresholds serialized with umbrales.yaml keys, absent levels dropped."""
    return thresholds.model_dump(mode="json", by_alias=True, exclude_none=True)


def write_yaml(tmp_path: Path, text: str) -> Path:
    """Write a umbrales.yaml variant to a temp dir."""
    path = tmp_path / "umbrales.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def loaded() -> dict[str, Any]:
    """Fixture umbrales.yaml loaded and serialized."""
    return as_contract(load_thresholds(FIXTURE))


def test_load_thresholds_returns_thresholds() -> None:
    assert isinstance(load_thresholds(FIXTURE), Thresholds)


def test_load_thresholds_mirrors_fixture_values(loaded: dict[str, Any]) -> None:
    assert loaded == EXPECTED


def test_gap_minimum_units_and_levels(loaded: dict[str, Any]) -> None:
    assert loaded["gap"] == {"minimo_unidades": 3, "media": 10, "alta": 20, "critica": 35}


def test_local_delay_has_media_alta_critica(loaded: dict[str, Any]) -> None:
    assert loaded["retraso_dias"]["Local"] == {"media": 1, "alta": 2, "critica": 3}


@pytest.mark.parametrize("market", ["Brasil", "Europa"])
def test_brasil_and_europa_delay_have_no_media(loaded: dict[str, Any], market: str) -> None:
    levels = loaded["retraso_dias"][market]
    assert "media" not in levels
    assert levels == {"alta": 1, "critica": 3}


def test_delay_levels_cover_the_three_markets(loaded: dict[str, Any]) -> None:
    assert set(loaded["retraso_dias"]) == {"Local", "Brasil", "Europa"}


def test_tolerance_minutes_loaded(loaded: dict[str, Any]) -> None:
    assert loaded["demora"]["tolerancia_minutos"] == 60


def test_snapshots_without_deviation_loaded(loaded: dict[str, Any]) -> None:
    assert loaded["resolucion"]["snapshots_sin_desvio"] == 2


def test_values_come_from_the_file_not_defaults(tmp_path: Path) -> None:
    loaded = as_contract(load_thresholds(write_yaml(tmp_path, CUSTOM_YAML)))
    assert loaded["gap"] == {"minimo_unidades": 5, "media": 12, "alta": 25, "critica": 40}
    assert loaded["retraso_dias"]["Local"] == {"media": 2, "alta": 4, "critica": 6}
    assert loaded["retraso_dias"]["Brasil"] == {"alta": 2, "critica": 5}
    assert loaded["retraso_dias"]["Europa"] == {"alta": 7, "critica": 14}
    assert loaded["demora"]["tolerancia_minutos"] == 45
    assert loaded["resolucion"]["snapshots_sin_desvio"] == 3


def test_missing_section_raises(tmp_path: Path) -> None:
    text = CUSTOM_YAML.replace("resolucion:\n  snapshots_sin_desvio: 3\n", "")
    with pytest.raises(ValueError):
        load_thresholds(write_yaml(tmp_path, text))


def test_misspelled_market_raises(tmp_path: Path) -> None:
    text = CUSTOM_YAML.replace("Brasil:", "Brasill:")
    with pytest.raises(ValueError):
        load_thresholds(write_yaml(tmp_path, text))


def test_missing_market_raises_naming_it(tmp_path: Path) -> None:
    text = CUSTOM_YAML.replace("  Europa: {alta: 7, critica: 14}\n", "")
    assert "Europa" not in text
    with pytest.raises(ValueError, match="Europa"):
        load_thresholds(write_yaml(tmp_path, text))


def test_yaml_syntax_error_raises_value_error_naming_the_file(tmp_path: Path) -> None:
    text = CUSTOM_YAML.replace("  media: 12\n", "  media: [12\n")
    path = write_yaml(tmp_path, text)
    with pytest.raises(ValueError) as info:
        load_thresholds(path)
    assert path.name in str(info.value)


def test_non_numeric_threshold_raises(tmp_path: Path) -> None:
    text = CUSTOM_YAML.replace("tolerancia_minutos: 45", "tolerancia_minutos: mucho")
    with pytest.raises(ValueError):
        load_thresholds(write_yaml(tmp_path, text))


def test_thresholds_is_frozen() -> None:
    thresholds = load_thresholds(FIXTURE)
    name = next(iter(Thresholds.model_fields))
    with pytest.raises(ValidationError):
        setattr(thresholds, name, None)
