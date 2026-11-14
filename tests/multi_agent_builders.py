"""Script builders and run helpers shared by the 009 and 010 incident-series integrations."""

import json
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from agent_builders import (
    RAISE2,
    RAISE5,
    end,
    lift_proposal,
    out,
    tools_reply,
)
from draft_builders import agent_text
from incident_builders import (
    incident_context,
    incident_shifts,
    write_incident_series,
)
from incident_runs import AC1, AC2, F4, F6
from judgment_builders import PB_CASE, PL_CASE

from plant_monitor.agents.allowlists import INVESTIGATOR_TOOLS
from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelReply, ModelRequest, TextBlock
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.notices import Notice, NoticeType, ShiftReport
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.notify.composite import CompositeNotifier
from plant_monitor.notify.file import FileNotifier
from plant_monitor.runner.agent_pipeline import build_agent_pipeline
from plant_monitor.runner.outbox import OutboxDispatcher
from plant_monitor.runner.post_commit import PostCommitChain
from plant_monitor.runner.series import run_series
from plant_monitor.telemetry.trace import TraceLine, TraceWriter, read_trace, trace_path
from plant_monitor.telemetry.usage import Usage

from builders import CRIT

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
        pipeline = build_agent_pipeline(
            settings, registry, incident_context(), policy, model, trace, criteria=CRIT
        )
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
            criteria=CRIT,
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
