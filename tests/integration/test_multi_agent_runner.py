"""009 T15b, T16: IF series through investigator, control and coordinator (E18-E22, E24)."""

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from agent_builders import (
    RAISE2,
    RAISE5,
    end,
    lift_proposal,
    out,
    set_cause_proposal,
    tools_reply,
)
from control_builders import S010_TASK
from draft_builders import agent_text
from incident_builders import (
    INCIDENTS,
    copy_incident_logbooks,
    incident_context,
    incident_shifts,
    write_incident_series,
)
from incident_runs import AC1, AC2, EV_T02, EV_T05, F3, F4, F5, F6
from judgment_builders import PB_CASE, PL_CASE

from plant_monitor.agents.factory import COORDINATOR_TOOLS, INVESTIGATOR_TOOLS, load_prompt
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.investigator import CORRECTION_HEADER, render_task
from plant_monitor.agents.model import ModelCallFailed, ModelReply, ModelRequest, TextBlock, ToolResultBlock
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import Notice, NoticeType, Origin, Reason, ShiftReport
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.notify.composite import CompositeNotifier
from plant_monitor.notify.file import FileNotifier
from plant_monitor.runner.agent_pipeline import build_agent_pipeline
from plant_monitor.runner.outbox import OutboxDispatcher
from plant_monitor.runner.post_commit import PostCommitChain
from plant_monitor.runner.series import RunAborted, run_series
from plant_monitor.telemetry.trace import TraceLine, TraceWriter, read_trace, run_totals, trace_path
from plant_monitor.telemetry.usage import Usage

from builders import isolate_settings_env

SIDS = tuple(f"S{n:03d}" for n in range(1, 6))
ALL = tuple(f"S{n:03d}" for n in range(1, 13))
STARTED = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)
SECOND_START = datetime(2026, 3, 2, 23, 30, tzinfo=UTC)
USAGE = Usage(input_tokens=3000, output_tokens=200)
SE_CASE = "S005-SUV-Europa"
PE_CASE = "S011-Pickup-Europa"
WRONG_FRAGMENT = "se detuvo la línea de montaje de Pickup"
WRONG_RAISE5 = {**RAISE5, "fragmento": WRONG_FRAGMENT}
FRAGMENT_ERROR = "propuestas[0]: fragment not found in T05"
UNDECLARED_ERROR = (
    "propuestas[0]: no_declarada is never proposed: code keeps it when no logbook names a cause"
)

type Call = tuple[str, dict[str, object]]


def query(path: Path, sql: str) -> list[tuple[object, ...]]:
    """Rows of a read-only query over a closed registry file."""
    with closing(sqlite3.connect(path)) as conn:
        return [tuple(row) for row in conn.execute(sql)]


def run_ids(
    root: Path, settings: Settings, script: Sequence[ModelReply | Exception], ids: Sequence[str]
) -> tuple[FakeModel, tuple[TraceLine, ...]]:
    """Run the named IF snapshots on a file registry with a scripted model; return the model and the trace."""
    root.mkdir(parents=True, exist_ok=True)
    arrivals: list[Arrival] = write_incident_series(root / "snapshots", ids)
    model = FakeModel(script)
    trace = TraceWriter(trace_path(root / "traces", STARTED))
    policy = HeldOutPolicy.from_calendar(incident_shifts(), "T06", is_open=True)
    with SqliteRegistry(root / "registry.sqlite3") as registry:
        pipeline = build_agent_pipeline(settings, registry, incident_context(), policy, model, trace)
        run_series(arrivals, incident_shifts(), registry, pipeline, post_commit=trace)
    return model, read_trace(trace_path(root / "traces", STARTED))


# --- Script builders (the replies of 009 E19) ---


def alert_id(snapshot_id: str, case_id: str) -> str:
    return f"{snapshot_id}-{NoticeType.ALERT}-{case_id}"


def news_id(snapshot_id: str, case_id: str) -> str:
    return f"{snapshot_id}-{NoticeType.SHIFT_REPORT}-{case_id}"


def logbook(turno_id: str) -> Call:
    return ("get_logbook", {"turno_id": turno_id})


