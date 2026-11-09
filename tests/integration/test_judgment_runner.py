"""008 T12: IF series through the agent pipeline with judgment and a file-backed registry (E21, E22, E33)."""

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from agent_builders import end, tools_reply
from draft_builders import agent_text
from incident_builders import INCIDENTS, incident_context, incident_shifts, write_incident_series
from incident_runs import AC1, AC2, EV_T02, EV_T05, F2, F4, F5, F6

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelCallFailed, ModelReply, ToolResultBlock
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
from plant_monitor.runner.pipeline import SnapshotDecision, ThresholdPipeline
from plant_monitor.runner.post_commit import PostCommitChain
from plant_monitor.runner.series import RunAborted, run_series
from plant_monitor.telemetry.trace import TraceWriter, read_trace, run_totals, trace_path
from plant_monitor.telemetry.usage import Usage

from builders import isolate_settings_env

SIDS = tuple(f"S{n:03d}" for n in range(1, 13))
CLOCK_TIME = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)
SECOND_START = datetime(2026, 3, 2, 23, 30, tzinfo=UTC)
USAGE = Usage(input_tokens=3000, output_tokens=200)
TRACE_1 = "trace-20260302T230000Z.jsonl"

SE = "S005-SUV-Europa"
PL = "S010-Pickup-Local"
PB = "S010-Pickup-Brasil"
PE = "S011-Pickup-Europa"
QUALITY_HOLD = Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY)
LINE_STOP = Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY)
RAISE_AC1: dict[str, object] = {
    "categoria": "retencion_de_calidad",
    "etapa": "calidad",
    "modelo": "SUV",
    "mercado": "Europa",
    "bitacora": "T02",
    "fragmento": F2,
}
RAISE_AC2: dict[str, object] = {
    "categoria": "parada_de_linea",
    "etapa": "montaje",
    "modelo": "Pickup",
    "bitacora": "T05",
    "fragmento": F5,
}

type Call = tuple[str, dict[str, object]]
type Delivery = tuple[str, str]
type Rows = list[tuple[str, str, str, str, str | None, str]]


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


def lift(active_cause_id: str, bitacora: str, fragmento: str) -> Call:
    args: dict[str, object] = {
        "active_cause_id": active_cause_id,
        "bitacora": bitacora,
        "fragmento": fragmento,
    }
    return ("lift_severity_raise", args)


def turn(number: int, *calls: Call) -> ModelReply | Exception:
    """The model's reply number 'number' of a snapshot: one or more tool uses in a single reply."""
    return tools_reply(*calls, prefix=f"tu{number}", usage=USAGE)


def raise_call(arguments: dict[str, object]) -> Call:
    return ("raise_severity", arguments)


S002 = [turn(1, logbook("T01")), end("Sin causas.", USAGE)]
S004 = [turn(1, logbook("T02")), turn(2, raise_call(RAISE_AC1)), end("Causa registrada.", USAGE)]
S005 = [turn(1, alert("S005", SE))]
S006 = [turn(1, logbook("T03")), turn(2, report("S006", SE))]
S008 = [turn(1, logbook("T04")), turn(2, lift(AC1, "T04", F4)), turn(3, report("S008", SE))]
S010_JUDGE = [turn(1, logbook("T05")), turn(2, raise_call(RAISE_AC2))]
S010_EMIT = [turn(3, alert("S010", PL), alert("S010", PB), report("S010", PL, PB))]
S011 = [turn(1, alert("S011", PE))]
S012 = [turn(1, logbook("T06")), turn(2, lift(AC2, "T06", F6), report("S012", PE))]
HEAD = [*S002, *S004, *S005, *S006, *S008]
TAIL = [*S011, *S012]


class Recorder:
    """Keeps the '(channel, id)' order of every delivered alert and report."""

    def __init__(self) -> None:
        self.calls: list[Delivery] = []

    def alert(self, notice: Notice) -> None:
        self.calls.append(("alert", notice.notice_id))

    def report(self, report: ShiftReport) -> None:
        self.calls.append(("report", report.turno_id))


@dataclass(frozen=True)
class Outcome:
    """A finished run: where it wrote and what it delivered."""

    path: Path
    out: Path
    trace: Path
    recorder: Recorder
    model: FakeModel


