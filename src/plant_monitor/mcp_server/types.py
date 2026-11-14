"""Plain tool types shared by 'mcp_server' and 'agents'; no 'mcp' import (R17)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

LIST_AVAILABLE_LOGBOOKS: Final = "list_available_logbooks"
GET_LOGBOOK: Final = "get_logbook"
GET_DEVIATIONS: Final = "get_deviations"
GET_ACTIVE_CASES: Final = "get_active_cases"
GET_CASE: Final = "get_case"
GET_DELAYED_UNITS: Final = "get_delayed_units"
SET_CAUSE: Final = "set_cause"
RAISE_SEVERITY: Final = "raise_severity"
LIFT_SEVERITY_RAISE: Final = "lift_severity_raise"
APPLY_PROPOSAL: Final = "apply_proposal"
EMIT_ALERT: Final = "emit_alert"
EMIT_SHIFT_REPORT: Final = "emit_shift_report"
CRITERIA_PROMPT: Final = "criteria"

READ_TOOLS: Final[tuple[str, ...]] = (
    LIST_AVAILABLE_LOGBOOKS,
    GET_LOGBOOK,
    GET_DEVIATIONS,
    GET_ACTIVE_CASES,
    GET_CASE,
    GET_DELAYED_UNITS,
)
WRITE_TOOLS: Final[tuple[str, ...]] = (
    SET_CAUSE,
    RAISE_SEVERITY,
    LIFT_SEVERITY_RAISE,
    APPLY_PROPOSAL,
    EMIT_ALERT,
    EMIT_SHIFT_REPORT,
)


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
