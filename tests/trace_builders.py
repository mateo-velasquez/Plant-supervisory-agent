"""Hand-built inputs for the 013 trace view and renderer tests (no CLI helpers)."""

import contextlib
import io
import shutil
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

import pytest
from cli_builders import cli_deps, cli_settings, write_cli_data
from judgment_builders import PB_CASE, PL_CASE
from multi_agent_builders import ALL, HEAD, S010_JUDGE, STARTED, alert, logbook, report, turn

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.config import Settings
from plant_monitor.domain.cases import CaseHistoryRow, CaseState
from plant_monitor.domain.causes import ActiveCause, Cause, CauseCategory, CauseScope, CitedCause, Evidence
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import Notice, NoticeType, Origin, Reason, notice_id_for
from plant_monitor.domain.stored import StoredNotice
from plant_monitor.runner.cli import main
from plant_monitor.telemetry.trace import TraceFile, TraceLine, TraceToolCall

from builders import combination_of


def history_row(
    case_id: str,
    snapshot_id: str,
    state: CaseState = CaseState.FOLLOW_UP,
    minimum: Severity = Severity.MEDIUM,
    raised: bool = False,
    *,
    gap_units: float = -4.0,
    gap_pct: float | None = -13.3,
    delay_days: float | None = 0.0,
    bottleneck: Stage | None = Stage.ASSEMBLY,
) -> CaseHistoryRow:
    """A history row with visible metrics."""
    return CaseHistoryRow(
        case_id=case_id,
        snapshot_id=snapshot_id,
        state=state,
        minimum_severity=minimum,
        raised=raised,
        gap_units=gap_units,
        gap_pct=gap_pct,
        delay_days=delay_days,
        bottleneck=bottleneck,
        clean_streak=0,
    )


def active_cause(
    active_cause_id: str,
    opened_at: str,
    evidence: Evidence,
    categoria: CauseCategory,
    scope: CauseScope,
) -> ActiveCause:
    """An active cause still in force."""
    return ActiveCause(
        active_cause_id=active_cause_id,
        categoria=categoria,
        scope=scope,
        opened_at=opened_at,
        opened_by=evidence,
    )


def agent_alert(snapshot_id: str, case_id: str, texto: str, evidencia: Sequence[Evidence]) -> Notice:
    """An agent-set 'alerta_inmediata' with a cited cause."""
    combo = combination_of(case_id)
    return Notice(
        notice_id=notice_id_for(snapshot_id, NoticeType.ALERT, case_id),
        snapshot_id=snapshot_id,
        case_id=case_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        tipo=NoticeType.ALERT,
        severidad=Severity.CRITICAL,
        severidad_maxima=Severity.CRITICAL,
        estado=CaseState.ESCALATED,
        origen=Origin.AGENT,
        motivo=(Reason.LOGBOOK,),
        causa=Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY),
        evidencia=tuple(evidencia),
        texto=texto,
    )


def tool_call(
    turn: int, name: str, arguments: Mapping[str, object], *, error: str | None = None
) -> TraceToolCall:
    """A traced tool call; 'error' makes it a failed one."""
    return TraceToolCall.model_validate(
        {
            "turn": turn,
            "name": name,
            "arguments": dict(arguments),
            "is_error": error is not None,
            "result_chars": 0,
            "error": error,
            "latency_ms": 0,
        }
    )


def apply_call(turn: int, proposal_id: str, *, error: str | None = None) -> TraceToolCall:
    """A coordinator 'apply_proposal' call."""
    return tool_call(turn, "apply_proposal", {"propuesta": proposal_id}, error=error)


