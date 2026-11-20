"""014 T5: 'load_view' over resumed, corrupt and held-out runs (R12, R13, E12, E13, E15)."""

from pathlib import Path

import pytest
import trace_builders
from dashboard_builders import RESUMED as _RESUMED
from trace_builders import copied

from plant_monitor.cases.registry.run_reader import RunRows
from plant_monitor.config import Settings
from plant_monitor.dashboard.source import RunView, load_view
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.ingestion.plant import load_shifts

from builders import isolate_settings_env

RESUMED = _RESUMED
agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir

FIRST_FILE = "trace-20260302T230000Z.jsonl"
SECOND_FILE = "trace-20260302T233000Z.jsonl"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _view(settings: Settings) -> RunView:
    """The 'RunView' of a run under the policy its settings give."""
    shifts = load_shifts(settings.plant_dir / "turnos.csv")
    policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
    return load_view(settings.registry_path, settings.traces_dir, policy)


def test_e12_resumed_run_counts_the_aborted_attempt_and_shows_the_committed_line(RESUMED: Settings) -> None:
    """014 E12 (R12): S005 has one aborted line and its committed line is in the second file."""
    view = _view(RESUMED)
    assert view.trace_error is None
    assert len(view.aborted["S005"]) == 1
    assert view.aborted["S005"][0][1].status == "aborted"
    assert "S004" not in view.aborted
    assert view.committed["S005"].status == "committed"
    assert [(name, line.status) for name, line in view.lines if line.snapshot_id == "S005"] == [
        (FIRST_FILE, "aborted"),
        (SECOND_FILE, "committed"),
    ]


@pytest.mark.parametrize(
    ("case", "error"),
    [
        ("duplicate", f"traces: two committed lines for S001 ({FIRST_FILE}, trace-20260302T235900Z.jsonl)"),
        ("broken", "traces: trace-20260301T000000Z.jsonl is not a readable trace file"),
        ("partial", None),
    ],
)
def test_e13_corrupt_traces_set_trace_error_and_keep_registry_views(
    agent_dir: Settings, tmp_path: Path, case: str, error: str | None
) -> None:
    """014 E13 (R12): (a) duplicate, (b) broken line, (c) partial tail, registry rows kept."""
    intact = _view(agent_dir)
    settings = copied(agent_dir, tmp_path)
    original = settings.traces_dir / FIRST_FILE
    if case == "duplicate":
        (settings.traces_dir / "trace-20260302T235900Z.jsonl").write_bytes(original.read_bytes())
    elif case == "broken":
        (settings.traces_dir / "trace-20260301T000000Z.jsonl").write_text("{broken\n", encoding="utf-8")
    else:
        with original.open("a", encoding="utf-8") as handle:
            handle.write('{"snapshot_id": "S0')

    view = _view(settings)

    assert view.trace_error == error
    assert view.rows == intact.rows
    assert view.deliverables == intact.deliverables
    if error is None:
        assert view.committed == intact.committed
        assert view.lines == intact.lines
    else:
        assert not view.committed
        assert not view.aborted


def test_e15_closed_guard_leaves_no_case_of_held_out_snapshots(thresholds_dir: Settings) -> None:
    """014 E15 (R13): with the guard closed, 'rows.cases' holds no case opened at S011 or S012."""
    closed = thresholds_dir.model_copy(update={"heldout_open": False})
    rows: RunRows = _view(closed).rows
    assert rows.cases
    assert not [c for c in rows.cases if c.case_id.startswith(("S011", "S012"))]
