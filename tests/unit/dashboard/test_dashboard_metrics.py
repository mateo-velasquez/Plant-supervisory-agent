"""015 T4-T5: 'build_metrics' cost, days, authors, noise (R1, R3-R9, R12; E1-E9, E17, E21, E23)."""

import json
from pathlib import Path
from typing import Any

import pytest
import trace_builders
from dashboard_builders import run_rows
from metrics_builders import CAL, call, metric_line, metric_view
from trace_builders import copied

from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.cases.registry.run_reader import NoticeAt, ProcessedRow, RunRows
from plant_monitor.config import Settings
from plant_monitor.dashboard.metrics import build_metrics
from plant_monitor.dashboard.panels import AccuracyPanel, RunsPanel
from plant_monitor.dashboard.payloads import MetricsPayload
from plant_monitor.dashboard.source import Calendar, RunView, cost_as_of, load_view
from plant_monitor.dashboard.state import build_state
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.notices import Notice
from plant_monitor.ingestion.plant import load_shifts

from builders import isolate_settings_env
from notice_builders import PICKUP_LOCAL_CASE, SEDAN_LOCAL_CASE, SUV_LOCAL_CASE, alert_notice, shift_report

agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir

ZERO = "0.00000000"
NO_CALENDAR = Calendar(shifts=(), combinations=())
NO_ACCURACY = AccuracyPanel(state="none", file=None, evaluated_at=None, summary=None, earlier=0, unreadable=0)
NO_RUNS = RunsPanel(items=(), unreadable=0, omitted=0)
type Metrics = dict[str, Any]


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


def _build(view: RunView, calendar: Calendar, at: int | None = None) -> Metrics:
    """The metrics payload as the client parses it, with empty fixed panels."""
    payload: MetricsPayload = build_metrics(view, calendar, view.resolve_at(at), NO_ACCURACY, NO_RUNS)
    metrics: Metrics = json.loads(json.dumps(payload))
    return metrics


def _metrics(settings: Settings, at: int | None = None) -> Metrics:
    view, calendar = _load(settings)
    return _build(view, calendar, at)


def _points(metrics: Metrics) -> dict[str, Metrics]:
    return {p["snapshot_id"]: p for p in metrics["cost"]["points"]}


def _split(point: Metrics) -> tuple[str, str, str]:
    """A point's investigator USD, coordinator USD and cumulative USD."""
    return point["usd"]["investigator"], point["usd"]["coordinator"], point["cumulative_usd"]


def _processed(count: int) -> RunRows:
    """Registry rows with snapshots S001 to S'count' processed at seq 1 to 'count'."""
    return run_rows([ProcessedRow(f"S{n:03d}", n) for n in range(1, count + 1)])


def _state_cost_usd(view: RunView, calendar: Calendar, at: int) -> str:
    cost = build_state(view, calendar, at)["kpis"]["cost"]
    assert cost is not None
    return cost["usd"]


# --- T4 ---


def test_e2_cost_per_snapshot_stacks_the_agents_and_accumulates(agent_dir: Settings) -> None:
    """015 E2 (R3, R4; FR-37): AGENT_DIR at 5 and at 10."""
    view, calendar = _load(agent_dir)
    at5 = _build(view, calendar, 5)
    assert [_split(p) for p in at5["cost"]["points"]] == [
        (ZERO, ZERO, ZERO),
        ("0.00080000", ZERO, "0.00080000"),
        (ZERO, ZERO, "0.00080000"),
        ("0.00080000", "0.00080000", "0.00240000"),
        (ZERO, "0.00040000", "0.00280000"),
    ]
    assert [p["seq"] for p in at5["cost"]["points"]] == [1, 2, 3, 4, 5]
    totals = at5["cost"]["totals"]
    assert (totals["usd"], totals["model_calls"]) == ("0.00280000", 7)
    assert totals["usd"] == _state_cost_usd(view, calendar, 5)
    assert at5["cost"]["unplaced_usd"] == ZERO
    points = _points(at5)
    assert points["S004"]["tokens"] == {
        "input": 12000,
        "output": 800,
        "cache_read": 0,
        "cache_write_5m": 0,
        "cache_write_1h": 0,
    }
    assert points["S004"]["cache_pct"] == "0.0"
    assert set(points["S001"]["tokens"].values()) == {0}
    assert points["S001"]["cache_pct"] is None

    at10 = _build(view, calendar, 10)
    cost = at10["cost"]
    assert _points(at10)["S010"]["usd"] == {"investigator": "0.00080000", "coordinator": "0.00120000"}
    assert cost["points"][-1]["cumulative_usd"] == cost["totals"]["usd"] == "0.00760000"
    assert cost["unplaced_usd"] == ZERO


