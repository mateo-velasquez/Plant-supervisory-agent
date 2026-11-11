"""Settings from environment variables (take precedence) and '.env'; fails fast if anything is missing."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
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

    # Anthropic call and retry limits (007 R16).
    anthropic_max_tokens: int = Field(default=16000, ge=1, le=128_000)
    anthropic_max_retries: int = Field(default=4, ge=0, le=10)
    anthropic_retry_base_seconds: float = Field(default=1.0, gt=0)
    anthropic_retry_cap_seconds: float = 30.0

    # Loop limits (007 R16); the prompt ceiling is the 100k hard limit.
    prompt_token_limit: int = Field(default=95000, ge=1, le=100_000)
    agent_max_turns: int = Field(default=8, ge=1)
    notice_text_max_chars: int = Field(default=1500, gt=0)

    # Multi-agent limits (009 R15).
    investigator_max_turns: int = Field(default=4, ge=1)
    proposal_output_max_chars: int = Field(default=2000, gt=0)
    logbook_review_max_attempts: int = Field(default=2, ge=1)

    # Prices in USD per million tokens (007 R16).
    price_input_per_mtok: Decimal = Field(default=Decimal("0.10"), ge=0)
    price_cache_write_5m_per_mtok: Decimal = Field(default=Decimal("0.125"), ge=0)
    price_cache_write_1h_per_mtok: Decimal = Field(default=Decimal("0.20"), ge=0)
    price_cache_read_per_mtok: Decimal = Field(default=Decimal("0.01"), ge=0)
    price_output_per_mtok: Decimal = Field(default=Decimal("0.50"), ge=0)
    long_context_threshold_tokens: int = Field(default=100000, gt=0)
    long_context_multiplier: Decimal = Field(default=Decimal(5), ge=1)

    @model_validator(mode="after")
    def _retry_cap_not_below_base(self) -> Self:
        if self.anthropic_retry_cap_seconds < self.anthropic_retry_base_seconds:
            raise ValueError("anthropic_retry_cap_seconds must be >= anthropic_retry_base_seconds")
        return self

    @property
    def traces_dir(self) -> Path:
        """Run trace files, derived from output_dir."""
        return self.output_dir / "traces"

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