def alert(snapshot_id: str, case_id: str) -> Call:
    return ("emit_alert", {"case_id": case_id, "texto": agent_text(alert_id(snapshot_id, case_id))})


def report(snapshot_id: str, *case_ids: str) -> Call:
    textos = [{"case_id": c, "texto": agent_text(news_id(snapshot_id, c))} for c in case_ids]
    return ("emit_shift_report", {"textos": textos})


def apply(proposal_id: str) -> Call:
    return ("apply_proposal", {"propuesta": proposal_id})


def turn(number: int, *calls: Call) -> ModelReply:
    """One model reply with one or more tool uses, usage 3,000 / 200."""
    return tools_reply(*calls, prefix=f"tu{number}", usage=USAGE)


NONE = out(usage=USAGE)
LIFT4 = out(lift_proposal(AC1, "T04", F4, "resuelta"), usage=USAGE)
LIFT6 = out(lift_proposal(AC2, "T06", F6, "resuelta"), usage=USAGE)
S002 = [turn(1, logbook("T01")), NONE]
S004 = [turn(1, logbook("T02")), out(RAISE2, usage=USAGE), turn(1, apply("S004-p1")), end("Aplicada.", USAGE)]
S005 = [turn(1, alert("S005", SE_CASE))]
S006 = [turn(1, logbook("T03")), NONE, turn(1, report("S006", SE_CASE))]
S008 = [turn(1, logbook("T04")), LIFT4, turn(1, apply("S008-p1")), turn(2, report("S008", SE_CASE))]
S010_JUDGE = [turn(1, logbook("T05")), out(RAISE5, usage=USAGE), turn(1, apply("S010-p1"))]
S010_EMIT = [turn(2, alert("S010", PL_CASE), alert("S010", PB_CASE), report("S010", PL_CASE, PB_CASE))]
S011 = [turn(1, alert("S011", PE_CASE))]
S012 = [turn(1, logbook("T06")), LIFT6, turn(1, apply("S012-p1"), report("S012", PE_CASE))]
HEAD: list[ModelReply | Exception] = [*S002, *S004, *S005, *S006, *S008]
TAIL: list[ModelReply | Exception] = [*S011, *S012]
S012_NO_CAUSE = [
    NONE,
    turn(
        1,
        alert("S012", PL_CASE),
        alert("S012", PB_CASE),
        alert("S012", PE_CASE),
        report("S012", PL_CASE, PB_CASE, PE_CASE),
    ),
]


class Recorder:
    """Keeps the '(channel, id)' order of every delivered alert and report."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def alert(self, notice: Notice) -> None:
        self.calls.append(("alert", notice.notice_id))

    def report(self, report: ShiftReport) -> None:
        self.calls.append(("report", report.turno_id))


def run_full(
    root: Path,
    arrivals: Sequence[Arrival],
    settings: Settings,
    model: FakeModel,
    recorder: Recorder,
    started: datetime,
) -> None:
    """Run the series on 'root' with the production wiring: file registry, trace and outbox."""
    root.mkdir(parents=True, exist_ok=True)
    trace = TraceWriter(trace_path(root / "traces", started))
    with SqliteRegistry(root / "registry.sqlite3") as registry:
        pipeline = build_agent_pipeline(
            settings,
            registry,
            incident_context(),
            HeldOutPolicy.from_calendar(incident_shifts(), "T06", is_open=True),
            model,
            trace,
        )
        outbox = OutboxDispatcher(
            registry.notices,
            CompositeNotifier((FileNotifier(root / "out"), recorder)),
            lambda: datetime(2026, 3, 2, 23, 0, tzinfo=UTC),
        )
        run_series(
            arrivals, incident_shifts(), registry, pipeline, post_commit=PostCommitChain([trace, outbox])
        )


def stored_rows(path: Path) -> list[tuple[object, ...]]:
    """Every stored notice row of a closed registry file, in processing order."""
    return query(
        path, "SELECT notice_id, snapshot_id, kind, tipo, case_id, payload FROM notices ORDER BY seq, idx"
    )


def out_files(out_dir: Path) -> dict[str, bytes]:
    """File name to bytes for everything in the output directory."""
    return {p.name: p.read_bytes() for p in sorted(out_dir.iterdir())} if out_dir.exists() else {}


def notices_of(path: Path, snapshot_id: str) -> dict[str, Notice]:
    """The notices of a snapshot, report news included, by id."""
    with SqliteRegistry(path) as registry:
        items = registry.notices.for_snapshot(snapshot_id)
    found: dict[str, Notice] = {}
    for item in items:
        for notice in item.novedades if isinstance(item, ShiftReport) else (item,):
            found[notice.notice_id] = notice
    return found


def trace_of(root: Path, started: datetime = STARTED) -> dict[str, TraceLine]:
    """The run's trace lines by snapshot id."""
    return {line.snapshot_id: line for line in read_trace(trace_path(root / "traces", started))}