def test_e3_missing_line_is_null_and_cache_share_uses_all_prompt_tokens() -> None:
    """015 E3 (R3, R4; I7): no line is null, a line with no call is zero; built at 4 and at 2."""
    lines = [
        metric_line("S001"),
        metric_line("S003", coord=[call(0.0001, 0, 1000, 100, 3000)]),
        metric_line("S004", inv=[call(0.0002, 0, 500, 50, 0, 1500)]),
    ]
    view = metric_view(_processed(4), lines)
    at4 = _build(view, NO_CALENDAR, 4)
    points = _points(at4)
    assert points["S001"]["usd"] == {"investigator": ZERO, "coordinator": ZERO}
    assert set(points["S001"]["tokens"].values()) == {0}
    assert points["S001"]["cache_pct"] is None
    for key in ("usd", "tokens", "cache_pct", "latency_ms"):
        assert points["S002"][key] is None
    assert points["S002"]["cumulative_usd"] == ZERO
    assert points["S003"]["usd"]["coordinator"] == "0.00010000"
    assert points["S003"]["cache_pct"] == "75.0"
    assert points["S004"]["usd"]["investigator"] == "0.00020000"
    assert points["S004"]["tokens"]["cache_write_5m"] == 1500
    assert points["S004"]["cache_pct"] == "0.0"
    assert at4["cost"]["totals"] == {
        "usd": "0.00030000",
        "model_calls": 2,
        "input": 1500,
        "output": 150,
        "cache_read": 3000,
        "cache_write_5m": 1500,
        "cache_write_1h": 0,
        "cache_pct": "50.0",
        "latency_ms": 0,
    }
    assert _build(view, NO_CALENDAR, 2)["cost"]["totals"]["cache_pct"] is None


def test_e4_aborted_and_unplaced_lines_count_in_the_remainder_only_at_latest(
    agent_dir: Settings, tmp_path: Path
) -> None:
    """015 E4 (R3; Q-97): an aborted S004 line and an aborted line of unprocessed S011."""
    settings = copied(agent_dir, tmp_path)
    aborted = [metric_line(sid, coord=[call(0.0004)], status="aborted") for sid in ("S004", "S011")]
    extra = settings.traces_dir / "trace-20260303T000000Z.jsonl"
    extra.write_text("".join(line.model_dump_json() + "\n" for line in aborted), encoding="utf-8")
    view, calendar = _load(settings)

    at10 = _build(view, calendar, 10)
    cost = at10["cost"]
    assert _points(at10)["S004"]["usd"] == {"investigator": "0.00080000", "coordinator": "0.00120000"}
    assert "S011" not in _points(at10)
    assert cost["points"][-1]["cumulative_usd"] == "0.00800000"
    assert cost["unplaced_usd"] == "0.00040000"
    assert cost["totals"]["usd"] == _state_cost_usd(view, calendar, 10) == "0.00840000"

    at9 = _build(view, calendar, 9)["cost"]
    assert at9["unplaced_usd"] == ZERO
    assert at9["points"][-1]["cumulative_usd"] == at9["totals"]["usd"] == "0.00600000"
    assert at9["totals"]["usd"] == _state_cost_usd(view, calendar, 9)


