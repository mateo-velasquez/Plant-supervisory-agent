"""016 T1: the early-warning settings (R10, E14)."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from plant_monitor.config import Settings

from builders import isolate_settings_env

WINDOW = "EARLY_WARNING_WINDOW_SNAPSHOTS"
HORIZON = "EARLY_WARNING_HORIZON_SNAPSHOTS"


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each test runs without the real .env or system variables."""
    isolate_settings_env(monkeypatch, tmp_path)
    monkeypatch.delenv(WINDOW, raising=False)
    monkeypatch.delenv(HORIZON, raising=False)


def test_e14_defaults() -> None:
    settings = Settings(anthropic_api_key="k")
    assert settings.early_warning_window_snapshots == 12
    assert settings.early_warning_horizon_snapshots == 3


@pytest.mark.parametrize(("name", "value"), [(WINDOW, "1"), (HORIZON, "0")])
def test_e14_out_of_bounds_values_are_rejected(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(anthropic_api_key="k")


def test_e14_env_example_names_both_settings() -> None:
    example = Path(__file__).resolve().parents[2] / ".env.example"
    lines = example.read_text(encoding="utf-8").splitlines()
    for name in (WINDOW, HORIZON):
        assert any(line.startswith(f"{name}=") for line in lines)
