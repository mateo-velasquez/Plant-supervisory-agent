"""015 T1: 'read_summary' and the atomic write of the evaluation summary file (E10)."""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from plant_monitor.evaluation.summary import evaluate, write_summary
from plant_monitor.evaluation.summary_file import EVAL_NAME, read_summary, write_summary_json

from eval_builders import (
    PB1,
    SEL,
    alert,
    fixture_shifts,
    golden_alert,
    golden_news,
    golden_set,
    report,
    run_output,
)

AT = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
NAME = "eval-20261107T120000Z.json"


def _e32_written(directory: Path) -> Path:
    """Write 005 E32's summary (1 alert, 2 reports) through 'write_summary'."""
    golden = golden_set(
        ("T01", "T02"),
        alerts=[golden_alert(SEL, "S003")],
        news=[golden_news("T01", PB1, "en_seguimiento", "ninguna", "media", depends_on=["Q-26"])],
    )
    run = run_output([alert("S003", SEL)], [report("T01", "S002"), report("T02", "S004")])
    summary = evaluate(
        run,
        golden,
        fixture_shifts(),
        capabilities=frozenset(),
        registry="registry.sqlite3",
        golden_dir="evals/golden",
    )
    return write_summary(summary, directory, AT)


def test_e10_read_summary_returns_the_stored_fields(tmp_path: Path) -> None:
    stored = read_summary(_e32_written(tmp_path))
    assert stored.deliverables == 3
    assert stored.capabilities == []
    assert stored.covered_shifts == ["T01", "T02"]
    assert stored.news.gated["missing"] == 1
    assert (stored.gating_errors, stored.exit_code) == (1, 1)
    assert EVAL_NAME.fullmatch(NAME)


def test_e10_an_old_file_without_deliverables_and_causes_still_parses(tmp_path: Path) -> None:
    path = _e32_written(tmp_path)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    del data["deliverables"], data["causes"]
    path.write_text(json.dumps(data), encoding="utf-8")
    stored = read_summary(path)
    assert stored.deliverables is None
    assert (stored.causes.gated, stored.causes.not_gated) == ({}, {})


def test_e10_a_broken_file_raises_a_named_value_error(tmp_path: Path) -> None:
    path = tmp_path / NAME
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match=f"^{NAME} is not a readable evaluation summary$"):
        read_summary(path)


def test_e10_after_a_write_the_directory_holds_only_eval_files(tmp_path: Path) -> None:
    _e32_written(tmp_path / "evals")
    assert [p.name for p in (tmp_path / "evals").iterdir()] == [NAME]


def test_write_summary_json_leaves_no_temp_file_when_the_replace_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Risk: a failed replace leaves a '.tmp' file that a later directory scan could mistake for a summary."""

    def boom(src: object, dst: object) -> None:
        raise OSError("disk gone")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk gone"):
        write_summary_json({"registry": "r"}, tmp_path, AT)
    assert list(tmp_path.iterdir()) == []
