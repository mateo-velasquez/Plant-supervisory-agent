"""Thresholds from `umbrales.yaml`; field names mirror the file's keys."""

from pathlib import Path

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    NonNegativeFloat,
    NonNegativeInt,
    PositiveInt,
    ValidationError,
    model_validator,
)

from plant_monitor.domain.enums import Market


class _StrictFrozen(BaseModel):
    """Immutable and rejects unknown keys, so a typo never silently drops a level."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class GapThresholds(_StrictFrozen):
    """Gap levels as % behind the daily plan, gated by a minimum of units behind."""

    minimo_unidades: NonNegativeInt
    media: NonNegativeFloat
    alta: NonNegativeFloat
    critica: NonNegativeFloat


class DelayLevels(_StrictFrozen):
    """Delay levels in days for one market; `media` is absent for some markets."""

    media: NonNegativeFloat | None = None
    alta: NonNegativeFloat
    critica: NonNegativeFloat


class StageDelayThresholds(_StrictFrozen):
    tolerancia_minutos: NonNegativeInt


class ResolutionThresholds(_StrictFrozen):
    snapshots_sin_desvio: PositiveInt


class Thresholds(_StrictFrozen):
    gap: GapThresholds
    retraso_dias: dict[Market, DelayLevels]
    demora: StageDelayThresholds
    resolucion: ResolutionThresholds

    @model_validator(mode="after")
    def _every_market_has_delay_levels(self) -> Thresholds:
        missing = [m.value for m in Market if m not in self.retraso_dias]
        if missing:
            raise ValueError(f"retraso_dias is missing markets: {', '.join(missing)}")
        return self


def load_thresholds(path: Path) -> Thresholds:
    """Load and validate `umbrales.yaml`; errors name the file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    try:
        return Thresholds.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{path}: {exc}") from exc