def tool_names(request: ModelRequest) -> tuple[str, ...]:
    return tuple(spec.name for spec in request.tools)


def split_requests(model: FakeModel) -> tuple[list[ModelRequest], list[ModelRequest]]:
    """The investigator's and the coordinator's requests, each in order."""
    inv: list[ModelRequest] = []
    coord: list[ModelRequest] = []
    for request in model.requests:
        (inv if set(tool_names(request)) == set(INVESTIGATOR_TOOLS) else coord).append(request)
    return inv, coord


def block_text(request: ModelRequest, index: int) -> str:
    """The text of the first block of message 'index' of a request."""
    block = request.messages[index].content[0]
    assert isinstance(block, TextBlock)
    return block.text


def task_of(request: ModelRequest) -> dict[str, object]:
    """The investigator task JSON of its first message."""
    parsed: dict[str, object] = json.loads(block_text(request, 0).split("\n")[1])
    return parsed


def at_s010(path: Path) -> list[tuple[object, ...]]:
    """State and severity the Pickup cases had when S010 closed."""
    return query(
        path,
        "SELECT case_id, state, effective_severity FROM case_history "
        "WHERE snapshot_id = 'S010' AND case_id LIKE 'S010-Pickup-%' ORDER BY case_id",
    )


def task_case_ids(request: ModelRequest) -> list[str]:
    """The 'case_id' of each case without a cause in the investigator task."""
    task = json.loads(block_text(request, 0).split("\n")[1])
    return [case["case_id"] for case in task["casos_sin_causa"]]


def review_rows(path: Path) -> list[tuple[object, ...]]:
    return query(
        path,
        "SELECT turno_id, attempts, reviewed_at, given_up_at FROM logbook_reviews ORDER BY turno_id",
    )


