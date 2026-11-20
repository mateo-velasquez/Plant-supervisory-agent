"""014 T6-T7: 'build_state' header, timeline, cells, KPIs, cost and feed (R3-R7, R13; E1-E6, E15)."""

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import trace_builders
from dashboard_builders import run_rows, run_view
from incident_runs import F5
from trace_builders import copied, history_row

from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.cases.registry.run_reader import CaseRow, HistoryAt, NoticeAt, ProcessedRow
from plant_monitor.config import Settings
from plant_monitor.dashboard.payloads import StatePayload
from plant_monitor.dashboard.source import Calendar, RunView, load_view
from plant_monitor.dashboard.state import build_state
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination
from plant_monitor.domain.notices import Notice, report_id_for
from plant_monitor.ingestion.plant import load_shifts

from builders import isolate_settings_env
from notice_builders import alert_notice

agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir

PL_ALERT_S010 = "S010-alerta_inmediata-S010-Pickup-Local"
PL_ALERT_S012 = "S012-alerta_inmediata-S010-Pickup-Local"
TRACE_FILE = "trace-20260302T230000Z.jsonl"
type State = dict[str, Any]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _load(settings: Settings) -> tuple[RunView, Calendar]:
    """The view and calendar of a run under the policy its settings give."""
    shifts = load_shifts(settings.plant_dir / "turnos.csv")
    policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
    return load_view(settings.registry_path, settings.traces_dir, policy), Calendar.load(
        settings.plant_dir, policy
    )


def _build(view: RunView, calendar: Calendar, at: int | None = None) -> State:
    """The state payload as the client parses it, at the position 'at' resolves to."""
    payload: StatePayload = build_state(view, calendar, view.resolve_at(at))
    state: State = json.loads(json.dumps(payload))
    return state


def _state(settings: Settings, at: int | None = None) -> State:
    view, calendar = _load(settings)
    return _build(view, calendar, at)


def _cell(state: State, modelo: str, mercado: str) -> State:
    cell: State = next(c for c in state["cells"] if (c["modelo"], c["mercado"]) == (modelo, mercado))
    return cell


def _feed_ids(state: State) -> list[str]:
    return [item["notice_id"] if item["kind"] == "alert" else item["report_id"] for item in state["feed"]]


def _snapshots(state: State) -> dict[str, State]:
    return {
        s["snapshot_id"]: s for day in state["days"] for shift in day["shifts"] for s in shift["snapshots"]
    }


@pytest.mark.parametrize(("arg", "effective"), [(None, 12), (5, 5), (0, 0), (99, 12)])
def test_e1_position_resolves_and_zero_is_an_empty_plant(
    thresholds_dir: Settings, arg: int | None, effective: int
) -> None:
    """014 E1 (R3): 'at' and 'latest'; every position is listed; at 0 nothing is shown."""
    state = _state(thresholds_dir, arg)
    assert (state["at"], state["latest"]) == (effective, 12)
    assert state["positions"] == list(range(1, 13))
    if effective == 0:
        assert state["current"] is None
        assert {c["status"] for c in state["cells"]} == {"calm"}
        assert state["feed"] == []