def run_agent(
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
            registry.notices, CompositeNotifier((FileNotifier(root / "out"), recorder)), lambda: CLOCK_TIME
        )
        run_series(
            arrivals, incident_shifts(), registry, pipeline, post_commit=PostCommitChain([trace, outbox])
        )


def stored_rows(path: Path) -> Rows:
    """Every stored notice row of a closed registry file, in processing order."""
    query = "SELECT notice_id, snapshot_id, kind, tipo, case_id, payload FROM notices ORDER BY seq, idx"
    with closing(sqlite3.connect(path)) as conn:
        return [(r[0], r[1], r[2], r[3], r[4], r[5]) for r in conn.execute(query)]


def query(path: Path, sql: str) -> list[tuple[object, ...]]:
    """Rows of a read-only query over a closed registry file."""
    with closing(sqlite3.connect(path)) as conn:
        return [tuple(row) for row in conn.execute(sql)]


def out_files(out: Path) -> dict[str, bytes]:
    """File name to bytes for everything in the output directory."""
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())} if out.exists() else {}


def stored(path: Path) -> tuple[dict[str, Notice], dict[str, ShiftReport]]:
    """Notices (reports' news included) by id, and reports by 'turno_id', read through a fresh registry."""
    notices: dict[str, Notice] = {}
    reports: dict[str, ShiftReport] = {}
    with SqliteRegistry(path) as registry:
        for sid in SIDS:
            for item in registry.notices.for_snapshot(sid):
                if isinstance(item, ShiftReport):
                    reports[item.turno_id] = item
                    notices.update({n.notice_id: n for n in item.novedades})
                else:
                    notices[item.notice_id] = item
    return notices, reports


def tool_results(model: FakeModel) -> list[ToolResultBlock]:
    """Every tool result in the model's last request, in order."""
    return [b for m in model.requests[-1].messages for b in m.content if isinstance(b, ToolResultBlock)]