class Outcome:
    """A finished uninterrupted run: where it wrote and what it saw."""

    def __init__(self, root: Path, model: FakeModel, recorder: Recorder) -> None:
        self.root = root
        self.path = root / "registry.sqlite3"
        self.out = root / "out"
        self.model = model
        self.recorder = recorder


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Default settings with the IF logbooks under 'data_dir'."""
    isolate_settings_env(monkeypatch, tmp_path)
    return Settings(anthropic_api_key="k", data_dir=INCIDENTS)


@pytest.fixture
def arrivals(tmp_path: Path) -> list[Arrival]:
    """IF arrivals S001-S012 written under 'tmp_path'."""
    return write_incident_series(tmp_path / "snapshots", ALL)


@pytest.fixture
def e19(tmp_path: Path, arrivals: list[Arrival], settings: Settings) -> Outcome:
    """E19: the whole IF series with the exact script."""
    root = tmp_path / "e19"
    model = FakeModel([*HEAD, *S010_JUDGE, *S010_EMIT, *TAIL])
    recorder = Recorder()
    run_full(root, arrivals, settings, model, recorder, STARTED)
    return Outcome(root, model, recorder)


def test_e18_a_declined_proposal_leaves_no_cause_and_the_logbook_reviewed(
    tmp_path: Path, settings: Settings
) -> None:
    """E18, R9, R11: the coordinator declines; 'proposals' reason, no active cause, T02 'revisada'."""
    script = [out(usage=USAGE), out(RAISE2, usage=USAGE), end("No aplico la propuesta.", USAGE)]
    model, lines = run_ids(tmp_path / "e18", settings, script, SIDS)
    path = tmp_path / "e18" / "registry.sqlite3"
    assert len(model.requests) == 3
    by_id = {line.snapshot_id: line for line in lines}
    s004 = by_id["S004"]
    assert (s004.decision, s004.decision_reason) == ("call", "proposals")
    assert (s004.proposals_applied, s004.proposals_declined) == ([], ["S004-p1"])
    assert query(path, "SELECT active_cause_id FROM active_causes") == []
    assert query(path, "SELECT turno_id, attempts, reviewed_at FROM logbook_reviews ORDER BY turno_id") == [
        ("T01", 1, "S002"),
        ("T02", 1, "S004"),
    ]
    s005 = by_id["S005"]
    assert (s005.decision, s005.decision_reason, s005.notices_agent) == ("skip", "no_text_needed", [])
    with SqliteRegistry(path) as registry:
        case = registry.cases.get_case(SE_CASE)
    assert case is not None
    assert (case.state, case.current_severity) == (CaseState.OPEN, Severity.MEDIUM)


def test_e19_incident_series_through_both_agents_reviews_every_logbook_and_totals_per_agent(
    e19: Outcome,
) -> None:
    """E19, R1-R14: 22 requests, six reviews, the S010 and S011 requests, 12 trace lines, per-agent totals."""
    model = e19.model
    inv, coord = split_requests(model)
    assert (len(model.requests), len(inv), len(coord)) == (22, 12, 10)
    results = [
        b for r in model.requests for m in r.messages for b in m.content if isinstance(b, ToolResultBlock)
    ]
    assert [b for b in results if b.is_error] == []
    assert all("get_logbook" not in tool_names(r) for r in coord)

    assert review_rows(e19.path) == [
        (f"T0{n}", 1, f"S{sid:03d}", None) for n, sid in zip(range(1, 7), (2, 4, 6, 8, 10, 12), strict=True)
    ]
    assert query(e19.path, "SELECT active_cause_id, lifted_at FROM active_causes ORDER BY seq") == [
        (AC1, "S008"),
        (AC2, "S012"),
    ]
    assert query(e19.path, "SELECT active_cause_id, case_id FROM active_cause_links ORDER BY rowid") == [
        (AC1, SE_CASE),
        (AC2, PL_CASE),
        (AC2, PB_CASE),
        (AC2, PE_CASE),
    ]
    assert len(stored_rows(e19.path)) == 20
    assert e19.recorder.calls == [
        ("report", "T01"),
        ("report", "T02"),
        ("alert", alert_id("S005", SE_CASE)),
        ("report", "T03"),
        ("report", "T04"),
        ("alert", alert_id("S010", PL_CASE)),
        ("alert", alert_id("S010", PB_CASE)),
        ("report", "T05"),
        ("alert", alert_id("S011", PE_CASE)),
        ("report", "T06"),
    ]
    s005_alert = notices_of(e19.path, "S005")[alert_id("S005", SE_CASE)]
    assert (s005_alert.causa, s005_alert.evidencia) == (
        Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY),
        (EV_T02,),
    )
    s010_alert = notices_of(e19.path, "S010")[alert_id("S010", PL_CASE)]
    assert (s010_alert.causa, s010_alert.evidencia) == (
        Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY),
        (EV_T05,),
    )

    assert inv[8].system == load_prompt("investigator")
    assert tool_names(inv[8]) == INVESTIGATOR_TOOLS
    assert block_text(inv[8], 0) == render_task(S010_TASK)
    assert tool_names(coord[6]) == COORDINATOR_TOOLS
    s010_brief = block_text(coord[6], 0).split("\n")
    assert [p["case_id"] for p in json.loads(s010_brief[1])["perspectivas"]] == [PL_CASE, PB_CASE]
    block_line = {
        "id": "S010-p1",
        "tipo": "raise",
        "categoria": "parada_de_linea",
        "etapa": "montaje",
        "modelo": "Pickup",
        "mercado": None,
        "bitacora": "T05",
        "fragmento": F5,
        "estado_causa": "activa_sin_fecha",
    }
    assert s010_brief[3] == json.dumps(block_line, ensure_ascii=False, separators=(",", ":"))

    s011_brief = block_text(coord[8], 0).split("\n")
    s011 = json.loads(s011_brief[1])
    assert len(s011_brief) == 2
    assert [a["case_id"] for a in s011["alertas"]] == [PE_CASE]
    assert s011["novedades"] == []
    assert s011["perspectivas"] == [
        {
            "case_id": PE_CASE,
            "gap": {"unidades": -6.0, "pct_plan_diario": -20.0, "en_ultimo_informe": None},
            "embarque": {
                "unidades_demoradas": 1,
                "retraso_dias": 0.0,
                "embarque_asignado": "EUR-0305",
                "embarque_alcanzable": "EUR-0305",
            },
            "cuello": {"etapa": "montaje"},
        }
    ]

    lines = trace_of(e19.root)
    assert list(lines) == list(ALL)
    reasons = {
        "no_text_needed": ("S001", "S003", "S007", "S009"),
        "investigator_only": ("S002",),
        "proposals": ("S004", "S008"),
        "text_needed": ("S005", "S006", "S010", "S011", "S012"),
    }
    for reason, sids in reasons.items():
        for sid in sids:
            kind = "skip" if reason == "no_text_needed" else "call"
            assert (lines[sid].decision, lines[sid].decision_reason) == (kind, reason)
    applied = {"S004": ["S004-p1"], "S008": ["S008-p1"], "S010": ["S010-p1"], "S012": ["S012-p1"]}
    closings = {"S002": "T01", "S004": "T02", "S006": "T03", "S008": "T04", "S010": "T05", "S012": "T06"}
    for sid, line in lines.items():
        assert (line.proposals_applied, line.proposals_declined) == (applied.get(sid, []), [])
        if sid in closings:
            assert line.investigator is not None
            assert (line.investigator.outcome, line.investigator.marks) == (
                "done",
                {closings[sid]: "revisada"},
            )
        else:
            assert line.investigator is None
    assert lines["S011"].agents_run == ["coordinator"]

    totals = run_totals(lines.values())
    assert (totals.snapshots, totals.called, totals.model_calls) == (12, 8, 22)
    assert (totals.input_tokens, totals.output_tokens, totals.usd) == (66_000, 4_400, Decimal("0.0088"))
    investigator, coordinator = totals.by_agent["investigator"], totals.by_agent["coordinator"]
    assert (investigator.runs, investigator.model_calls) == (6, 12)
    assert (investigator.input_tokens, investigator.output_tokens, investigator.usd) == (
        36_000,
        2_400,
        Decimal("0.0048"),
    )
    assert (coordinator.runs, coordinator.model_calls) == (7, 10)
    assert (coordinator.input_tokens, coordinator.output_tokens, coordinator.usd) == (
        30_000,
        2_000,
        Decimal("0.004"),
    )


def test_e20_investigator_outage_aborts_with_its_partial_record_and_a_second_run_resumes_to_e19(
    tmp_path: Path, arrivals: list[Arrival], settings: Settings, e19: Outcome
) -> None:
    """E20, R6, R14, NFR-10: abort in the investigator keeps 'control_errors'; the rerun equals E19."""
    root = tmp_path / "e20"
    outage: list[ModelReply | Exception] = [
        *HEAD,
        out(WRONG_RAISE5, usage=USAGE),
        ModelCallFailed("create", 529),
    ]
    with pytest.raises(RunAborted) as info:
        run_full(root, arrivals, settings, FakeModel(outage), Recorder(), STARTED)
    assert info.value.snapshot_id == "S010"
    assert type(info.value.cause) is ModelCallFailed

    path = root / "registry.sqlite3"
    assert [r[0] for r in query(path, "SELECT active_cause_id FROM active_causes")] == [AC1]
    assert [r[0] for r in query(path, "SELECT active_cause_id FROM active_cause_links")] == [AC1]
    assert query(path, "SELECT case_id FROM cases WHERE case_id LIKE 'S010-%'") == []
    assert [r[0] for r in review_rows(path)] == ["T01", "T02", "T03", "T04"]
    lines = trace_of(root)
    s010 = lines["S010"]
    assert (s010.status, s010.decision, s010.decision_reason, s010.outcome) == (
        "aborted",
        "call",
        "text_needed",
        "skipped",
    )
    assert s010.agents_run == ["investigator"]
    assert s010.investigator is not None
    assert (
        s010.investigator.outcome,
        s010.investigator.logbooks,
        s010.investigator.marks,
        s010.investigator.control_errors,
        len(s010.investigator.model_calls),
    ) == ("aborted:ModelCallFailed", ["T05"], {}, [[FRAGMENT_ERROR]], 1)
    totals = run_totals(lines.values())
    assert (totals.snapshots, totals.called, totals.model_calls) == (10, 6, 15)
    assert (totals.input_tokens, totals.output_tokens, totals.usd) == (45_000, 3_000, Decimal("0.006"))
    investigator, coordinator = totals.by_agent["investigator"], totals.by_agent["coordinator"]
    assert (investigator.runs, investigator.model_calls, investigator.input_tokens) == (5, 9, 27_000)
    assert (investigator.output_tokens, investigator.usd) == (1_800, Decimal("0.0036"))
    assert (coordinator.runs, coordinator.model_calls, coordinator.input_tokens) == (4, 6, 18_000)
    assert (coordinator.output_tokens, coordinator.usd) == (1_200, Decimal("0.0024"))

    run_full(root, arrivals, settings, FakeModel([*S010_JUDGE, *S010_EMIT, *TAIL]), Recorder(), SECOND_START)
    assert stored_rows(path) == stored_rows(e19.path)
    assert out_files(root / "out") == out_files(e19.out)
    assert review_rows(path) == review_rows(e19.path)
    assert [r for r in review_rows(path) if r[0] == "T05"] == [("T05", 1, "S010", None)]


def test_e21_control_failures_correct_once_fall_back_and_give_up_after_two_attempts(
    tmp_path: Path, arrivals: list[Arrival], settings: Settings
) -> None:
    """E21a, R5-R7: S006 corrected, S010 rejected twice, S011 turn cap and given up, S012 reads only T06."""
    s006 = [
        out(lift_proposal(AC1, "T03", F3, "con_fecha"), usage=USAGE),
        NONE,
        turn(1, report("S006", SE_CASE)),
    ]
    undeclared = set_cause_proposal(PL_CASE, "no_declarada", "T05", F5, "activa_sin_fecha")
    s010 = [
        out(WRONG_RAISE5, usage=USAGE),
        out(undeclared, usage=USAGE),
        turn(1, report("S010", PL_CASE, PB_CASE)),
    ]
    s011_turns = [turn(n, logbook("T05")) for n in range(1, 5)]
    script = [*S002, *S004, *S005, *s006, *S008, *s010, *s011_turns, *S012_NO_CAUSE]
    root = tmp_path / "e21"
    model = FakeModel(script)
    run_full(root, arrivals, settings, model, Recorder(), STARTED)
    path = root / "registry.sqlite3"
    inv, coord = split_requests(model)
    assert (len(inv), len(coord)) == (15, 8)
    lines = trace_of(root)

    s006_retry = inv[5].messages[-1].content[0]
    assert isinstance(s006_retry, TextBlock)
    assert s006_retry.text == "\n".join(
        [CORRECTION_HEADER, "- propuestas[0]: lift needs estado_causa resuelta, got con_fecha"]
    )
    assert lines["S006"].investigator is not None
    assert (lines["S006"].investigator.outcome, lines["S006"].investigator.marks) == (
        "done",
        {"T03": "revisada"},
    )
    assert query(path, "SELECT active_cause_id, lifted_at FROM active_causes") == [(AC1, "S008")]

    retry = inv[9].messages[-1].content[0]
    assert isinstance(retry, TextBlock)
    assert retry.text == "\n".join([CORRECTION_HEADER, f"- {FRAGMENT_ERROR}"])
    s010_line = lines["S010"].investigator
    assert s010_line is not None
    assert s010_line.outcome == "fallback:invalid_output"
    assert s010_line.control_errors == [[FRAGMENT_ERROR], [UNDECLARED_ERROR]]
    assert (lines["S010"].decision, lines["S010"].decision_reason) == ("call", "text_needed")
    assert s010_line.marks == {"T05": "reintento"}
    assert at_s010(path) == [
        (PB_CASE, CaseState.OPEN.value, Severity.MEDIUM.value),
        (PL_CASE, CaseState.OPEN.value, Severity.MEDIUM.value),
    ]
    for notice in notices_of(path, "S010").values():
        assert notice.notice_id == news_id("S010", notice.case_id)
        assert (notice.causa, notice.evidencia) == (
            Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY),
            (),
        )

    s011_task = task_of(inv[10])
    assert s011_task["bitacoras"] == ["T05"]
    assert task_case_ids(inv[10]) == [PL_CASE, PB_CASE, PE_CASE]
    s011 = lines["S011"]
    assert s011.investigator is not None
    assert s011.investigator.outcome == "fallback:turn_cap"
    assert (s011.decision_reason, s011.agents_run) == ("investigator_only", ["investigator"])
    assert s011.investigator.marks == {"T05": "sin_revisar"}
    assert [r for r in review_rows(path) if r[0] == "T05"] == [("T05", 2, None, "S011")]
    assert task_of(inv[14])["bitacoras"] == ["T06"]


def test_e22_a_missing_logbook_skips_the_investigator_and_is_retried_then_given_up(
    tmp_path: Path, arrivals: list[Arrival], settings: Settings
) -> None:
    """E22, R8, Q-52: no investigator request at S010 or S011; 'reintento', 'sin_revisar'; S012 reads T06."""
    data = tmp_path / "data22"
    copy_incident_logbooks(data / "bitacoras", omit=("T05",))
    script = [*HEAD, turn(1, report("S010", PL_CASE, PB_CASE)), turn(1, logbook("T06")), *S012_NO_CAUSE]
    root = tmp_path / "e22"
    model = FakeModel(script)
    run_full(root, arrivals, settings.model_copy(update={"data_dir": data}), model, Recorder(), STARTED)
    inv, _ = split_requests(model)
    assert {task_of(r)["snapshot_id"] for r in inv} == {"S002", "S004", "S006", "S008", "S012"}
    assert task_of(inv[-1])["bitacoras"] == ["T06"]
    lines = trace_of(root)
    s010 = lines["S010"]
    assert s010.decision_reason == "text_needed"
    assert s010.investigator is not None
    assert (
        s010.investigator.outcome,
        s010.investigator.logbooks,
        s010.investigator.missing,
        s010.investigator.marks,
    ) == ("skipped", [], ["T05"], {"T05": "reintento"})
    for notice in notices_of(root / "registry.sqlite3", "S010").values():
        assert notice.causa is not None
        assert notice.causa.categoria is CauseCategory.UNDECLARED
    s011 = lines["S011"]
    assert (s011.decision, s011.decision_reason) == ("skip", "no_text_needed")
    assert s011.investigator is not None
    assert s011.investigator.marks == {"T05": "sin_revisar"}


@pytest.mark.parametrize(
    ("second", "requests", "applied", "declined", "causes"),
    [
        pytest.param(
            [turn(2, apply("S010-p1")), S010_EMIT[0]], 3, ["S010-p1"], [], 1, id="a-apply-after-the-texts"
        ),
        pytest.param([end("Declino la propuesta.", USAGE)], 2, [], ["S010-p1"], 0, id="b-real-decline"),
    ],
)
def test_e26_texts_before_apply_proposal_do_not_end_the_coordinator_loop(
    tmp_path: Path,
    arrivals: list[Arrival],
    settings: Settings,
    second: list[ModelReply],
    requests: int,
    applied: list[str],
    declined: list[str],
    causes: int,
) -> None:
    """E26, R11, Q-53: an early report text leaves the unapplied proposal to be applied or declined."""
    judge = [turn(1, logbook("T05")), out(RAISE5, usage=USAGE)]
    first = turn(1, report("S010", PL_CASE, PB_CASE))
    root = tmp_path / "e26"
    model = FakeModel([*HEAD, *judge, first, *second])
    run_full(root, arrivals[:10], settings, model, Recorder(), STARTED)
    path = root / "registry.sqlite3"
    _, coord = split_requests(model)
    assert len(coord[6:]) == requests
    line = trace_of(root)["S010"]
    assert (line.outcome, line.proposals_applied, line.proposals_declined) == ("done", applied, declined)
    assert line.investigator is not None
    assert line.investigator.marks == {"T05": "revisada"}
    links = query(path, "SELECT active_cause_id, case_id FROM active_cause_links WHERE linked_at = 'S010'")
    assert len(links) == causes * 2
    if causes:
        assert {r[0] for r in links} == {"S010-causa-1"}
        assert {alert_id("S010", PL_CASE), alert_id("S010", PB_CASE)} <= set(notices_of(path, "S010"))


def test_e24_a_coordinator_fallback_at_the_pickup_stop_leaves_the_logbook_for_the_next_snapshot(
    tmp_path: Path, arrivals: list[Arrival], settings: Settings
) -> None:
    """E24, R7, Q-53, X1: a coordinator turn cap at S010 is a failed attempt; S011 applies and reviews."""
    s010 = [
        turn(1, logbook("T05")),
        out(RAISE5, usage=USAGE),
        *[turn(n, ("get_deviations", {})) for n in range(1, 9)],
    ]
    s011_script = [
        out(RAISE5, usage=USAGE),
        turn(1, apply("S011-p1")),
        turn(2, alert("S011", PL_CASE), alert("S011", PB_CASE), alert("S011", PE_CASE)),
    ]
    root = tmp_path / "e24"
    model = FakeModel([*HEAD, *s010, *s011_script])
    run_full(root, arrivals[:11], settings, model, Recorder(), STARTED)
    path = root / "registry.sqlite3"
    inv, coord = split_requests(model)
    assert (len(inv), len(coord)) == (11, 16)
    lines = trace_of(root)

    line10 = lines["S010"]
    assert line10.investigator is not None
    assert line10.investigator.outcome == "done"
    assert [p["id"] for p in line10.investigator.proposals] == ["S010-p1"]
    assert line10.investigator.marks == {"T05": "reintento"}
    assert (line10.outcome, line10.proposals_applied, line10.proposals_declined) == (
        "fallback:turn_cap",
        [],
        ["S010-p1"],
    )
    assert line10.notices_agent == []
    assert {news_id("S010", PL_CASE), news_id("S010", PB_CASE)} <= set(line10.notices_template)
    assert [
        r[0] for r in query(path, "SELECT active_cause_id FROM active_causes WHERE opened_at = 'S010'")
    ] == []
    assert at_s010(path) == [
        (PB_CASE, CaseState.OPEN.value, Severity.MEDIUM.value),
        (PL_CASE, CaseState.OPEN.value, Severity.MEDIUM.value),
    ]
    for notice in notices_of(path, "S010").values():
        assert (notice.origen, notice.causa) == (
            Origin.THRESHOLD,
            Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY),
        )

    s011_task = task_of(inv[10])
    assert s011_task["bitacoras"] == ["T05"]
    assert task_case_ids(inv[10]) == [PL_CASE, PB_CASE, PE_CASE]
    line11 = lines["S011"]
    assert line11.decision_reason == "proposals"
    assert query(
        path,
        "SELECT active_cause_id, case_id FROM active_cause_links WHERE linked_at >= 'S010' ORDER BY rowid",
    ) == [
        ("S011-causa-1", PL_CASE),
        ("S011-causa-1", PB_CASE),
        ("S011-causa-1", PE_CASE),
    ]
    alerts = notices_of(path, "S011")
    for case_id in (PL_CASE, PB_CASE, PE_CASE):
        assert alerts[alert_id("S011", case_id)].motivo == (Reason.LOGBOOK,)
    assert [r for r in review_rows(path) if r[0] == "T05"] == [("T05", 2, "S011", None)]