def test_e2_replay_as_of_n_shows_the_case_cause_and_feed_of_that_position(thresholds_dir: Settings) -> None:
    """014 E2 (R3, R6, R7): Pickup x Local at 9, 11 and 12."""
    view, calendar = _load(thresholds_dir)
    at9 = _cell(_build(view, calendar, 9), "Pickup", "Local")
    assert (at9["status"], at9["case"]) == ("calm", None)

    at11 = _build(view, calendar, 11)
    case = _cell(at11, "Pickup", "Local")["case"]
    assert _cell(at11, "Pickup", "Local")["status"] == "active"
    assert (case["case_id"], case["estado"], case["opened_at"]) == (
        "S010-Pickup-Local",
        "en_seguimiento",
        "S010",
    )
    assert PL_ALERT_S012 not in _feed_ids(at11)

    at12 = _build(view, calendar, 12)
    cell = _cell(at12, "Pickup", "Local")
    case = cell["case"]
    assert cell["status"] == "active"
    assert (case["estado"], case["severidad"], case["gap_unidades"]) == ("escalado", "critica", -11.0)
    assert round(case["gap_pct"], 1) == -36.7
    assert (case["etapa_cuello"], case["causa"], case["etapa"]) == (None, "no_declarada", None)
    assert len(cell["series"]) == 12
    assert cell["series"][:9] == [None] * 9
    assert cell["series"][11] == -11.0
    expected = [
        item.notice_id if isinstance(item, Notice) else report_id_for(item.turno_id)
        for item in reversed(read_deliverables(thresholds_dir.registry_path))
    ]
    assert _feed_ids(at12) == expected
    assert PL_ALERT_S012 in expected


def test_e3_timeline_groups_shifts_by_day_and_marks_processed_alerts_and_reports(
    thresholds_dir: Settings,
) -> None:
    """014 E3 (R4): TH_DIR at 11, then at 12."""
    view, calendar = _load(thresholds_dir)
    state = _build(view, calendar, 11)
    assert [(d["label"], [s["turno_id"] for s in d["shifts"]]) for d in state["days"]] == [
        ("3/2/2026", ["T01", "T02", "T03"]),
        ("3/3/2026", ["T04", "T05", "T06"]),
    ]
    cells = _snapshots(state)
    assert [sid for sid, c in cells.items() if c["processed"]] == [f"S{n:03d}" for n in range(1, 12)]
    assert [sid for sid, c in cells.items() if c["report"]] == ["S002", "S004", "S006", "S008", "S010"]
    assert (state["current"]["snapshot_id"], state["current"]["turno_id"]) == ("S011", "T06")
    assert (state["total"], state["complete"]) == (12, False)
    assert cells["S012"]["alerts"] == 0
    assert [c["seq"] for c in cells.values()] == [*range(1, 12), None]

    last = _build(view, calendar, 12)
    assert _snapshots(last)["S012"]["seq"] == 12
    assert last["complete"] is True
    assert _snapshots(last)["S012"]["alerts"] == 3


