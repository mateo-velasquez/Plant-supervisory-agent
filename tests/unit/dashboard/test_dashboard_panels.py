"""015 T7: 'load_accuracy' and 'load_runs' through 'build_metrics' (R11-R13; E11-E15, E22)."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import trace_builders
from dashboard_builders import RESUMED as _RESUMED
from metrics_builders import eval_file
from trace_builders import copied

from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.config import Settings
from plant_monitor.dashboard.metrics import build_metrics
from plant_monitor.dashboard.panels import load_accuracy, load_runs
from plant_monitor.dashboard.source import Calendar, RunView, load_view
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.ingestion.plant import load_shifts

from builders import isolate_settings_env

agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir
RESUMED = _RESUMED
type Metrics = dict[str, Any]

STAMP = "run-20260302T230000Z.json"
STARTED = "2026-03-02T23:00:00Z"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, 3, hour, minute, tzinfo=UTC)


def _policy(settings: Settings) -> HeldOutPolicy:
    shifts = load_shifts(settings.plant_dir / "turnos.csv")
    return HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)


def _view(settings: Settings) -> RunView:
    return load_view(settings.registry_path, settings.traces_dir, _policy(settings))


def _metrics(settings: Settings, at: int | None = None) -> Metrics:
    """The metrics payload as the client parses it, with the panels read from the settings' folders."""
    policy = _policy(settings)
    view = _view(settings)
    payload = build_metrics(
        view,
        Calendar.load(settings.plant_dir, policy),
        view.resolve_at(at),
        load_accuracy(settings.evals_dir, settings.registry_path, policy),
        load_runs(settings.runs_dir, settings.traces_dir, policy),
    )
    metrics: Metrics = json.loads(json.dumps(payload))
    return metrics


def _item(file: str | None, status: str, started_at: str, duration: float | None) -> Metrics:
    return {
        "file": file,
        "mode": "agent",
        "status": status,
        "started_at": started_at,
        "duration_seconds": duration,
    }


def test_e11_eval_selection_takes_the_newest_match_and_counts_the_rest(
    agent_dir: Settings, tmp_path: Path
) -> None:
    """015 E11 (R11): newest readable match wins; older match, broken file and foreign registry counted."""
    s = copied(agent_dir, tmp_path)
    eval_file(s.evals_dir, _at(10), s.registry_path)
    eval_file(s.evals_dir, _at(12), s.registry_path)
    eval_file(s.evals_dir, _at(13), s.output_dir / "evals" / "smoke-1" / "registry.sqlite3")
    (s.evals_dir / "eval-20260303T140000Z.json").write_text("{broken", encoding="utf-8")
    (s.evals_dir / "notes.json").write_text("{}", encoding="utf-8")

    expected = {
        "state": "ok",
        "file": "eval-20260303T120000Z.json",
        "evaluated_at": "2026-03-03T12:00:00Z",
        "earlier": 1,
        "unreadable": 1,
        "deliverables": 8,
        "current_deliverables": 8,
        "stale": False,
    }
    for at in (None, 3):
        accuracy = _metrics(s, at)["accuracy"]
        assert {key: accuracy[key] for key in expected} == expected
        assert accuracy["summary"]["covered_shifts"] == ["T05"]


def test_i8_an_eval_with_an_impossible_date_is_unreadable_not_fatal(
    agent_dir: Settings, tmp_path: Path
) -> None:
    """Risk: I8 (R11): a name matching 'EVAL_NAME' with a bad date must be counted, never raise."""
    s = copied(agent_dir, tmp_path)
    good = eval_file(s.evals_dir, _at(12), s.registry_path)
    (s.evals_dir / "eval-20261399T000000Z.json").write_bytes(good.read_bytes())

    accuracy = _metrics(s)["accuracy"]

    assert (accuracy["state"], accuracy["file"], accuracy["unreadable"]) == ("ok", good.name, 1)


@pytest.mark.parametrize(
    ("write", "registry", "deliverables", "expected"),
    [
        pytest.param(True, None, 7, {"state": "ok", "stale": True, "deliverables": 7}, id="a-stale"),
        pytest.param(True, None, None, {"state": "ok", "stale": None, "deliverables": None}, id="b-no-count"),
        pytest.param(
            False,
            None,
            8,
            {"state": "none", "summary": None, "earlier": 0, "unreadable": 0},
            id="c-no-evals-dir",
        ),
        pytest.param(True, "out/registry.sqlite3", 8, {"state": "ok"}, id="d-relative-registry"),
    ],
)
def test_e12_staleness_none_and_relative_registry(
    agent_dir: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    write: bool,
    registry: str | None,
    deliverables: int | None,
    expected: Metrics,
) -> None:
    """015 E12 (R11): stale, unknown vigencia, no evals folder, and a relative stored registry."""
    s = copied(agent_dir, tmp_path)
    monkeypatch.chdir(tmp_path)
    if write:
        eval_file(s.evals_dir, _at(12), registry or s.registry_path, deliverables=deliverables)

    accuracy = _metrics(s)["accuracy"]

    assert {key: accuracy[key] for key in expected} == expected


