import pytest
from agent_builders import RAISE2, lift_proposal, set_cause_proposal
from incident_runs import EV_T02, PICKUP_ANY, SUV_EUROPE
from trace_builders import (
    active_cause,
    agent_alert,
    apply_call,
    committed_line,
    history_row,
    stored,
    tool_call,
    trace_file,
)

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import ActiveCause, CauseCategory, CitedCause, Evidence
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import NoticeType
from plant_monitor.telemetry.trace import TraceLine, TraceToolCall
from plant_monitor.telemetry.trace_query import NoticeTrace, build_notice_trace
from plant_monitor.telemetry.trace_render import render_notice_trace

from notice_builders import alert_notice, make_notice

CASE = "S019-Pickup-Local"
OTHER = "S020-SUV-Local"
EV_F = Evidence(bitacora="T10", fragmento="f")
SUV_CASE = "S005-SUV-Europa"


def _coordinator_calls(trace: NoticeTrace) -> tuple[bool, ...]:
    assert trace.line is not None
    coordinator = next(a for a in trace.line.agents if a.agent == "coordinator")
    return tuple(c.this_case for c in coordinator.calls)


def test_e9_call_marking_follows_the_case_and_the_applied_proposal() -> None:
    """013 E9 (R8): a call is marked for this case by argument, report item, or applied proposal."""
    raise_p4 = {**RAISE2, "categoria": "parada_de_linea", "etapa": "montaje", "modelo": "Pickup"}
    raise_p4 |= {"mercado": None, "bitacora": "T10", "fragmento": "f"}
    proposals = [
        {"id": "S020-p1", **set_cause_proposal(CASE, "parada_de_linea", "T10", "f", "activa_sin_fecha")},
        {"id": "S020-p2", **set_cause_proposal(OTHER, "parada_de_linea", "T10", "f", "activa_sin_fecha")},
        {"id": "S020-p3", **lift_proposal("S010-causa-1", "T10", "f", "resuelta")},
        {"id": "S020-p4", **raise_p4},
    ]
    calls: list[TraceToolCall] = [
        tool_call(1, "get_case", {"case_id": CASE}),
        tool_call(2, "get_case", {"case_id": OTHER}),
        tool_call(
            3,
            "emit_shift_report",
            {"textos": [{"case_id": OTHER, "texto": "x"}, {"case_id": CASE, "texto": "y"}]},
        ),
        apply_call(4, "S020-p1"),
        apply_call(5, "S020-p2"),
        apply_call(6, "S020-p3"),
        apply_call(7, "S020-p4"),
        apply_call(8, "S020-p1", error="refused"),
        apply_call(9, "S020-p9"),
        tool_call(10, "emit_alert", {"case_id": 7, "texto": "t"}),
    ]
    causes = (
        active_cause(
            "S010-causa-1",
            "S010",
            Evidence(bitacora="T05", fragmento="g"),
            CauseCategory.LINE_STOP,
            PICKUP_ANY,
        ),
        active_cause("S020-causa-1", "S020", EV_F, CauseCategory.LINE_STOP, PICKUP_ANY),
    )
    source = stored(
        alert_notice("S020", CASE),
        [history_row(CASE, "S019"), history_row(CASE, "S020")],
        causes,
        links={"S010-causa-1": "S019", "S020-causa-1": "S021"},
        order={"S010": 1, "S019": 2, "S020": 3, "S021": 4},
    )

    trace = build_notice_trace(
        source,
        [trace_file("trace-a.jsonl", committed_line("S020", proposals=proposals, coordinator_calls=calls))],
    )

    assert _coordinator_calls(trace) == (True, False, True, True, False, True, False, False, False, False)
    assert [c.cause.active_cause_id for c in trace.causes] == ["S010-causa-1"]


def test_x1_news_of_a_case_resolved_earlier_uses_the_last_row_before_the_snapshot() -> None:
    """013 X1 (R5): with no row at S018 the view uses S017 and its predecessor S016."""
    case = "S015-SUV-Local"
    rows = [
        history_row(case, "S015", CaseState.OPEN, Severity.MEDIUM),
        history_row(case, "S016", CaseState.FOLLOW_UP, Severity.NONE),
        history_row(case, "S017", CaseState.RESOLVED, Severity.NONE),
    ]
    notice = make_notice(
        "S018", NoticeType.SHIFT_REPORT, case, severity=Severity.NONE, state=CaseState.RESOLVED
    )
    source = stored(notice, rows, order={"S015": 1, "S016": 2, "S017": 3, "S018": 4})

    trace = build_notice_trace(source, None)
    view = trace.history

    assert (view.row.snapshot_id, view.at_notice, view.opened_at) == ("S017", False, "S015")
    assert view.previous is not None
    assert view.previous.snapshot_id == "S016"
    lines = render_notice_trace(trace).splitlines()
    assert any(line.startswith("metrics at S017 (last history row; no row at S018): ") for line in lines)
    assert "severity at S017: minimum ninguna, effective ninguna, raised no" in lines
    assert "transition: en_seguimiento (S016) → resuelto (S017)" in lines
    assert "motivo: none" in lines


