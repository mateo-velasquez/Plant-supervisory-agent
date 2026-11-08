"""005 T11: 'EvalSummary', 'evaluate', 'exit_code', 'render_table' and 'write_summary' (E26, E33, E34)."""

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from plant_monitor.evaluation.golden import Capability
from plant_monitor.evaluation.noise import NoiseScore, RepeatedNews
from plant_monitor.evaluation.results import Result, Section
from plant_monitor.evaluation.summary import EvalSummary, evaluate, exit_code, render_table, write_summary

from eval_builders import (
    PB1,
    PL,
    SEL,
    alert,
    fixture_shifts,
    golden_alert,
    golden_news,
    golden_set,
    report,
    run_output,
)

NO_NOISE = NoiseScore(repeats=(), duplicate_alerts=())


def _summary(
    alerts: tuple[Result, ...] = (),
    news: tuple[Result, ...] = (),
    noise: NoiseScore = NO_NOISE,
) -> EvalSummary:
    return EvalSummary(
        registry="registry.sqlite3",
        golden="evals/golden",
        capabilities=frozenset(),
        covered_shifts=("T01",),
        alerts=alerts,
        news=news,
        noise=noise,
    )


def _result(section: Section, contributions: dict[str, int], *, gated: bool = True) -> Result:
    return Result(
        section=section,
        label="g.yaml#x",
        case_id=SEL,
        where="T01",
        contributions=contributions,
        gated=gated,
    )


def _alert(contributions: dict[str, int], *, gated: bool = True) -> tuple[Result, ...]:
    return (_result(Section.ALERTS, contributions, gated=gated),)


def _news(contributions: dict[str, int], *, gated: bool = True) -> tuple[Result, ...]:
    return (_result(Section.NEWS, contributions, gated=gated),)


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        pytest.param(_summary(_alert({"hit": 1}), _news({"hit": 1})), 0, id="a-clean"),
        pytest.param(
            _summary(
                _alert({"hit": 1, "motivo_mismatch": 1}),
                _news({"hit": 1, "estado_mismatch": 1, "severidad_mismatch": 1, "maxima_mismatch": 1}),
                NoiseScore(repeats=(), duplicate_alerts=((SEL, 2),)),
            ),
            0,
            id="b-attributes-and-duplicate-alerts-never-gate",
        ),
        pytest.param(_summary(news=_news({"extra": 1})), 1, id="c-gated-extra-news"),
        pytest.param(
            _summary(noise=NoiseScore(repeats=(RepeatedNews("T02", SEL, "T01"),), duplicate_alerts=())),
            1,
            id="d-noise-repeat",
        ),
        pytest.param(_summary(_alert({"duplicates": 1})), 1, id="e-gated-alert-duplicate"),
        pytest.param(
            _summary(_alert({"missing": 1}, gated=False), _news({"extra": 1, "missing": 1}, gated=False)),
            0,
            id="f-only-ungated-errors",
        ),
    ],
)
def test_e33_exit_code_follows_the_gating_errors(summary: EvalSummary, expected: int) -> None:
    assert exit_code(summary) == expected


def _e32_summary(depends_on: list[str] | None = None) -> EvalSummary:
    golden = golden_set(
        ("T01", "T02"),
        alerts=[golden_alert(SEL, "S003")],
        news=[
            golden_news("T01", PB1, "en_seguimiento", "ninguna", "media", depends_on=depends_on or ["Q-26"])
        ],
    )
    run = run_output([alert("S003", SEL)], [report("T01", "S002"), report("T02", "S004")])
    return evaluate(
        run,
        golden,
        fixture_shifts(),
        capabilities=frozenset(),
        registry="registry.sqlite3",
        golden_dir="evals/golden",
    )


def test_e32_evaluate_gates_a_missing_item_that_depends_on_a_question() -> None:
    summary = _e32_summary()
    assert summary.gating_errors == 1
    assert exit_code(summary) == 1


def test_e26_gating_counts_unscored_duplicate_alerts_as_zero() -> None:
    run = run_output([alert("S003", SEL), alert("S005", SEL), alert("S004", PL)], [report("T01", "S002")])
    summary = evaluate(
        run,
        golden_set(("T01",)),
        fixture_shifts(),
        capabilities=frozenset(),
        registry="r",
        golden_dir="g",
    )
    assert summary.noise.duplicate_alerts == ((SEL, 2),)
    assert summary.gating_errors == 0


def test_evaluate_keeps_the_capabilities_and_covered_shifts() -> None:
    golden = golden_set(("T01",))
    summary = evaluate(
        run_output([], [report("T01", "S002")]),
        golden,
        fixture_shifts(),
        capabilities=frozenset({Capability.AGENT}),
        registry="r",
        golden_dir="g",
    )
    assert summary.capabilities == {Capability.AGENT}
    assert summary.covered_shifts == ("T01",)
    assert (summary.registry, summary.golden) == ("r", "g")


def test_e34a_write_summary_names_the_file_in_utc_and_keeps_the_bytes_clean(tmp_path: Path) -> None:
    at = datetime(2026, 11, 7, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
    path = write_summary(_e32_summary(), tmp_path / "evals", at)
    assert path == tmp_path / "evals" / "eval-20261107T120000Z.json"
    raw = path.read_bytes()
    assert b"\r" not in raw
    assert raw.endswith(b"\n")
    assert not raw.endswith(b"\n\n")
    assert "Sedán".encode() in raw
    data: dict[str, Any] = json.loads(raw)
    assert {
        "registry",
        "golden",
        "capabilities",
        "covered_shifts",
        "alerts",
        "news",
        "noise",
        "gating_errors",
        "exit_code",
    } <= set(data)
    assert data["news"]["gated"]["missing"] == 1
    assert data["news"]["by_question"]["Q-26"]["missing"] == 1
    assert [r["label"] for r in data["news"]["results"]] == ["g.yaml#news[0]"]
    assert (data["gating_errors"], data["exit_code"]) == (1, 1)


def test_e34b_a_naive_timestamp_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_summary(_e32_summary(), tmp_path, datetime(2026, 11, 7, 9, 0))


def test_write_summary_accepts_utc_input_unchanged(tmp_path: Path) -> None:
    """Guards the conversion: a UTC input must not be shifted."""
    path = write_summary(_summary(), tmp_path, datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
    assert path.name == "eval-20260102T030405Z.json"


def test_e34c_the_table_shows_every_section_bucket_and_question() -> None:
    table = render_table(_e32_summary())
    for word in ("alerts", "news", "noise", "gated", "not gated", "Q-26"):
        assert word in table
