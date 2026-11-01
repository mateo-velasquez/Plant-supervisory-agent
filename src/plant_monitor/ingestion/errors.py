"""Load error type and a compact rendering of pydantic validation errors."""

from pydantic import ValidationError


class DataLoadError(ValueError):
    """Input data that cannot be loaded; the message names the file, the row and the field."""


def describe_validation_error(exc: ValidationError) -> str:
    """One `field 'x': reason` entry per validation error, joined by `; `."""
    parts: list[str] = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "<root>"
        got = "" if error["type"] == "missing" else f" (got {error['input']!r})"
        parts.append(f"field '{field}': {error['msg']}{got}")
    return "; ".join(parts)
