"""Domain enums; values keep the data contract's Spanish spelling (ADR-0005)."""

from enum import StrEnum


class Stage(StrEnum):
    """Plant stages, defined in downstream order."""

    BODY = "carroceria"
    PAINT = "pintura"
    ASSEMBLY = "montaje"
    QUALITY = "calidad"
    YARD = "patio"
    DISPATCH = "despacho"

    @property
    def rank(self) -> int:
        """Downstream position: higher means closer to dispatch."""
        return list(Stage).index(self)


PRODUCTION_STAGES: tuple[Stage, ...] = (Stage.BODY, Stage.PAINT, Stage.ASSEMBLY, Stage.QUALITY)
"""Stages a unit passes before reaching the yard, in downstream order."""


class Market(StrEnum):
    LOCAL = "Local"
    BRAZIL = "Brasil"
    EUROPE = "Europa"


class Model(StrEnum):
    SEDAN = "Sedán"
    SUV = "SUV"
    PICKUP = "Pickup"


class Severity(StrEnum):
    """Severity ordered by domain rank (NONE < MEDIUM < HIGH < CRITICAL), not alphabetically."""

    NONE = "ninguna"
    MEDIUM = "media"
    HIGH = "alta"
    CRITICAL = "critica"

    @property
    def rank(self) -> int:
        """Position in the domain order."""
        return list(Severity).index(self)

    @staticmethod
    def _coerce(other: object) -> Severity | None:
        """Convert a plain `str` to `Severity` (ValueError if unknown); None for other types."""
        if isinstance(other, Severity):
            return other
        if isinstance(other, str):
            return Severity(other)
        return None

    # As a str subclass, these run reflected first for `"x" < Severity.Y`, so plain strings raise too.
    def __lt__(self, other: str, /) -> bool:
        rhs = Severity._coerce(other)
        if rhs is None:
            return NotImplemented
        return self.rank < rhs.rank

    def __le__(self, other: str, /) -> bool:
        rhs = Severity._coerce(other)
        if rhs is None:
            return NotImplemented
        return self.rank <= rhs.rank

    def __gt__(self, other: str, /) -> bool:
        rhs = Severity._coerce(other)
        if rhs is None:
            return NotImplemented
        return self.rank > rhs.rank

    def __ge__(self, other: str, /) -> bool:
        rhs = Severity._coerce(other)
        if rhs is None:
            return NotImplemented
        return self.rank >= rhs.rank
