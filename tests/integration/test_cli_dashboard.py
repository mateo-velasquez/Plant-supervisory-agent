"""014 T11: the 'plant-monitor dashboard' command with a 'serve' seam, no model, no socket (E18, E19)."""

import io
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from cli_builders import cli_deps, cli_settings, write_cli_data
from dashboard_builders import FakeServe
from multi_agent_builders import ALL

from plant_monitor.runner.cli import main

from builders import isolate_settings_env

URL_LINE = "dashboard: http://127.0.0.1:8765/ (Ctrl+C to stop)\n"


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


@pytest.mark.parametrize(
    ("argv", "serve", "first_shift", "code", "out", "err", "ports"),
    [
        (["dashboard"], FakeServe(), "T06", 0, URL_LINE, "", [8765]),
        (["dashboard"], FakeServe(raises=KeyboardInterrupt()), "T06", 0, URL_LINE, "", [8765]),
        (
            ["dashboard"],
            FakeServe(ready=False, raises=OSError()),
            "T06",
            2,
            "",
            "dashboard: cannot listen on 127.0.0.1:8765 (OSError)\n",
            [8765],
        ),
        (["dashboard"], FakeServe(), "T99", 2, "", "first held-out shift T99 is not in turnos.csv\n", []),
        (["dashboard", "x"], FakeServe(), "T06", 2, None, None, []),
        (["dashboard", "--help"], FakeServe(), "T06", 0, None, None, []),
    ],
    ids=["a-ready", "b-ctrl-c", "c-bind-error", "d-bad-shift", "e-extra-arg", "f-help"],
)
def test_e18_dashboard_command(
    argv: list[str],
    serve: FakeServe,
    first_shift: str,
    code: int,
    out: str | None,
    err: str | None,
    ports: list[int],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """014 E18 (R1): exit codes, URL line and stderr per case; the model factory is never called."""
    settings = cli_settings(
        write_cli_data(tmp_path / "data", ALL[:1]),
        tmp_path / "out",
        anthropic_api_key=None,
        heldout_first_shift=first_shift,
    )
    deps = replace(cli_deps(settings, None), serve=serve)
    assert main(argv, deps=deps) == code
    captured = capsys.readouterr()
    if out is not None:
        assert captured.out == out
    if err is not None:
        assert captured.err == err
    assert serve.ports == ports


def test_e19_error_cannot_crash_a_cp1252_stderr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Risk: 014 E19 (R1): an unencodable character in the failure line is escaped, not raised."""
    settings = cli_settings(
        write_cli_data(tmp_path / "data", ALL[:1]),
        tmp_path / "out",
        anthropic_api_key=None,
        heldout_first_shift=f"T99{chr(0x2212)}",
    )
    raw = io.BytesIO()
    stderr = io.TextIOWrapper(raw, encoding="cp1252", newline="")
    monkeypatch.setattr(sys, "stderr", stderr)
    deps = replace(cli_deps(settings, None), serve=FakeServe())
    assert main(["dashboard"], deps=deps) == 2
    assert raw.getvalue() == b"first held-out shift T99\\u2212 is not in turnos.csv\n"