def test_e5_latency_sums_every_call_including_aborted_attempts() -> None:
    """015 E5 (R5; Q-116): coordinator, investigator and aborted calls; no call is 0, no line is null."""
    lines = [
        metric_line("S001", coord=[call(0.0001, 1200), call(0.0001, 800)], inv=[call(0.0001, 500)]),
        metric_line("S001", coord=[call(0.0001, 300)], status="aborted"),
        metric_line("S002"),
    ]
    metrics = _build(metric_view(_processed(3), lines), NO_CALENDAR)
    assert [p["latency_ms"] for p in metrics["cost"]["points"]] == [2800, 0, None]
    assert metrics["cost"]["totals"]["latency_ms"] == 2800


def test_e6_cost_states_thresholds_only_and_unreadable_traces(
    thresholds_dir: Settings, agent_dir: Settings, tmp_path: Path
) -> None:
    """015 E6 (R6): (a) thresholds only, (b) a broken trace file in an agent run."""
    assert _metrics(thresholds_dir)["cost"] == {
        "state": "thresholds_only",
        "points": [],
        "unplaced_usd": None,
        "totals": None,
    }

    intact = _metrics(agent_dir)
    settings = copied(agent_dir, tmp_path)
    (settings.traces_dir / "trace-20260301T000000Z.jsonl").write_text("{broken\n", encoding="utf-8")
    broken = _metrics(settings)
    assert broken["trace_error"] == "traces: trace-20260301T000000Z.jsonl is not a readable trace file"
    assert broken["cost"]["state"] == "trace_error"
    assert (broken["cost"]["points"], broken["cost"]["unplaced_usd"], broken["cost"]["totals"]) == (
        [],
        None,
        None,
    )
    assert broken["days"] == intact["days"]
    assert broken["authors"]["agent"] == broken["authors"]["template"] == 0
    assert broken["authors"]["unknown"] > 0


def test_e21_cumulative_sums_line_totals_so_it_matches_planta_exactly() -> None:
    """015 E21 (R3, R5; F1): per-call USD differs from the line total by rounding; built at 2 and at 1."""
    lines = [
        metric_line(
            "S001",
            coord=[call(0.00000003, 100), call(0.00000003, 200)],
            totals_usd=0.00000007,
        ),
        metric_line("S002", inv=[call(0.0001, 300)]),
        metric_line("S003", coord=[call(0.0002, 400)]),
    ]
    view = metric_view(_processed(2), lines)

    at2 = _build(view, NO_CALENDAR, 2)["cost"]
    first, second = at2["points"]
    assert first["usd"]["coordinator"] == "0.00000006"
    assert (first["cumulative_usd"], second["cumulative_usd"]) == ("0.00000007", "0.00010007")
    assert at2["unplaced_usd"] == "0.00020000"
    assert at2["totals"]["usd"] == "0.00030007"
    cost = cost_as_of(view, 2)
    assert cost is not None
    assert cost["usd"] == at2["totals"]["usd"]
    assert at2["totals"]["latency_ms"] == 1000

    at1 = _build(view, NO_CALENDAR, 1)["cost"]
    assert at1["points"][-1]["cumulative_usd"] == at1["totals"]["usd"] == "0.00000007"
    assert at1["unplaced_usd"] == ZERO
    cost = cost_as_of(view, 1)
    assert cost is not None
    assert cost["usd"] == "0.00000007"
    assert at1["totals"]["latency_ms"] == 300


def test_i13_accuracy_panel_ok_without_a_summary_is_rejected() -> None:
    """Risk: I13: an 'ok' accuracy panel with no summary would render an empty table as a result."""
    with pytest.raises(ValueError):
        AccuracyPanel(
            state="ok",
            file="eval-20260303T120000Z.json",
            evaluated_at=None,
            summary=None,
            earlier=0,
            unreadable=0,
        )


# --- T5 ---

TRACE_FILE = "trace-20260302T230000Z.jsonl"
DAY_ONE, DAY_TWO = "3/2/2026", "3/3/2026"
ZERO_DAY = {"alerts": 0, "reports": 0, "reports_with_news": 0, "reports_without_news": 0}


