from pathlib import Path

import pytest
from pydantic import ValidationError

from plant_monitor.config import Settings


@pytest.fixture(autouse=True)
def _aislar_entorno(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Cada test corre sin el .env real ni variables del sistema."""
    monkeypatch.chdir(tmp_path)
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_EFFORT", "DATA_DIR", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)


def test_falla_sin_api_key() -> None:
    with pytest.raises(ValidationError):
        Settings()


def test_lee_del_entorno_con_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = Settings()
    assert settings.anthropic_model == "claude-haiku-5-5"
    assert settings.data_dir == Path("data")


def test_lee_de_archivo_env(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-archivo\nLOG_LEVEL=DEBUG\n", encoding="utf-8")
    settings = Settings()
    assert settings.anthropic_api_key.get_secret_value() == "sk-archivo"
    assert settings.log_level == "DEBUG"


def test_api_key_no_se_filtra_en_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secreta")
    assert "sk-secreta" not in repr(Settings())


def test_rechaza_effort_invalido(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_EFFORT", "turbo")
    with pytest.raises(ValidationError):
        Settings()
