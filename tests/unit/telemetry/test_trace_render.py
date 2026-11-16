import pytest
from trace_builders import agent_alert, committed_line, history_row, stored, tool_call, trace_file

from plant_monitor.domain.causes import Evidence
from plant_monitor.telemetry.trace_query import build_notice_trace
from plant_monitor.telemetry.trace_render import render_notice_trace

from notice_builders import alert_notice

CASE = "S019-Pickup-Local"
ESC, BEL, DEL, CSI = "\x1b", "\x07", "\x7f", "\x9b"


def test_e10_a_logbook_cannot_drive_the_terminal() -> None:
    """Risk: 013 E10 (R12; Q-81, FR-20): control characters in stored text print as '\\xHH' escapes."""
    notice = agent_alert(
        "S020",
        CASE,
        f"ver {ESC}[31mrojo{ESC}[0m",
        [Evidence(bitacora="T10", fragmento=f"parada{BEL} total{DEL}")],
    )
    call = tool_call(1, "emit_alert", {"case_id": CASE, "texto": f"a{CSI}b"})
    source = stored(notice, [history_row(CASE, "S020")])

    text = render_notice_trace(
        build_notice_trace(
            source, [trace_file("trace-a.jsonl", committed_line("S020", coordinator_calls=[call]))]
        )
    )

    assert 'texto: "ver \\x1b[31mrojo\\x1b[0m"' in text
    assert '  T10: "parada\\x07 total\\x7f"' in text
    assert '{"case_id":"S019-Pickup-Local","texto":"a\\x9bb"}' in text
    assert not [ch for ch in text if ch != "\n" and (ch < " " or "\x7f" <= ch <= "\x9f")]


@pytest.mark.parametrize(
    ("gap_units", "gap_pct", "delay_days", "expected"),
    [
        pytest.param(-4.0, None, 0.0, "gap -4.0 units (no shift plan), delay 0.0 days", id="null_gap_pct"),
        pytest.param(-4.0, -13.3, None, "(-13.3 %), delay beyond the shipment horizon,", id="null_delay"),
        pytest.param(-0.04, -0.1, 0.0, "gap 0.0 units (-0.1 %)", id="negative_zero_gap"),
    ],
)
def test_x4_null_metrics_render_without_crashing(
    gap_units: float, gap_pct: float | None, delay_days: float | None, expected: str
) -> None:
    """013 X4 (R12; Q-04, Q-16): a null percentage or delay has its own wording and '-0.0' never shows."""
    row = history_row(CASE, "S020", gap_units=gap_units, gap_pct=gap_pct, delay_days=delay_days)
    source = stored(alert_notice("S020", CASE), [row])

    text = render_notice_trace(build_notice_trace(source, None))

    assert expected in text