def _days(metrics: Metrics) -> dict[str, Metrics]:
    return {d["label"]: d for d in metrics["days"]}


def _counts(day: Metrics) -> tuple[int, int, int, int]:
    return day["alerts"], day["reports"], day["reports_with_news"], day["reports_without_news"]


@pytest.mark.parametrize(("arg", "effective"), [(None, 12), (5, 5), (0, 0), (99, 12)])
def test_e1_position_resolves_and_zero_is_an_empty_window(
    thresholds_dir: Settings, arg: int | None, effective: int
) -> None:
    """015 E1 (R1): 'at' and 'latest'; at 0 every bucket is zeros and noise has no errors."""
    metrics = _metrics(thresholds_dir, arg)
    assert (metrics["at"], metrics["latest"]) == (effective, 12)
    assert metrics["positions"] == list(range(1, 13))
    if effective == 0:
        assert [d["label"] for d in metrics["days"]] == [DAY_ONE, DAY_TWO]
        assert all({k: v for k, v in d.items() if k != "label"} == ZERO_DAY for d in metrics["days"])
        assert metrics["noise"]["errors"] == 0


def test_e7_days_count_alerts_and_reports_as_of_n(agent_dir: Settings) -> None:
    """015 E7a (R7; FR-22, FR-24): AGENT_DIR at 10 and at 5, per day."""
    view, calendar = _load(agent_dir)
    at10 = _days(_build(view, calendar, 10))
    assert [at10[d][k] for d in (DAY_ONE, DAY_TWO) for k in ("alerts", "reports")] == [1, 3, 2, 2]
    at5 = _days(_build(view, calendar, 5))
    assert [at5[DAY_ONE]["alerts"], at5[DAY_ONE]["reports"]] == [1, 2]
    assert {k: v for k, v in at5[DAY_TWO].items() if k != "label"} == ZERO_DAY


def test_e7_days_split_reports_by_news_over_a_hand_built_calendar() -> None:
    """015 E7b (R7): reports with and without news, built at 8 and at 4."""
    items = [
        NoticeAt(2, 0, shift_report("T01", "S002")),
        NoticeAt(4, 0, shift_report("T02", "S004", news=[PICKUP_LOCAL_CASE])),
        NoticeAt(5, 0, alert_notice("S005", SEDAN_LOCAL_CASE)),
        NoticeAt(8, 0, shift_report("T04", "S008", news=[PICKUP_LOCAL_CASE, SUV_LOCAL_CASE])),
    ]
    rows = run_rows([ProcessedRow(f"S{n:03d}", n) for n in range(1, 9)], notices=items)
    view = metric_view(rows, [])
    at8 = _days(_build(view, CAL, 8))
    assert _counts(at8[DAY_ONE]) == (1, 2, 1, 1)
    assert _counts(at8[DAY_TWO]) == (0, 1, 1, 0)
    at4 = _days(_build(view, CAL, 4))
    assert _counts(at4[DAY_ONE]) == (0, 2, 1, 1)


def test_e8_authors_count_texts_by_who_wrote_them(
    agent_dir: Settings, thresholds_dir: Settings, tmp_path: Path
) -> None:
    """015 E8 (R8; Q-77, Q-100): (a) agent run, (b) S010 line removed, (c) thresholds only."""
    view, calendar = _load(agent_dir)
    base = _build(view, calendar, 10)["authors"]
    assert base["agent"] >= 4

    settings = copied(agent_dir, tmp_path)
    path = settings.traces_dir / TRACE_FILE
    kept = [
        ln for ln in path.read_bytes().splitlines(keepends=True) if json.loads(ln)["snapshot_id"] != "S010"
    ]
    path.write_bytes(b"".join(kept))
    stripped = _metrics(settings, 10)["authors"]
    assert stripped == {
        "agent": base["agent"] - 4,
        "template": base["template"],
        "unknown": base["unknown"] + 4,
    }

    th_view, th_calendar = _load(thresholds_dir)
    state = build_state(th_view, th_calendar, 12)
    news = sum(len(item["novedades"]) for item in state["feed"] if item["kind"] == "report")
    assert _build(th_view, th_calendar, 12)["authors"] == {
        "agent": 0,
        "template": state["kpis"]["alerts"] + news,
        "unknown": 0,
    }


