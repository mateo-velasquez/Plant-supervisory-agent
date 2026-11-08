"""Plain tool types shared by 'mcp_server' and 'agents'; no 'mcp' import (R17)."""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ToolSpec:
    """Name, description and input schema of one tool."""

    name: str
    description: str
    input_schema: Mapping[str, object]


@dataclass(frozen=True)
class ToolOutcome:
    """Text of a tool result and whether it is an error the model should read."""

    text: str
    is_error: bool
