"""012 T2, T5: the 'plant-monitor run' command over synthetic data, no model (E2-E6, E11, E14)."""

import json
import logging
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from cli_builders import ARR13, Sleeps, cli_deps, cli_settings, never_model, write_cli_data
from multi_agent_builders import (
    ALL,
    HEAD,
    S002,
    S004,
    S005,
    S006,
    S010_EMIT,
    S010_JUDGE,
    SECOND_START,
    STARTED,
    TAIL,
    query,
)

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.model import ModelCallFailed
from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.config import Settings
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.runner.cli import CliDeps, main
from plant_monitor.telemetry.trace import read_trace, trace_path

from builders import isolate_settings_env


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def report_of(out: Path) -> dict[str, object]:
    """The single run report under 'runs'."""
    files = sorted((out / "runs").glob("run-*.json"))
    assert len(files) == 1
    loaded: dict[str, object] = json.loads(files[0].read_text(encoding="utf-8"))
    return loaded


def arrivals_of(out: Path) -> dict[str, list[str]]:
    """The 'processed' and 'skipped' ids of the run report."""
    run = report_of(out)["run"]
    assert isinstance(run, dict)
    arrivals: dict[str, list[str]] = run["arrivals"]
    return arrivals


def stored_ids(out: Path) -> list[str]:
    """Snapshot ids in the registry, in commit order."""
    rows = query(out / "registry.sqlite3", "SELECT snapshot_id FROM processed_snapshots ORDER BY seq")
    return [str(row[0]) for row in rows]


