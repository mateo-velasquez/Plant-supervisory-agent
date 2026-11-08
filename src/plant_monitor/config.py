"""Settings from environment variables (take precedence) and '.env'; fails fast if anything is missing."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: SecretStr = Field(min_length=1)
    anthropic_model: str = "claude-haiku-5-5"
    anthropic_effort: Literal["low", "medium", "high"] = "medium"

    data_dir: Path = Path("data")
    output_dir: Path = Path("outputs")

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # Product guard for held-out days (FR-40, Q-37); not the dev hook CLAUDE_ALLOW_HELDOUT.
    heldout_open: bool = False
    heldout_first_shift: str = Field(default="T22", min_length=1)

    # Size budgets for tool outputs and logbook texts (006 R12); about 4x the longest logbook.
    tool_output_max_chars: int = Field(default=4000, gt=0)
    logbook_max_chars: int = Field(default=4000, gt=0)

    @property
    def registry_path(self) -> Path:
        """Registry SQLite file, derived from output_dir."""
        return self.output_dir / "registry.sqlite3"

    @property
    def notices_dir(self) -> Path:
        """Directory of the file notifier, derived from output_dir."""
        return self.output_dir / "notices"

    @property
    def plant_dir(self) -> Path:
        """Plant files (turnos.csv, plan, standards, shipments), derived from data_dir."""
        return self.data_dir / "planta"

    @property
    def snapshots_dir(self) -> Path:
        """Snapshot JSON files and 'llegadas.csv', derived from data_dir."""
        return self.data_dir / "snapshots"

    @property
    def logbooks_dir(self) -> Path:
        """Shift logbook texts, derived from data_dir."""
        return self.data_dir / "bitacoras"

    @property
    def rules_dir(self) -> Path:
        """Domain rules (criterio.md, umbrales.yaml), derived from data_dir."""
        return self.data_dir / "reglas"

    @property
    def evals_dir(self) -> Path:
        """Evaluation run outputs, derived from output_dir."""
        return self.output_dir / "evals"


@lru_cache
def get_settings() -> Settings:
    """Single settings instance for the whole application."""
    return Settings()
