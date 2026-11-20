"""Builders for the 014 dashboard tests: hand-built run rows and the resumed run."""

import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from cli_builders import cli_deps, cli_settings, write_cli_data
from multi_agent_builders import ALL, S002, S004, S005, SECOND_START, STARTED
from trace_builders import PRICES

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelCallFailed
from plant_monitor.cases.registry.notices import is_deliverable
from plant_monitor.cases.registry.run_reader import CaseRow, HistoryAt, NoticeAt, ProcessedRow, RunRows
from plant_monitor.config import Settings
from plant_monitor.dashboard.source import Omitted, RunView
from plant_monitor.runner.cli import main

if TYPE_CHECKING:
    from plant_monitor.dashboard.server import DashboardApp


def run_rows(
    processed: Sequence[ProcessedRow] = (),
    cases: Sequence[CaseRow] = (),
    history: Sequence[HistoryAt] = (),
    notices: Sequence[NoticeAt] = (),
) -> RunRows:
    """Hand-built registry rows; every table defaults to empty."""
    return RunRows(
        processed=tuple(processed), cases=tuple(cases), history=tuple(history), notices=tuple(notices)
    )


def run_view(rows: RunRows) -> RunView:
    """A 'RunView' over hand-built rows: guard open, no trace files."""
    return RunView(
        registry="ok",
        rows=rows,
        deliverables=tuple(n for n in rows.notices if is_deliverable(n.item)),
        lines=(),
        committed={},
        aborted={},
        trace_error=None,
        mode="thresholds_only",
        omitted=Omitted(snapshots=0, notices=0, trace_lines=0),
        policy_open=True,
    )


HOST = "127.0.0.1:8765"


def app_of(settings: Settings) -> DashboardApp:
    """The spec's APP(s): the dashboard app over 'settings' with the real frontend folder."""
    from plant_monitor.dashboard.server import DashboardApp

    return DashboardApp.from_settings(settings)


def get_json(app: DashboardApp, target: str, host: str | None = HOST) -> tuple[int, dict[str, object]]:
    """GET 'target' through 'handle' and return the status with the parsed JSON body."""
    response = app.handle("GET", target, host)
    body: dict[str, object] = json.loads(response.body)
    return response.status, body


class FakeServe:
    """A 'serve' seam: records its calls, optionally calls 'on_ready', then returns or raises."""

    def __init__(self, *, ready: bool = True, raises: BaseException | None = None) -> None:
        self.ports: list[int] = []
        self._ready = ready
        self._raises = raises

    def __call__(self, app: DashboardApp, port: int, on_ready: Callable[[int], None]) -> None:
        self.ports.append(port)
        if self._ready:
            on_ready(port)
        if self._raises is not None:
            raise self._raises


@pytest.fixture(scope="module")
def RESUMED(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    """The spec's RESUMED: 013 E5's two runs over five snapshots, S005 aborted then committed."""
    root: Path = tmp_path_factory.mktemp("resumed")
    settings = cli_settings(write_cli_data(root / "data", ALL[:5]), root / "out", **PRICES)
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(root)
        failing = FakeModel([*S002, *S004, ModelCallFailed("create", 529)])
        assert main(["run"], deps=cli_deps(settings, failing, now=STARTED)) == 2
        assert main(["run"], deps=cli_deps(settings, FakeModel(S005), now=SECOND_START)) == 0
    return settings
