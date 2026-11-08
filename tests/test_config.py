from pathlib import Path

import pytest
from pydantic import ValidationError

from plant_monitor.config import Settings


@pytest.fixture(autouse=True)
def _isolate_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Each test runs without the real .env or system variables."""
    monkeypatch.chdir(tmp_path)
    for var in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_EFFORT",
        "DATA_DIR",
        "LOG_LEVEL",
        "HELDOUT_OPEN",
        "HELDOUT_FIRST_SHIFT",
        "TOOL_OUTPUT_MAX_CHARS",
        "LOGBOOK_MAX_CHARS",
    ):
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


def test_e28_registry_path_is_derived_from_output_dir_with_no_new_variable() -> None:
    settings = Settings(anthropic_api_key="k", output_dir=Path("out"))
    assert settings.registry_path == Path("out") / "registry.sqlite3"
    assert "registry_path" not in Settings.model_fields


def test_e34_notices_dir_is_derived_from_output_dir_with_no_new_variable() -> None:
    settings = Settings(anthropic_api_key="k", output_dir=Path("out"))
    assert settings.notices_dir == Path("out") / "notices"
    assert "notices_dir" not in Settings.model_fields


def test_rejects_invalid_effort(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("ANTHROPIC_EFFORT", "turbo")
    with pytest.raises(ValidationError):
        Settings()


def test_e36_heldout_defaults_and_no_cutoff_field() -> None:
    settings = Settings(anthropic_api_key="k")
    assert settings.heldout_open is False
    assert settings.heldout_first_shift == "T22"
    assert not [name for name in Settings.model_fields if "cutoff" in name]


def test_e36_heldout_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("HELDOUT_OPEN", "true")
    monkeypatch.setenv("HELDOUT_FIRST_SHIFT", "T20")
    settings = Settings()
    assert settings.heldout_open is True
    assert settings.heldout_first_shift == "T20"


def test_e36_empty_first_heldout_shift_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("HELDOUT_FIRST_SHIFT", "")
    with pytest.raises(ValidationError):
        Settings()


def test_e36_derived_paths_come_from_data_dir_and_output_dir() -> None:
    settings = Settings(anthropic_api_key="k", data_dir=Path("d"), output_dir=Path("o"))
    assert settings.plant_dir == Path("d") / "planta"
    assert settings.snapshots_dir == Path("d") / "snapshots"
    assert settings.logbooks_dir == Path("d") / "bitacoras"
    assert settings.rules_dir == Path("d") / "reglas"
    assert settings.evals_dir == Path("o") / "evals"
    derived = {"plant_dir", "snapshots_dir", "logbooks_dir", "rules_dir", "evals_dir"}
    assert derived.isdisjoint(Settings.model_fields)


def test_e19_budget_defaults() -> None:
    """E19 (a): both budgets default to 4000."""
    settings = Settings(anthropic_api_key="k")
    assert settings.tool_output_max_chars == 4000
    assert settings.logbook_max_chars == 4000


def test_e19_budgets_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """E19 (b): env overrides both budgets."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("TOOL_OUTPUT_MAX_CHARS", "2500")
    monkeypatch.setenv("LOGBOOK_MAX_CHARS", "3000")
    settings = Settings()
    assert settings.tool_output_max_chars == 2500
    assert settings.logbook_max_chars == 3000


@pytest.mark.parametrize("name", ["TOOL_OUTPUT_MAX_CHARS", "LOGBOOK_MAX_CHARS"])
def test_e19_zero_budget_is_rejected(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    """E19 (c): a zero budget is invalid."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv(name, "0")
    with pytest.raises(ValidationError):
        Settings()


def test_e19_env_example_has_both_budget_lines() -> None:
    """E19 (d): '.env.example' names both variables."""
    example = Path(__file__).resolve().parents[1] / ".env.example"
    lines = example.read_text(encoding="utf-8").splitlines()
    for name in ("TOOL_OUTPUT_MAX_CHARS", "LOGBOOK_MAX_CHARS"):
        assert any(line.startswith(f"{name}=") for line in lines)


def test_e36_env_example_lists_every_settings_field() -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    names = {
        line.split("=", 1)[0].strip()
        for line in example.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    assert {field.upper() for field in Settings.model_fields} <= names
    assert {"HELDOUT_OPEN", "HELDOUT_FIRST_SHIFT"} <= names