def test_e13_held_out_eval_is_omitted_and_staleness_ignores_the_filter(
    thresholds_dir: Settings, tmp_path: Path
) -> None:
    """015 E13 (R11, R12; Q-110): T06 eval omitted; T05 eval counts shown + omitted; open guard shows it."""
    closed = copied(thresholds_dir, tmp_path).model_copy(update={"heldout_open": False})
    t06 = eval_file(closed.evals_dir, _at(12), closed.registry_path, covered_shifts=("T06",))

    omitted = _metrics(closed)
    assert omitted["accuracy"]["state"] == "omitted"
    assert omitted["accuracy"]["summary"] is None
    assert omitted["heldout"]["omitted"]["evals"] == 1
    assert "T06" not in json.dumps(omitted)

    total = len(read_deliverables(closed.registry_path))
    t06.unlink()
    eval_file(closed.evals_dir, _at(12), closed.registry_path, covered_shifts=("T05",), deliverables=total)
    t05 = _metrics(closed)
    view = _view(closed)
    assert t05["heldout"]["omitted"]["notices"] > 0
    assert t05["heldout"]["omitted"]["evals"] == 0
    assert t05["accuracy"]["current_deliverables"] == total == len(view.deliverables) + view.omitted.notices
    assert t05["accuracy"]["stale"] is False

    (closed.evals_dir / "eval-20260303T120000Z.json").unlink()
    eval_file(closed.evals_dir, _at(12), closed.registry_path, covered_shifts=("T06",))
    opened = _metrics(closed.model_copy(update={"heldout_open": True}))
    assert opened["accuracy"]["state"] == "ok"
    assert set(opened["heldout"]["omitted"].values()) == {0}


@pytest.mark.parametrize(
    ("fixture", "delete_runs", "expected"),
    [
        pytest.param("agent_dir", False, [_item(STAMP, "ok", STARTED, 1.0)], id="a-agent-report"),
        pytest.param(
            "RESUMED",
            False,
            [
                _item(STAMP, "aborted", STARTED, 1.0),
                _item("run-20260302T233000Z.json", "ok", "2026-03-02T23:30:00Z", 1.0),
            ],
            id="b-resumed",
        ),
        pytest.param("agent_dir", True, [_item(None, "running", STARTED, None)], id="c-trace-without-report"),
        pytest.param("thresholds_dir", True, [], id="d-thresholds-no-trace"),
    ],
)
def test_e14_runs_list_reports_by_start_and_add_a_running_trace(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    fixture: str,
    delete_runs: bool,
    expected: list[Metrics],
) -> None:
    """015 E14 (R13; Q-108): reports in start order, a trace with no report is 'running'."""
    s = copied(request.getfixturevalue(fixture), tmp_path)
    if delete_runs:
        for report in s.runs_dir.iterdir():
            report.unlink()
        s.runs_dir.rmdir()

    assert _metrics(s)["runs"]["items"] == expected
    assert _metrics(s, 3)["runs"]["items"] == expected


@pytest.mark.parametrize(
    ("fixture", "closed", "broken", "items", "omitted", "unreadable"),
    [
        pytest.param("thresholds_dir", True, False, 0, 1, 0, id="a-held-out-report"),
        pytest.param("agent_dir", False, True, 1, 0, 1, id="b-unreadable-report"),
    ],
)
def test_e15_a_held_out_report_is_omitted_and_an_unreadable_one_is_counted(
    request: pytest.FixtureRequest,
    tmp_path: Path,
    fixture: str,
    closed: bool,
    broken: bool,
    items: int,
    omitted: int,
    unreadable: int,
) -> None:
    """015 E15 (R12, R13; I8): the T06+ report is omitted; a broken file is counted, the real one stays."""
    s = copied(request.getfixturevalue(fixture), tmp_path)
    if closed:
        s = s.model_copy(update={"heldout_open": False})
    if broken:
        (s.runs_dir / "run-20260301T000000Z.json").write_text("{", encoding="utf-8")

    metrics = _metrics(s)

    assert len(metrics["runs"]["items"]) == items
    assert metrics["heldout"]["omitted"]["run_reports"] == omitted
    assert metrics["runs"]["unreadable"] == unreadable
    if broken:
        assert metrics["runs"]["items"][0]["file"] == STAMP


@pytest.mark.parametrize(
    ("closed", "broken", "omitted", "unreadable"),
    [
        pytest.param(True, False, 1, 0, id="a-omitted-report"),
        pytest.param(False, True, 0, 1, id="b-unreadable-report"),
    ],
)
def test_e22_a_trace_whose_report_is_omitted_or_unreadable_is_not_running(
    agent_dir: Settings, tmp_path: Path, closed: bool, broken: bool, omitted: int, unreadable: int
) -> None:
    """015 E22 (R13; F3): pairing goes by report name, so no 'running' item appears."""
    s = copied(agent_dir, tmp_path)
    if closed:
        s = s.model_copy(update={"heldout_open": False, "heldout_first_shift": "T05"})
    if broken:
        (s.runs_dir / STAMP).write_text("{", encoding="utf-8")

    metrics = _metrics(s)

    assert metrics["runs"]["items"] == []
    assert metrics["heldout"]["omitted"]["run_reports"] == omitted
    assert metrics["runs"]["unreadable"] == unreadable
