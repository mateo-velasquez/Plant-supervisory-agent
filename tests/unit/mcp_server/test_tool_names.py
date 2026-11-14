"""010 T16: tool names have one source in 'mcp_server.types' (R2, D4, E24)."""

from plant_monitor.mcp_server import server, types


def test_e24_server_re_exports_the_types_tuples_with_the_same_values() -> None:
    """E24: 'server.READ_TOOLS' and 'WRITE_TOOLS' are the 'types' objects, values unchanged."""
    assert server.READ_TOOLS is types.READ_TOOLS
    assert server.WRITE_TOOLS is types.WRITE_TOOLS
    assert types.READ_TOOLS == (
        types.LIST_AVAILABLE_LOGBOOKS,
        types.GET_LOGBOOK,
        types.GET_DEVIATIONS,
        types.GET_ACTIVE_CASES,
        types.GET_CASE,
        types.GET_DELAYED_UNITS,
    )
    assert types.WRITE_TOOLS == (
        types.SET_CAUSE,
        types.RAISE_SEVERITY,
        types.LIFT_SEVERITY_RAISE,
        types.APPLY_PROPOSAL,
        types.EMIT_ALERT,
        types.EMIT_SHIFT_REPORT,
    )
    assert (types.GET_LOGBOOK, types.APPLY_PROPOSAL, types.EMIT_ALERT) == (
        "get_logbook",
        "apply_proposal",
        "emit_alert",
    )