def test_e2_thresholds_only_runs_with_no_key_no_model_and_no_traces(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E2: no key, the real clock and sleep defaults, nothing from the model, 6 shift reports."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    settings = cli_settings(data, out, anthropic_api_key=None)
    deps = replace(CliDeps(), settings=lambda: settings, model_factory=never_model)

    assert main(["run", "--thresholds-only"], deps=deps) == 0

    assert arrivals_of(out) == {"processed": list(ALL), "skipped": ["S004"]}
    assert not (out / "traces").exists()
    report = report_of(out)
    zero = {
        "model_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_5m_tokens": 0,
        "cache_write_1h_tokens": 0,
        "usd": 0,
    }
    run, series = report["run"], report["series"]
    assert isinstance(run, dict)
    assert isinstance(series, dict)
    assert run["tokens"] == zero
    assert run["by_agent"] == {"investigator": zero, "coordinator": zero}
    assert series["tokens"] == zero
    assert series["shift_reports"] == 6
    assert "summary: " in capsys.readouterr().out


def test_e4b_invalid_settings_return_2_before_any_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E4b: Risk: a settings 'ValidationError' prints 'settings: invalid or missing', creates nothing."""
    out = tmp_path / "out"

    def invalid() -> Settings:
        return Settings.model_validate({"log_level": "LOUD"})

    deps = replace(cli_deps(cli_settings(tmp_path / "data", out)), settings=invalid)

    assert main(["run"], deps=deps) == 2

    assert capsys.readouterr().err.startswith("settings: invalid or missing")
    assert not out.exists()


@pytest.mark.parametrize(
    ("overrides", "argv", "code", "processed", "skipped", "message", "preexisting"),
    [
        pytest.param({}, ["--until", "S004"], 0, list(ALL[:4]), [], "", False, id="a-until-first-occurrence"),
        pytest.param(
            {"heldout_open": False}, ["--until", "S011"], 2, [], [], "held out", False, id="b-held-out"
        ),
        pytest.param({}, ["--until", "S099"], 2, [], [], "S099", False, id="c-unknown"),
        pytest.param(
            {"heldout_open": False}, [], 0, list(ALL[:10]), ["S004"], "", False, id="d-closed-guard"
        ),
        pytest.param({}, ["--until", "S004"], 2, [], [], "", True, id="e-report-exists"),
    ],
)
def test_e5_selection_of_arrivals(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    overrides: dict[str, object],
    argv: list[str],
    code: int,
    processed: list[str],
    skipped: list[str],
    message: str,
    preexisting: bool,
) -> None:
    """E5a-e: '--until' keeps the first occurrence, bad targets and a taken report name return 2 first."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    existing = out / "runs" / "run-20260302T230000Z.json"
    if preexisting:
        existing.parent.mkdir(parents=True)
        existing.write_text("{}", encoding="utf-8")
    deps = cli_deps(cli_settings(data, out, **overrides))

    assert main(["run", "--thresholds-only", *argv], deps=deps) == code

    err = capsys.readouterr().err
    assert message in err
    if message == "held out":
        assert "S011" in err
    if code == 0:
        assert arrivals_of(out) == {"processed": processed, "skipped": skipped}
    else:
        assert out.exists() is preexisting
        assert not (out / "registry.sqlite3").exists()
    if preexisting:
        assert existing.read_text(encoding="utf-8") == "{}"


def test_e14_an_unreadable_trace_never_loses_the_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E14: Risk: a broken earlier trace makes the summary unavailable; the run still ends 0."""
    data, out = write_cli_data(tmp_path / "data", ALL[:2]), tmp_path / "out"
    broken = out / "traces" / "trace-20260301T000000Z.jsonl"
    broken.parent.mkdir(parents=True)
    broken.write_text("{broken\n", encoding="utf-8")

    assert main(["run"], deps=cli_deps(cli_settings(data, out), FakeModel([*S002]))) == 0

    assert stored_ids(out) == ["S001", "S002"]
    err = capsys.readouterr().err
    assert "summary unavailable: " in err
    assert "Traceback" not in err


def test_x2_closed_guard_drops_a_repeat_that_arrives_after_the_last_allowed_snapshot(tmp_path: Path) -> None:
    """X2: closed mode stops at S010, so a repeat of S004 placed after it is never read."""
    ids = (*ALL[:10], "S004")
    data, out = write_cli_data(tmp_path / "data", ids), tmp_path / "out"

    assert main(["run", "--thresholds-only"], deps=cli_deps(cli_settings(data, out, heldout_open=False))) == 0

    assert arrivals_of(out) == {"processed": list(ALL[:10]), "skipped": []}


# --- 012 T5: pacing and Ctrl-C (E6, E11) ---


def test_e6a_speed_sleeps_once_per_committed_snapshot_never_at_start_or_for_a_repeat(tmp_path: Path) -> None:
    """E6a: '--speed 2.5' to S005 sleeps 2.5 s five times: not at the start, not for the skipped repeat."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    sleeps = Sleeps()

    code = main(
        ["run", "--thresholds-only", "--until", "S005", "--speed", "2.5"],
        deps=cli_deps(cli_settings(data, out), sleep=sleeps),
    )

    assert code == 0
    assert arrivals_of(out) == {"processed": list(ALL[:5]), "skipped": ["S004"]}
    assert sleeps.calls == [2.5] * 5


@pytest.mark.parametrize(
    ("argv", "code"),
    [(["--speed", "-1"], 2), (["--speed", "nan"], 2), (["--help"], 0)],
    ids=["negative", "nan", "help"],
)
def test_e6cd_bad_speed_returns_2_and_help_returns_0_without_creating_output(
    tmp_path: Path, argv: list[str], code: int
) -> None:
    """E6c, E6d: a negative or non-finite '--speed' is a parse error; '--help' exits 0; nothing is created."""
    out = tmp_path / "out"
    deps = cli_deps(cli_settings(tmp_path / "data", out))

    assert main(["run", "--thresholds-only", *argv], deps=deps) == code

    assert not out.exists()


def test_e11_ctrl_c_returns_130_with_an_interrupted_report(tmp_path: Path) -> None:
    """E11: Risk: Ctrl-C in the 2nd pause keeps S001 and S002 committed and writes an 'interrupted' report."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    sleeps = Sleeps(interrupt_at=2)

    code = main(
        ["run", "--thresholds-only", "--speed", "1"], deps=cli_deps(cli_settings(data, out), sleep=sleeps)
    )

    assert code == 130
    report = report_of(out)
    run = report["run"]
    assert isinstance(run, dict)
    assert (report["status"], run["arrivals"]) == ("interrupted", None)
    assert stored_ids(out) == ["S001", "S002"]


# --- 012 T1: agent mode (E1, E4a, E12) ---


def load_report(out: Path, stamp: str) -> dict[str, Any]:
    """The run report written for the run started at 'stamp' (e.g. '20260302T230000Z')."""
    loaded: dict[str, Any] = json.loads((out / "runs" / f"run-{stamp}.json").read_text(encoding="utf-8"))
    return loaded


def tally(tokens: dict[str, Any]) -> tuple[int, int, int, Any]:
    """Calls, input, output and usd of a report's token block."""
    return tokens["model_calls"], tokens["input_tokens"], tokens["output_tokens"], tokens["usd"]


def test_e1_full_series_in_agent_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """E1: agent mode over ARR13 sends 22 requests, traces 12 snapshots and reports exact tokens."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    model = FakeModel([*HEAD, *S010_JUDGE, *S010_EMIT, *TAIL])
    deps = cli_deps(cli_settings(data, out), model, ticks=(10.0, 52.5))

    assert main(["run"], deps=deps) == 0

    assert len(model.requests) == 22
    assert arrivals_of(out) == {"processed": list(ALL), "skipped": ["S004"]}
    assert len(read_trace(trace_path(out / "traces", STARTED))) == 12
    items = read_deliverables(out / "registry.sqlite3")
    assert [r.turno_id for r in items if isinstance(r, ShiftReport)] == [
        "T01",
        "T02",
        "T03",
        "T04",
        "T05",
        "T06",
    ]
    assert sum(isinstance(i, Notice) for i in items) == 4
    report = load_report(out, "20260302T230000Z")
    assert (report["mode"], report["status"], report["duration_seconds"]) == ("agent", "ok", 42.5)
    run = report["run"]
    assert tally(run["tokens"]) == (22, 66000, 4400, pytest.approx(0.0088))
    assert (run["tokens"]["cache_read_tokens"], run["tokens"]["cache_write_5m_tokens"]) == (0, 0)
    assert run["tokens"]["cache_write_1h_tokens"] == 0
    assert tally(run["by_agent"]["investigator"]) == (12, 36000, 2400, pytest.approx(0.0048))
    assert tally(run["by_agent"]["coordinator"]) == (10, 30000, 2000, pytest.approx(0.004))
    assert run["budget_exceeded"] == []
    assert report["series"] == {"tokens": run["tokens"], "shift_reports": 6, "alerts": 4}
    assert (
        capsys.readouterr().out.splitlines()[-1] == f"summary: {out / 'runs' / 'run-20260302T230000Z.json'}"
    )


def test_e4a_agent_mode_without_key_returns_2_before_any_work(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E4a: Risk: no key in agent mode names 'ANTHROPIC_API_KEY', builds no model, creates nothing."""
    out = tmp_path / "out"
    deps = cli_deps(cli_settings(tmp_path / "data", out, anthropic_api_key=None))

    assert main(["run"], deps=deps) == 2

    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not out.exists()


def test_e12_agent_run_over_a_threshold_only_directory_processes_nothing(tmp_path: Path) -> None:
    """E12: Risk: agent mode on a directory already processed without a model skips all and sends nothing."""
    data, out = write_cli_data(tmp_path / "data", ARR13), tmp_path / "out"
    first = cli_deps(cli_settings(data, out, anthropic_api_key=None))
    assert main(["run", "--thresholds-only"], deps=first) == 0
    model = FakeModel([])

    assert main(["run"], deps=cli_deps(cli_settings(data, out), model, now=SECOND_START)) == 0

    assert model.requests == []
    report = load_report(out, "20260302T233000Z")
    assert report["run"]["arrivals"] == {"processed": [], "skipped": list(ARR13)}
    assert tally(report["run"]["tokens"]) == (0, 0, 0, 0)
    assert not (out / "traces" / "trace-20260302T233000Z.jsonl").exists()


# --- 012 T6: prompt-budget report (E8) ---


def test_e8_prompt_budget_is_reported_and_the_run_continues(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    """E8: an oversized prompt sends nothing, lands in 'budget_exceeded', warns, and the exit stays 0."""
    data, out = write_cli_data(tmp_path / "data", ALL[:2]), tmp_path / "out"
    model = FakeModel([], count=96_000)

    with caplog.at_level(logging.WARNING, logger="plant_monitor.agents.loop"):
        assert main(["run"], deps=cli_deps(cli_settings(data, out), model)) == 0

    assert model.requests == []
    assert len(model.counted) == 1
    report = load_report(out, "20260302T230000Z")
    assert report["status"] == "ok"
    assert report["run"]["arrivals"] == {"processed": ["S001", "S002"], "skipped": []}
    assert report["run"]["budget_exceeded"] == [{"snapshot_id": "S002", "agent": "investigator"}]
    assert tally(report["run"]["tokens"]) == (0, 0, 0, 0)
    assert report["series"]["shift_reports"] == 1
    assert "budget exceeded: S002 investigator" in capsys.readouterr().out
    warnings = [r.getMessage() for r in caplog.records if r.name == "plant_monitor.agents.loop"]
    assert (
        "snapshot S002 turn 1: prompt of 96000 tokens is over the limit of 95000; request not sent"
        in warnings
    )


# --- 012 T4: resume after a failure (E7) ---


def test_e7_resume_after_a_model_failure_reprocesses_only_the_failed_snapshot_onward(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E7: a 529 at S004 aborts with 2; a rerun on the same directory resumes at S004 with its own trace."""
    data, out = write_cli_data(tmp_path / "data", ALL[:6]), tmp_path / "out"
    failing = FakeModel([*S002, S004[0], ModelCallFailed("create", 529)])

    assert main(["run"], deps=cli_deps(cli_settings(data, out), failing)) == 2

    assert "run aborted at S004: " in capsys.readouterr().err
    first = load_report(out, "20260302T230000Z")
    assert (first["status"], first["aborted_at"]) == ("aborted", "S004")
    assert first["cause"] == "ModelCallFailed: model call 'create' failed (status 529)"
    assert first["run"]["arrivals"] == {"processed": ["S001", "S002", "S003"], "skipped": []}
    assert tally(first["run"]["tokens"]) == (3, 9000, 600, pytest.approx(0.0012))
    assert first["series"]["tokens"] == first["run"]["tokens"]

    resumed = FakeModel([*S004, *S005, *S006])
    assert main(["run"], deps=cli_deps(cli_settings(data, out), resumed, now=SECOND_START)) == 0

    assert len(resumed.requests) == 8
    second = load_report(out, "20260302T233000Z")
    assert second["run"]["arrivals"] == {
        "processed": ["S004", "S005", "S006"],
        "skipped": ["S001", "S002", "S003"],
    }
    assert tally(second["run"]["tokens"]) == (8, 24000, 1600, pytest.approx(0.0032))
    assert tally(second["series"]["tokens"]) == (11, 33000, 2200, pytest.approx(0.0044))
    assert (second["series"]["shift_reports"], second["series"]["alerts"]) == (3, 1)


# --- 012 T12 ---


def test_e15_an_agent_directory_stays_agent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """E15: Risk: '--thresholds-only' over an agent directory returns 2 and commits nothing (Q-71)."""
    data, out = write_cli_data(tmp_path / "data", ALL[:4]), tmp_path / "out"
    assert main(["run", "--until", "S002"], deps=cli_deps(cli_settings(data, out), FakeModel([*S002]))) == 0
    capsys.readouterr()

    deps = cli_deps(cli_settings(data, out, anthropic_api_key=None), now=SECOND_START)
    assert main(["run", "--thresholds-only"], deps=deps) == 2

    err = capsys.readouterr().err
    assert "agent-mode traces" in err and "agent mode" in err
    assert stored_ids(out) == ["S001", "S002"]
    assert not (out / "runs" / "run-20260302T233000Z.json").exists()