@pytest.mark.parametrize(
    ("line_names", "line_present", "text_by", "opening_status", "rendered"),
    [
        pytest.param(
            ("S004", "aborted-S020"),
            False,
            "unknown",
            "found",
            ("trace: no committed trace line for S020", "text written by: unknown"),
            id="a_no_notice_line",
        ),
        pytest.param(
            ("S020-agent",),
            True,
            "agent",
            "no_line",
            ("    raise opened at S004: no committed trace line",),
            id="b_no_opening_line",
        ),
        pytest.param(
            ("S004-plain", "S020-template"),
            True,
            "template",
            "no_proposal",
            ("    raise opened at S004: no matching proposal in the committed line",),
            id="c_no_proposal",
        ),
    ],
)
def test_x2_missing_lines_fall_back_without_guessing(
    line_names: tuple[str, ...],
    line_present: bool,
    text_by: str,
    opening_status: str,
    rendered: tuple[str, ...],
) -> None:
    """013 X2 (R6, R9): no notice line, no opening line, and an opening line without a match."""
    notice = alert_notice("S020", SUV_CASE)
    matching = [{"id": "S004-p1", **RAISE2}]
    builders: dict[str, TraceLine] = {
        "S004": committed_line("S004", proposals=matching, coordinator_calls=[apply_call(1, "S004-p1")]),
        "aborted-S020": committed_line("S020", status="aborted"),
        "S020-agent": committed_line("S020", notices_agent=[notice.notice_id]),
        "S004-plain": committed_line("S004"),
        "S020-template": committed_line("S020", notices_template=[notice.notice_id]),
    }
    cause = active_cause("S004-causa-1", "S004", EV_T02, CauseCategory.QUALITY_HOLD, SUV_EUROPE)
    source = stored(
        notice,
        [history_row(SUV_CASE, "S005"), history_row(SUV_CASE, "S020")],
        [cause],
        links={"S004-causa-1": "S005"},
        order={"S004": 1, "S005": 2, "S020": 3},
    )

    trace = build_notice_trace(source, [trace_file("trace-a.jsonl", *(builders[k] for k in line_names))])

    assert (trace.line is not None) == line_present
    assert trace.text_by == text_by
    opening = trace.causes[0].opening
    assert opening is not None
    assert opening.status == opening_status
    assert set(rendered) <= set(render_notice_trace(trace).splitlines())


def test_x3_old_line_without_agent_fields_renders_a_coordinator_section_and_no_hooks() -> None:
    """013 X3 (R7, R8; Q-44): the 'ran' fallback gives a coordinator section and 'hooks' stays empty."""
    raw = committed_line("S020").model_dump(mode="json")
    for key in ("hooks", "agents_run", "investigator", "proposals_applied"):
        del raw[key]
    for call in raw["model_calls"]:
        call.pop("prefix_hash", None)
    old = TraceLine.model_validate(raw)
    source = stored(alert_notice("S020", CASE), [history_row(CASE, "S020")])

    trace = build_notice_trace(source, [trace_file("trace-a.jsonl", old)])

    assert trace.line is not None
    assert [a.agent for a in trace.line.agents] == ["coordinator"]
    assert trace.line.hooks == ()
    assert not trace.line.no_agent
    assert "hooks: none" in render_notice_trace(trace).splitlines()


