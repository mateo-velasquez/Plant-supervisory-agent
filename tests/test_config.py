from pathlib import Path

import pytest
from pydantic import ValidationError

from plant_monitor.config import Settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each test runs without the real .env or system variables."""
    monkeypatch.chdir(tmp_path)
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL", "ANTHROPIC_EFFORT", "DATA_DIR", "LOG_LEVEL"):
        monkeypatch.delenv(var, raising=False)


def test_fails_without_api_key() -> None:
    with pytest.raises(ValidationError):
        Settings()


def test_reads_environment_with_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = Settings()
    assert settings.anthropic_model == "claude-haiku-5-5"
    assert settings.data_dir == Path("data")


def test_reads_env_file(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-file\nLOG_LEVEL=DEBUG\n", encoding="utf-8")
    settings = Settings()
    assert settings.anthropic_api_key.get_secret_value() == "sk-file"
    assert settings.log_level == "DEBUG"


def test_api_key_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")
    assert "sk-secret" not in repr(Settings())


def test_rejects_invalid_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_EFFORT", "turbo")
    with pytest.raises(ValidationError):
        Settings()