def test_e9_live_noise_as_of_n_finds_repeats_and_duplicate_alerts() -> None:
    """015 E9 (R9; Q-33): a repeated news item and a case alerted twice, built at 3 and at 5."""
    suv_case = "S003-SUV-Europa"
    items = [
        NoticeAt(2, 0, shift_report("T01", "S002", active=[PICKUP_LOCAL_CASE])),
        NoticeAt(3, 0, alert_notice("S003", suv_case)),
        NoticeAt(4, 0, shift_report("T02", "S004", news=[PICKUP_LOCAL_CASE])),
        NoticeAt(5, 0, alert_notice("S005", suv_case)),
    ]
    view = metric_view(run_rows([ProcessedRow(f"S{n:03d}", n) for n in range(1, 6)], notices=items), [])
    assert _build(view, CAL, 3)["noise"] == {
        "state": "ok",
        "errors": 0,
        "repeats": [],
        "duplicate_alerts": [],
    }
    assert _build(view, CAL, 5)["noise"] == {
        "state": "ok",
        "errors": 1,
        "repeats": [{"turno_id": "T02", "case_id": PICKUP_LOCAL_CASE, "previous_turno_id": "T01"}],
        "duplicate_alerts": [{"case_id": suv_case, "alerts": 2}],
    }


def test_e17_closed_guard_hides_the_held_out_shift_from_days_and_counts(thresholds_dir: Settings) -> None:
    """015 E17 (R12, R7): TH_DIR with the guard closed from T06."""
    closed = thresholds_dir.model_copy(update={"heldout_open": False})
    view, calendar = _load(closed)
    metrics = _build(view, calendar)
    assert metrics["latest"] == 10
    assert [d["label"] for d in metrics["days"]] == [DAY_ONE, DAY_TWO]
    shown = {f"S{n:03d}" for n in range(7, 11)}
    stored = read_deliverables(thresholds_dir.registry_path)
    day_two = _days(metrics)[DAY_TWO]
    assert day_two["alerts"] == sum(isinstance(i, Notice) and i.snapshot_id in shown for i in stored)
    assert day_two["reports"] == sum(
        not isinstance(i, Notice) and i.turno_id in {"T04", "T05"} for i in stored
    )
    state_omitted = build_state(view, calendar, 10)["heldout"]["omitted"]
    assert metrics["heldout"] == {
        "open": False,
        "omitted": {
            "snapshots": 2,
            "notices": state_omitted["notices"],
            "trace_lines": 0,
            "evals": 0,
            "run_reports": 0,
        },
    }
    assert metrics["heldout"]["omitted"]["notices"] > 0
    body = json.dumps(metrics)
    assert not [token for token in ("S011", "S012", "T06") if token in body]


def test_e23_invalid_run_output_degrades_only_the_noise_panel() -> None:
    """015 E23 (R9; I9): two reports for T01 make 'RunOutput' invalid; built at 3 and at 2."""
    items = [
        NoticeAt(2, 0, shift_report("T01", "S002")),
        NoticeAt(3, 0, shift_report("T01", "S003")),
    ]
    view = metric_view(run_rows([ProcessedRow(f"S{n:03d}", n) for n in range(1, 4)], notices=items), [])
    at3 = _build(view, CAL, 3)
    assert at3["noise"] == {"state": "invalid", "error": "ValidationError"}
    assert _counts(_days(at3)[DAY_ONE]) == (0, 2, 0, 2)
    assert at3["authors"] == {"agent": 0, "template": 0, "unknown": 0}
    at2 = _build(view, CAL, 2)["noise"]
    assert (at2["state"], at2["errors"]) == ("ok", 0)