def test_e5_cell_states_cause_as_of_n_and_the_same_seq_tie_break(thresholds_dir: Settings) -> None:
    """014 E5 (R6; FR-18): calm, active, resolved, cause as of N, sparkline holes and the tie-break."""
    calendar = _load(thresholds_dir)[1]
    suv = Combination(modelo=Model.SUV, mercado=Market.EUROPE)
    sedan = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
    suv_case, sedan_case, late_case = "S005-SUV-Europa", "S006-Sedán-Local", "S009-SUV-Europa"
    esc, fol = CaseState.ESCALATED, CaseState.FOLLOW_UP
    history = [
        HistoryAt(
            5,
            history_row(
                suv_case,
                "S005",
                esc,
                Severity.HIGH,
                True,
                gap_units=-4.0,
                delay_days=1.5,
                bottleneck=Stage.QUALITY,
            ),
        ),
        HistoryAt(
            6,
            history_row(suv_case, "S006", fol, Severity.HIGH, True, gap_units=-2.0, bottleneck=Stage.QUALITY),
        ),
        HistoryAt(7, history_row(suv_case, "S007", fol, Severity.HIGH, True, gap_units=0.0, bottleneck=None)),
        HistoryAt(8, history_row(suv_case, "S008", CaseState.RESOLVED, gap_units=0.0, bottleneck=None)),
        HistoryAt(6, history_row(sedan_case, "S006", CaseState.OPEN)),
    ]
    late = HistoryAt(8, history_row(late_case, "S009", CaseState.OPEN))
    cause = Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY)
    notice = alert_notice("S005", suv_case).model_copy(update={"causa": cause})
    cases = [CaseRow(suv_case, suv, "S005"), CaseRow(sedan_case, sedan, "S006")]
    processed = [ProcessedRow(f"S{n:03d}", n) for n in range(1, 10)]

    def build(at: int, *, boundary: bool) -> State:
        rows = run_rows(
            processed,
            [*cases, CaseRow(late_case, suv, "S009")] if boundary else cases,
            [*history, late] if boundary else history,
            [NoticeAt(5, 0, notice)],
        )
        return _build(run_view(rows), calendar, at)

    assert _cell(build(4, boundary=False), "SUV", "Europa")["status"] == "calm"
    at5 = _cell(build(5, boundary=False), "SUV", "Europa")
    assert (at5["status"], at5["case"]["severidad"]) == ("active", "critica")
    assert (at5["case"]["causa"], at5["case"]["etapa"]) == ("retencion_de_calidad", "calidad")
    assert (at5["case"]["retraso_dias"], at5["case"]["etapa_cuello"]) == (1.5, "calidad")
    at8 = _cell(build(8, boundary=False), "SUV", "Europa")
    assert (at8["status"], at8["case"]["resolved_at"]) == ("resolved", "S008")
    assert at8["series"] == [None, None, None, None, -4.0, -2.0, 0.0, 0.0]
    tie = _cell(build(8, boundary=True), "SUV", "Europa")
    assert (tie["status"], tie["case"]["case_id"]) == ("active", late_case)
    sedan_cell = _cell(build(6, boundary=False), "Sedán", "Local")
    assert sedan_cell["status"] == "active"
    assert (sedan_cell["case"]["causa"], sedan_cell["case"]["etapa"]) == ("no_declarada", "montaje")


@pytest.mark.parametrize("same_opened_at", [False, True])
def test_e5_two_cases_tied_on_seq_and_opened_at_or_both_active_raise(
    thresholds_dir: Settings, same_opened_at: bool
) -> None:
    """014 E5 (R6): a tie with two active cases, or two cases sharing 'opened_at', raises 'ValueError'."""
    calendar = _load(thresholds_dir)[1]
    suv = Combination(modelo=Model.SUV, mercado=Market.EUROPE)
    first, second = "S005-SUV-Europa", "S006-SUV-Europa"
    state = CaseState.FOLLOW_UP if not same_opened_at else CaseState.RESOLVED
    rows = run_rows(
        [ProcessedRow(f"S{n:03d}", n) for n in range(1, 8)],
        [CaseRow(first, suv, "S005"), CaseRow(second, suv, "S005" if same_opened_at else "S006")],
        [HistoryAt(7, history_row(first, "S007", state)), HistoryAt(7, history_row(second, "S007", state))],
    )
    with pytest.raises(ValueError, match=r"\Adashboard: "):
        _build(run_view(rows), calendar, 7)


@pytest.mark.parametrize(
    ("at", "alerts", "reports", "active", "critical", "calls", "usd", "tokens"),
    [
        (5, 1, 2, 1, {"SUV × Europa"}, 7, "0.00280000", 22400),  # noqa: RUF001
        (10, 3, 5, 2, {"Pickup × Local", "Pickup × Brasil"}, 19, "0.00760000", 60800),  # noqa: RUF001
    ],
)
def test_e4_kpis_and_cost_as_of_n(
    agent_dir: Settings,
    at: int,
    alerts: int,
    reports: int,
    active: int,
    critical: set[str],
    calls: int,
    usd: str,
    tokens: int,
) -> None:
    """014 E4 (R5; FR-37): AGENT_DIR at 5 and at 10."""
    kpis = _state(agent_dir, at)["kpis"]
    assert (kpis["alerts"], kpis["reports"], kpis["active"], kpis["combinations"]) == (
        alerts,
        reports,
        active,
        9,
    )
    assert kpis["critical"] == len(critical)
    assert set(kpis["critical_combinations"]) == critical
    assert kpis["cost"] == {"usd": usd, "model_calls": calls, "tokens": tokens}