def committed_line(
    snapshot_id: str,
    *,
    status: str = "committed",
    decision: str = "call",
    decision_reason: str | None = "text_needed",
    coordinator_calls: Sequence[TraceToolCall] = (),
    proposals: Sequence[Mapping[str, object]] | None = None,
    hooks: Sequence[Mapping[str, object]] = (),
    notices_agent: Sequence[str] = (),
    notices_template: Sequence[str] = (),
) -> TraceLine:
    """A trace line with defaults; 'proposals' (not None) adds an investigator entry and runs both agents."""
    investigator = (
        None
        if proposals is None
        else {
            "outcome": "done",
            "logbooks": [],
            "missing": [],
            "marks": {},
            "proposals": [dict(p) for p in proposals],
            "control_errors": [],
            "model_calls": [],
            "tool_calls": [],
            "thinking": [],
            "totals": {},
            "trigger": "review",
        }
    )
    return TraceLine.model_validate(
        {
            "snapshot_id": snapshot_id,
            "turno_id": "T01",
            "status": status,
            "decision": decision,
            "decision_reason": decision_reason,
            "outcome": "done",
            "required": [],
            "model_calls": [],
            "tool_calls": list(coordinator_calls),
            "thinking": [],
            "notices_agent": list(notices_agent),
            "notices_template": list(notices_template),
            "report_id": None,
            "totals": {},
            "hooks": [dict(h) for h in hooks],
            "agents_run": ["coordinator"] if proposals is None else ["investigator", "coordinator"],
            "investigator": investigator,
        }
    )


def trace_file(name: str, *lines: TraceLine) -> TraceFile:
    """A trace file by name."""
    return TraceFile(name=name, lines=tuple(lines))


def stored(
    notice: Notice,
    history: Sequence[CaseHistoryRow],
    causes: Sequence[ActiveCause] = (),
    links: Mapping[str, str] | None = None,
    cited: CitedCause | None = None,
    order: Mapping[str, int] | None = None,
) -> StoredNotice:
    """A 'StoredNotice'; 'order' defaults to the rows' snapshots in order."""
    return StoredNotice(
        notice=notice,
        history=tuple(history),
        order=order if order is not None else {row.snapshot_id: n for n, row in enumerate(history, start=1)},
        causes=tuple(causes),
        links=links if links is not None else {},
        cited=cited,
    )


# --- T3: CLI integration builders ---

S010_EMIT_HOOKED = [
    turn(2, logbook("T05")),
    turn(3, alert("S010", PL_CASE), alert("S010", PB_CASE), report("S010", PL_CASE, PB_CASE)),
]
PRICES: dict[str, Decimal] = {
    "price_input_per_mtok": Decimal("0.10"),
    "price_output_per_mtok": Decimal("0.50"),
    "price_cache_read_per_mtok": Decimal("0.01"),
    "price_cache_write_5m_per_mtok": Decimal("0.125"),
    "price_cache_write_1h_per_mtok": Decimal("0.20"),
}


def _quiet_run(settings: Settings, argv: list[str], model: FakeModel | None) -> None:
    """Run the CLI with its output swallowed, expecting exit 0."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        assert main(argv, deps=cli_deps(settings, model, now=STARTED, sleep=lambda _s: None)) == 0


@pytest.fixture(scope="module")
def agent_dir(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """The spec's AGENT_DIR: ten snapshots through the agents, scripted with 'S010_EMIT_HOOKED'."""
    root = tmp_path_factory.mktemp("agent_dir")
    data = write_cli_data(root / "data", ALL[:10])
    settings = cli_settings(data, root / "out", **PRICES)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(root)
        _quiet_run(settings, ["run"], FakeModel([*HEAD, *S010_JUDGE, *S010_EMIT_HOOKED]))
    return settings


@pytest.fixture(scope="module")
def thresholds_dir(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """The spec's TH_DIR: the twelve snapshots by thresholds only, no key."""
    root = tmp_path_factory.mktemp("thresholds_dir")
    data = write_cli_data(root / "data", ALL)
    settings = cli_settings(data, root / "out", anthropic_api_key=None)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(root)
        _quiet_run(settings, ["run", "--thresholds-only"], None)
    return settings


def copied(settings: Settings, tmp: Path) -> Settings:
    """Settings over a copy of 'output_dir' under 'tmp', for tests that mutate it."""
    target = tmp / "out"
    shutil.copytree(settings.output_dir, target)
    return settings.model_copy(update={"output_dir": target})


def traced(settings: Settings, notice_id: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run 'plant-monitor trace' with no model; return the exit code, stdout and stderr."""
    capsys.readouterr()
    code = main(["trace", notice_id], deps=cli_deps(settings, None))
    captured = capsys.readouterr()
    return code, captured.out, captured.err