@pytest.mark.parametrize(
    ("applies", "cause_id", "status", "proposal_id", "apply_turn"),
    [
        pytest.param(
            [(1, None), (2, "duplicate raise")],
            "S004-causa-1",
            "found",
            "S004-p1",
            1,
            id="a_second_apply_refused",
        ),
        pytest.param(
            [(1, None), (2, None)], "S004-causa-1", "no_proposal", None, None, id="b_two_candidates"
        ),
        pytest.param([(1, None)], "S004-causa-2", "no_proposal", None, None, id="c_ordinal_disagrees"),
    ],
)
def test_x10_raise_match_needs_one_candidate_and_the_right_ordinal(
    applies: list[tuple[int, str | None]],
    cause_id: str,
    status: str,
    proposal_id: str | None,
    apply_turn: int | None,
) -> None:
    """013 X10 (R6 steps 3-4): ambiguity or an ordinal mismatch means no match, never a pick."""
    proposals = [{"id": "S004-p1", **RAISE2}, {"id": "S004-p2", **RAISE2}]
    calls = [apply_call(turn, f"S004-p{turn}", error=error) for turn, error in applies]
    source = stored(
        alert_notice("S005", SUV_CASE),
        [history_row(SUV_CASE, "S005", CaseState.ESCALATED, Severity.CRITICAL)],
        [active_cause(cause_id, "S004", EV_T02, CauseCategory.QUALITY_HOLD, SUV_EUROPE)],
        links={cause_id: "S005"},
        order={"S004": 1, "S005": 2},
    )

    trace = build_notice_trace(
        source,
        [trace_file("trace-a.jsonl", committed_line("S004", proposals=proposals, coordinator_calls=calls))],
    )

    opening = trace.causes[0].opening
    assert opening is not None
    assert opening.status == status
    assert (None if opening.proposal is None else opening.proposal["id"]) == proposal_id
    assert (None if opening.apply is None else opening.apply.turn) == apply_turn


@pytest.mark.parametrize(
    ("lifted_at", "lifted_by", "ends", "has_lift_line", "snapshot", "shift"),
    [
        pytest.param("S008", "T04", "; lifted at S008", True, "S008", "T04", id="a_lift_before_the_notice"),
        pytest.param("S012", "T06", "; in force at S010", False, "S012", "T06", id="b_lift_after_the_notice"),
    ],
)
def test_x12_a_lift_is_shown_only_at_or_before_the_notice_snapshot(
    lifted_at: str, lifted_by: str, ends: str, has_lift_line: bool, snapshot: str, shift: str
) -> None:
    """013 X12 (R4, R11, R12): a later lift is neither rendered nor counted among the shown ids."""
    case = "S005-SUV-Europa"
    cause = ActiveCause(
        active_cause_id="S004-causa-1",
        categoria=CauseCategory.QUALITY_HOLD,
        scope=SUV_EUROPE,
        opened_at="S004",
        opened_by=EV_T02,
        lifted_at=lifted_at,
        lifted_by=Evidence(bitacora=lifted_by, fragmento="auditoría cerrada"),
    )
    source = stored(
        alert_notice("S010", case),
        [history_row(case, "S005"), history_row(case, "S010")],
        [cause],
        links={"S004-causa-1": "S005"},
        order={"S004": 1, "S005": 2, "S008": 3, "S010": 4, "S012": 5},
    )

    trace = build_notice_trace(source, None)
    lines = render_notice_trace(trace).splitlines()

    assert any(line.startswith("  S004-causa-1:") and line.endswith(ends) for line in lines)
    assert (f'    lifted at {lifted_at} by {lifted_by}: "auditoría cerrada"' in lines) == has_lift_line
    assert (snapshot in trace.shown_snapshots()) == has_lift_line
    assert (shift in trace.shown_shifts()) == has_lift_line


def test_x13_ids_inside_write_tool_arguments_count_as_shown() -> None:
    """013 X13 (R11): 'active_cause_id', 'causa_activa', 'bitacora' and the cited id feed the shown sets."""
    case = "S010-Pickup-Local"
    evidence = Evidence(bitacora="T05", fragmento="f")
    notice = agent_alert("S010", case, "t", [evidence])
    rows = [history_row(case, "S010")]
    order = {"S004": 1, "S006": 2, "S010": 3}
    line = committed_line(
        "S010",
        proposals=[{"id": "S010-p1", **lift_proposal("S006-causa-1", "T05", "f", "resuelta")}],
        coordinator_calls=[tool_call(1, "set_cause", {"active_cause_id": "S004-causa-1", "bitacora": "T02"})],
    )

    via_calls = build_notice_trace(stored(notice, rows, order=order), [trace_file("trace-a.jsonl", line)])
    cited = CitedCause(
        categoria=CauseCategory.LINE_STOP,
        etapa=Stage.ASSEMBLY,
        evidence=evidence,
        set_at="S010",
        active_cause_id="S004-causa-1",
    )
    via_cited = build_notice_trace(stored(notice, rows, cited=cited, order=order), None)

    assert {"S004", "S006"} <= via_calls.shown_snapshots()
    assert "T02" in via_calls.shown_shifts()
    assert "S004" in via_cited.shown_snapshots()