def test_q97_cost_counts_aborted_lines_and_those_of_uncommitted_snapshots_only_at_latest(
    agent_dir: Settings,
) -> None:
    """Risk: 014 R5 (Q-97): an aborted line of a never-committed snapshot is billed only at 'latest'."""
    view, calendar = _load(agent_dir)
    retried = view.committed["S004"].model_copy(update={"status": "aborted"})
    orphan = view.committed["S010"].model_copy(update={"snapshot_id": "S011", "status": "aborted"})
    extra = (("trace-extra.jsonl", retried), ("trace-extra.jsonl", orphan))
    patched = replace(
        view,
        lines=(*view.lines, *extra),
        aborted={"S004": (extra[0],), "S011": (extra[1],)},
    )
    at5 = _build(patched, calendar, 5)["kpis"]["cost"]
    latest = _build(patched, calendar, 10)["kpis"]["cost"]
    assert (at5["model_calls"], at5["usd"]) == (7 + 4, "0.00440000")
    assert (latest["model_calls"], latest["usd"]) == (19 + 4 + 5, "0.01120000")


def test_e6_feed_item_shows_its_text_author(
    agent_dir: Settings, thresholds_dir: Settings, tmp_path: Path
) -> None:
    """014 E6 (R7; Q-77): (a) agent author, (b) template without traces, (c) unknown without its line."""
    items = {i["notice_id"]: i for i in _state(agent_dir, 10)["feed"] if i["kind"] == "alert"}
    item = items[PL_ALERT_S010]
    assert item["texto"] == f"Agente: {PL_ALERT_S010}"
    assert item["author"] == "agent"
    assert item["motivo"] == ["bitacora"]
    assert item["origen"] == "agente"
    assert item["causa"] == {"categoria": "parada_de_linea", "etapa": "montaje"}
    assert [(e["bitacora"], e["fragmento"]) for e in item["evidencia"]] == [("T05", F5)]
    assert item["snapshot_id"] == "S010"
    stored = next(
        n
        for n in read_deliverables(agent_dir.registry_path)
        if isinstance(n, Notice) and n.notice_id == PL_ALERT_S010
    )
    assert item["severidad_maxima"] == stored.severidad_maxima.value

    template = next(i for i in _state(thresholds_dir, 12)["feed"] if i.get("notice_id") == PL_ALERT_S012)
    assert template["author"] == "template"

    settings = copied(agent_dir, tmp_path)
    path = settings.traces_dir / TRACE_FILE
    kept = [
        ln for ln in path.read_bytes().splitlines(keepends=True) if json.loads(ln)["snapshot_id"] != "S010"
    ]
    path.write_bytes(b"".join(kept))
    stripped = next(i for i in _state(settings, 10)["feed"] if i.get("notice_id") == PL_ALERT_S010)
    assert stripped["author"] == "unknown"


def test_e15_closed_guard_hides_the_held_out_shift_from_the_state(thresholds_dir: Settings) -> None:
    """014 E15 (R13, R4): state part with the guard closed from T06."""
    closed = thresholds_dir.model_copy(update={"heldout_open": False})
    state = _state(closed)
    assert (state["latest"], state["total"]) == (10, 10)
    assert state["positions"] == list(range(1, 11))
    assert "T06" not in [s["turno_id"] for day in state["days"] for s in day["shifts"]]
    hidden = sum(
        item.snapshot_id in {"S011", "S012"} for item in read_deliverables(thresholds_dir.registry_path)
    )
    assert hidden >= 2
    assert state["heldout"] == {
        "open": False,
        "omitted": {"snapshots": 2, "notices": hidden, "trace_lines": 0},
    }
    body = json.dumps(state)
    assert not [token for token in ("S011", "S012", "T06") if token in body]