@pytest.fixture
def arrivals(tmp_path: Path) -> list[Arrival]:
    """IF arrivals S001-S012 written under 'tmp_path'."""
    return write_incident_series(tmp_path / "snapshots", SIDS)


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Default settings with the IF logbooks under 'data_dir'."""
    isolate_settings_env(monkeypatch, tmp_path)
    return Settings(anthropic_api_key="k", data_dir=INCIDENTS)


@pytest.fixture
def e21(tmp_path: Path, arrivals: list[Arrival], settings: Settings) -> Outcome:
    """E21: the whole IF series with the exact script."""
    root = tmp_path / "e21"
    model = FakeModel([*HEAD, *S010_JUDGE, *S010_EMIT, *TAIL])
    recorder = Recorder()
    run_agent(root, arrivals, settings, model, recorder, CLOCK_TIME)
    return Outcome(root / "registry.sqlite3", root / "out", root / "traces" / TRACE_1, recorder, model)


def test_e21_incident_series_raises_and_lifts_causes_and_cites_them_in_the_notices(e21: Outcome) -> None:
    """E21: 17 requests, no tool error; cited notices, rows, deliveries, registry state and trace."""
    assert len(e21.model.requests) == 17
    seen = [b for r in e21.model.requests for m in r.messages for b in m.content]
    assert [b for b in seen if isinstance(b, ToolResultBlock) and b.is_error] == []

    notices, reports = stored(e21.path)
    cited = (QUALITY_HOLD, (EV_T02,))
    for nid in (alert_id("S005", SE), news_id("S006", SE)):
        n = notices[nid]
        assert (n.estado, n.severidad, n.severidad_maxima) == (CaseState.ESCALATED,) + (
            Severity.CRITICAL,
        ) * 2
        assert (n.motivo, n.origen, n.causa, n.evidencia) == ((Reason.LOGBOOK,), Origin.AGENT, *cited)
        assert n.texto == agent_text(nid)
    assert notices[f"S007-{NoticeType.NO_NOTICE}-{SE}"].tipo is NoticeType.NO_NOTICE
    assert (reports["T01"].novedades, reports["T01"].casos_activos) == ((), ())

    resolved = notices[news_id("S008", SE)]
    assert (resolved.estado, resolved.severidad, resolved.severidad_maxima) == (
        CaseState.RESOLVED,
        Severity.NONE,
        Severity.CRITICAL,
    )
    assert (resolved.motivo, resolved.origen, (resolved.causa, resolved.evidencia)) == (
        (),
        Origin.THRESHOLD,
        cited,
    )
    assert reports["T04"].casos_activos == ()

    for case in (PL, PB):
        raised_alert = notices[alert_id("S010", case)]
        assert (raised_alert.motivo, raised_alert.origen) == ((Reason.LOGBOOK,), Origin.AGENT)
        for n in (raised_alert, notices[news_id("S010", case)]):
            assert (n.estado, n.severidad, n.severidad_maxima) == (CaseState.ESCALATED,) + (
                Severity.CRITICAL,
            ) * 2
            assert (n.causa, n.evidencia) == (LINE_STOP, (EV_T05,))
        assert notices[f"S011-{NoticeType.NO_NOTICE}-{case}"].tipo is NoticeType.NO_NOTICE
        assert notices[f"S012-{NoticeType.NO_NOTICE}-{case}"].tipo is NoticeType.NO_NOTICE
    pe_alert = notices[alert_id("S011", PE)]
    assert (pe_alert.motivo, pe_alert.origen, pe_alert.causa, pe_alert.evidencia) == (
        (Reason.LOGBOOK,),
        Origin.AGENT,
        LINE_STOP,
        (EV_T05,),
    )
    pe_news = notices[news_id("S012", PE)]
    assert (pe_news.estado, pe_news.severidad, pe_news.severidad_maxima) == (
        CaseState.ESCALATED,
        Severity.CRITICAL,
        Severity.CRITICAL,
    )
    assert (pe_news.motivo, pe_news.origen) == ((Reason.GAP,), Origin.THRESHOLD)

    assert len(stored_rows(e21.path)) == 20
    assert e21.recorder.calls == [
        ("report", "T01"),
        ("report", "T02"),
        ("alert", alert_id("S005", SE)),
        ("report", "T03"),
        ("report", "T04"),
        ("alert", alert_id("S010", PL)),
        ("alert", alert_id("S010", PB)),
        ("report", "T05"),
        ("alert", alert_id("S011", PE)),
        ("report", "T06"),
    ]

    causes = query(
        e21.path,
        "SELECT active_cause_id, opened_at, opened_bitacora, lifted_at, lifted_bitacora, lifted_fragmento"
        " FROM active_causes ORDER BY seq",
    )
    assert causes == [(AC1, "S004", "T02", "S008", "T04", F4), (AC2, "S010", "T05", "S012", "T06", F6)]
    assert query(
        e21.path, "SELECT active_cause_id, case_id, linked_at FROM active_cause_links ORDER BY rowid"
    ) == [
        (AC1, SE, "S005"),
        (AC2, PL, "S010"),
        (AC2, PB, "S010"),
        (AC2, PE, "S011"),
    ]
    assert len(query(e21.path, "SELECT 1 FROM case_causes")) == 4
    assert query(
        e21.path, f"SELECT minimum_severity FROM case_history WHERE case_id = '{PE}' AND snapshot_id = 'S011'"
    ) == [(Severity.HIGH.value,)]

    lines = read_trace(e21.trace)
    assert [ln.snapshot_id for ln in lines] == list(SIDS)
    reasons = {ln.snapshot_id: (ln.decision, ln.decision_reason) for ln in lines}
    called = {"S002", "S004", "S005", "S006", "S008", "S010", "S011", "S012"}
    closing_review = {"S002", "S004", "S008"}
    for sid, (decision, reason) in reasons.items():
        if sid in closing_review:
            assert (decision, reason) == ("call", "closing_review")
        elif sid in called:
            assert (decision, reason) == ("call", "text_needed")
        else:
            assert decision == "skip"
    s010 = lines[9]
    assert [t.name for t in s010.tool_calls] == [
        "get_logbook",
        "raise_severity",
        "emit_alert",
        "emit_alert",
        "emit_shift_report",
    ]
    assert s010.tool_calls[1].arguments == RAISE_AC2
    totals = run_totals(lines)
    assert (totals.snapshots, totals.called, totals.model_calls) == (12, 8, 17)
    assert (totals.input_tokens, totals.output_tokens, totals.usd) == (51_000, 3_400, Decimal("0.0068"))


def test_e22_model_outage_mid_snapshot_rolls_it_back_and_a_second_run_resumes_to_e21(
    tmp_path: Path, arrivals: list[Arrival], settings: Settings, e21: Outcome
) -> None:
    """E22: S010 aborts at its third request with no cause rows; the rerun equals E21 (X3)."""
    root = tmp_path / "e22"
    outage: list[ModelReply | Exception] = [*HEAD, *S010_JUDGE, ModelCallFailed("create", 529)]
    with pytest.raises(RunAborted) as info:
        run_agent(root, arrivals, settings, FakeModel(outage), Recorder(), CLOCK_TIME)
    assert info.value.snapshot_id == "S010"
    assert type(info.value.cause) is ModelCallFailed

    path = root / "registry.sqlite3"
    assert [r[0] for r in query(path, "SELECT active_cause_id FROM active_causes")] == [AC1]
    assert [r[0] for r in query(path, "SELECT active_cause_id FROM active_cause_links")] == [AC1]
    assert [r[0] for r in query(path, "SELECT case_id FROM case_causes")] == [SE]
    assert query(path, "SELECT case_id FROM cases WHERE case_id LIKE 'S010-%'") == []
    assert "S010" not in {r[1] for r in stored_rows(path)}
    lines = read_trace(root / "traces" / TRACE_1)
    assert (lines[-1].snapshot_id, lines[-1].status, lines[-1].outcome) == (
        "S010",
        "aborted",
        "aborted:ModelCallFailed",
    )
    assert [t.name for t in lines[-1].tool_calls] == ["get_logbook", "raise_severity"]

    model = FakeModel([*S010_JUDGE, *S010_EMIT, *TAIL])
    run_agent(root, arrivals, settings, model, Recorder(), SECOND_START)
    assert stored_rows(path) == stored_rows(e21.path)
    assert out_files(root / "out") == out_files(e21.out)


def test_e33_internal_failure_in_a_judgment_write_closes_writes_and_aborts_the_snapshot(
    tmp_path: Path,
    arrivals: list[Arrival],
    settings: Settings,
    e21: Outcome,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E33 (X4): 'redecide' raises at S010; generic tool error, closed writes, rollback, healthy rerun."""
    root = tmp_path / "e33"
    original = ThresholdPipeline.redecide

    def exploding(self: ThresholdPipeline, decision: SnapshotDecision) -> SnapshotDecision:
        if decision.snapshot.snapshot_id == "S010":
            raise RuntimeError("boom")
        return original(self, decision)

    emit = turn(3, report("S010", PL, PB))
    script = [*HEAD, *S010_JUDGE, emit, end("Listo.", USAGE), end("Sin textos.", USAGE)]
    model = FakeModel(script)
    with monkeypatch.context() as patch:
        patch.setattr(ThresholdPipeline, "redecide", exploding)
        with pytest.raises(RunAborted) as info:
            run_agent(root, arrivals, settings, model, Recorder(), CLOCK_TIME)
    assert info.value.snapshot_id == "S010"
    assert type(info.value.cause) is RuntimeError
    assert str(info.value.cause) == "boom"

    raise_result, emit_result = tool_results(model)[-2:]
    assert (raise_result.is_error, raise_result.content) == (True, "Error executing tool raise_severity")
    assert (emit_result.is_error, emit_result.content) == (
        True,
        "Error executing tool emit_shift_report: writes are closed at S010 after an internal error",
    )

    path = root / "registry.sqlite3"
    assert [r[0] for r in query(path, "SELECT active_cause_id FROM active_causes")] == [AC1]
    assert [r[0] for r in query(path, "SELECT case_id FROM case_causes")] == [SE]
    assert query(path, "SELECT case_id FROM cases WHERE case_id LIKE 'S010-%'") == []
    assert [r for r in stored_rows(path) if r[1] == "S010"] == []
    last = read_trace(root / "traces" / TRACE_1)[-1]
    assert (last.snapshot_id, last.status, last.decision, last.decision_reason) == (
        "S010",
        "aborted",
        "call",
        "text_needed",
    )
    assert [t.name for t in last.tool_calls] == ["get_logbook", "raise_severity", "emit_shift_report"]

    rerun = FakeModel([*S010_JUDGE, *S010_EMIT, *TAIL])
    run_agent(root, arrivals, settings, rerun, Recorder(), SECOND_START)
    assert stored_rows(path) == stored_rows(e21.path)
    assert out_files(root / "out") == out_files(e21.out)
