"""016 R20: 'run --dashboard' runs the series in a fresh folder with the live dashboard (E26, E27)."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cli_builders import ARR13, Sleeps, cli_deps, cli_settings, write_cli_data
from dashboard_builders import HOST
from multi_agent_builders import ALL, S002, S004, query

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelCallFailed
from plant_monitor.config import Settings
from plant_monitor.dashboard.server import DashboardApp, RunningDashboard
from plant_monitor.runner.cli import CliDeps, main, parse_args

from builders import isolate_settings_env

NOW = datetime(2026, 11, 21, 20, 15, tzinfo=UTC)
STAMP = "20261121T201500Z"
PORT = 8765


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _api(app: DashboardApp, route: str) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(app.handle("GET", route, HOST).body)
    return body


class FakeDashboard:
    """Records the 'start_dashboard', 'wait' and 'stop' calls and what the app served at each."""

    def __init__(self, *, fail: OSError | None = None, interrupt_wait: bool = False) -> None:
        self.events: list[str] = []
        self.app: DashboardApp | None = None
        self.at_start: dict[str, Any] = {}
        self.at_wait: dict[str, Any] = {}
        self._fail = fail
        self._interrupt_wait = interrupt_wait

    def start(self, app: DashboardApp, port: int) -> RunningDashboard:
        self.events.append(f"start:{port}")
        if self._fail is not None:
            raise self._fail
        self.app = app
        self.at_start = _api(app, "/api/state")
        return RunningDashboard(port=port, stop=lambda: self.events.append("stop"))

    def wait(self) -> None:
        self.events.append("wait")
        assert self.app is not None
        self.at_wait = _api(self.app, "/api/forecast")
        if self._interrupt_wait:
            raise KeyboardInterrupt


def _deps(settings: Settings, fake: FakeDashboard, base: CliDeps | None = None) -> CliDeps:
    seams = base or cli_deps(settings, now=NOW)
    return replace(seams, start_dashboard=fake.start, wait=fake.wait)


def _run_dir(out: Path) -> Path:
    return out / f"run-{STAMP}"


def test_e26_run_dashboard_uses_a_fresh_folder_and_serves_it_before_during_and_after_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """016 E26 (R20; I12-I14): a folder per launch, the app reads it, start, wait, stop, rows forecast."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    settings = cli_settings(data, out, anthropic_api_key=None)
    fake = FakeDashboard()

    assert main(["run", "--dashboard", "--thresholds-only"], deps=_deps(settings, fake)) == 0

    folder = _run_dir(out)
    assert (folder / "registry.sqlite3").is_file()
    assert (folder / "notices").is_dir()
    assert (folder / "runs" / f"run-{STAMP}.json").is_file()
    assert not (out / "registry.sqlite3").exists()
    assert fake.events == [f"start:{PORT}", "wait", "stop"]
    assert fake.at_start["registry"] == "missing"
    assert (fake.at_wait["registry"], fake.at_wait["positions"]) == ("ok", list(range(1, len(ALL) + 1)))
    forecasts = query(folder / "registry.sqlite3", "SELECT COUNT(*) FROM gap_forecasts")
    assert forecasts[0][0] == 9 * len(ALL)
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"dashboard: http://127.0.0.1:{PORT}/"
    assert lines[1] == f"output: {folder}"
    assert any(line.startswith("summary: ") for line in lines)
    assert lines[-1] == f"dashboard still serving; trace with OUTPUT_DIR={folder} (Ctrl+C to stop)"


def test_e26_plain_run_has_no_dashboard() -> None:
    """016 E26 (I12): 'run' alone parses with 'dashboard' False; the flag sets it."""
    plain, flagged = parse_args(["run"]), parse_args(["run", "--dashboard", "--speed", "2"])
    assert getattr(plain, "dashboard", None) is False
    assert getattr(flagged, "dashboard", None) is True


def test_e27a_an_existing_run_folder_returns_2_before_anything_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """016 E27(a) (R20): the folder for this instant exists, so nothing is bound or processed."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    _run_dir(out).mkdir(parents=True)
    fake = FakeDashboard()

    code = main(["run", "--dashboard", "--thresholds-only"], deps=_deps(cli_settings(data, out), fake))

    assert code == 2
    assert f"{_run_dir(out)} already exists: wait a second and run again" in capsys.readouterr().err
    assert fake.events == []
    assert not (_run_dir(out) / "registry.sqlite3").exists()


def test_e27b_a_port_that_cannot_be_bound_returns_2_and_creates_no_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """016 E27(b) (R20): 'OSError' from the bind names the port; the run folder never exists."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    fake = FakeDashboard(fail=OSError("in use"))

    code = main(["run", "--dashboard", "--thresholds-only"], deps=_deps(cli_settings(data, out), fake))

    assert code == 2
    assert f"dashboard: cannot listen on 127.0.0.1:{PORT} (OSError)" in capsys.readouterr().err
    assert fake.events == [f"start:{PORT}"]
    assert not _run_dir(out).exists()


def test_e27c_agent_mode_without_key_returns_2_before_anything_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """016 E27(c) (R20; 012 E4a): the missing key is reported before any bind or folder."""
    out = tmp_path / "out"
    fake = FakeDashboard()

    code = main(
        ["run", "--dashboard"], deps=_deps(cli_settings(tmp_path / "data", out, anthropic_api_key=None), fake)
    )

    assert code == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert fake.events == []
    assert not out.exists()


def test_e27d_ctrl_c_during_the_series_returns_130_stops_and_does_not_wait(tmp_path: Path) -> None:
    """016 E27(d) (R20; 012 E11): an interrupted run writes its report, stops the server once, never waits."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    settings = cli_settings(data, out)
    fake = FakeDashboard()
    base = cli_deps(settings, now=NOW, sleep=Sleeps(interrupt_at=2))

    code = main(["run", "--dashboard", "--thresholds-only", "--speed", "1"], deps=_deps(settings, fake, base))

    assert code == 130
    assert fake.events == [f"start:{PORT}", "stop"]
    report = json.loads((_run_dir(out) / "runs" / f"run-{STAMP}.json").read_text(encoding="utf-8"))
    assert report["status"] == "interrupted"


def test_e27e_ctrl_c_during_the_wait_keeps_the_run_exit_code(tmp_path: Path) -> None:
    """016 E27(e) (R20): Ctrl+C after a finished run stops the server and exits with the run's 0."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    settings = cli_settings(data, out)
    fake = FakeDashboard(interrupt_wait=True)

    assert main(["run", "--dashboard", "--thresholds-only"], deps=_deps(settings, fake)) == 0
    assert fake.events == [f"start:{PORT}", "wait", "stop"]


def test_e27f_an_aborted_run_writes_its_report_and_still_waits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """016 E27(f) (R20; 012 E7): an abort exits 2 after the wait, so its state can be inspected."""
    data, out = write_cli_data(tmp_path / "data", ALL[:6]), tmp_path / "out"
    settings = cli_settings(data, out)
    failing = FakeModel([*S002, S004[0], ModelCallFailed("create", 529)])
    fake = FakeDashboard()

    code = main(["run", "--dashboard"], deps=_deps(settings, fake, cli_deps(settings, failing, now=NOW)))

    assert code == 2
    assert "run aborted at S004: " in capsys.readouterr().err
    assert fake.events == [f"start:{PORT}", "wait", "stop"]
    report = json.loads((_run_dir(out) / "runs" / f"run-{STAMP}.json").read_text(encoding="utf-8"))
    assert (report["status"], report["aborted_at"]) == ("aborted", "S004")
    assert fake.at_wait["positions"] == [1, 2, 3]
