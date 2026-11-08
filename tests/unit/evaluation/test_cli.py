"""005 T13: 'run_eval' exit codes, gating by capability and summary writing (E37)."""

import io
import json
from collections.abc import Collection, Iterable
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plant_monitor.evaluation.cli import run_eval
from plant_monitor.evaluation.golden import Capability

from builders import FIXTURE_PLANT
from eval_builders import (
    PL,
    SEL,
    Item,
    golden_alert,
    golden_file,
    golden_news,
    write_e40_registry,
    write_golden,
)

NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)


def _golden_dir(
    tmp_path: Path, *, covers: Iterable[str] = ("T01", "T02"), extra_news: Collection[Item] = ()
) -> Path:
    """Write E37's 'day_01.yaml', which matches E40's registry exactly, plus 'extra_news'."""
    directory = tmp_path / "golden"
    directory.mkdir()
    news = [
        golden_news("T01", SEL),
        golden_news("T01", PL, "en_seguimiento", "media", "media"),
        golden_news("T02", SEL, "escalado", "critica", "critica"),
        *extra_news,
    ]
    write_golden(
        directory, "day_01.yaml", golden_file(list(covers), alerts=[golden_alert(SEL, "S003")], news=news)
    )
    return directory


def _missing_pl_t02(*, requires_agent: bool = False) -> Item:
    item = golden_news("T02", PL, "en_seguimiento", "media", "media")
    if requires_agent:
        item["requires"] = ["agent"]
    return item


class Outcome:
    """Exit code, both streams and the summaries written by one 'run_eval' call."""

    def __init__(self, code: int, out: str, err: str, summaries: list[Path]) -> None:
        self.code = code
        self.out = out
        self.err = err
        self.summaries = summaries


def _run(
    tmp_path: Path,
    golden_dir: Path,
    *,
    capabilities: frozenset[Capability] = frozenset(),
    registry: Path | None = None,
) -> Outcome:
    if registry is None:
        registry = tmp_path / "registry.sqlite3"
        write_e40_registry(registry)
    logbooks = tmp_path / "logbooks"
    logbooks.mkdir(exist_ok=True)
    out_dir = tmp_path / "evals"
    out, err = io.StringIO(), io.StringIO()
    code = run_eval(
        registry=registry,
        golden_dir=golden_dir,
        shifts_path=FIXTURE_PLANT / "turnos.csv",
        logbooks_dir=logbooks,
        first_held_out_shift="T03",
        held_out_open=False,
        capabilities=capabilities,
        out_dir=out_dir,
        now=NOW,
        out=out,
        err=err,
    )
    summaries = sorted(out_dir.glob("eval-*.json")) if out_dir.exists() else []
    return Outcome(code, out.getvalue(), err.getvalue(), summaries)


def test_e37a_an_exact_match_returns_zero_prints_the_table_and_writes_one_summary(tmp_path: Path) -> None:
    result = _run(tmp_path, _golden_dir(tmp_path))
    assert result.code == 0
    assert "alerts" in result.out
    assert "news" in result.out
    assert [p.name for p in result.summaries] == ["eval-20261107T120000Z.json"]
    assert str(result.summaries[0]) in result.out
    assert result.err == ""


def test_e37b_a_gated_missing_item_returns_one(tmp_path: Path) -> None:
    result = _run(tmp_path, _golden_dir(tmp_path, extra_news=[_missing_pl_t02()]))
    assert result.code == 1
    assert len(result.summaries) == 1


def test_e37c_an_item_requiring_the_agent_does_not_gate_when_capabilities_are_none(tmp_path: Path) -> None:
    golden = _golden_dir(tmp_path, extra_news=[_missing_pl_t02(requires_agent=True)])
    result = _run(tmp_path, golden)
    assert result.code == 0
    assert "not gated" in result.out
    assert "missing" in result.out
    news_section = json.loads(result.summaries[0].read_text(encoding="utf-8"))["news"]
    assert news_section["not_gated"] == {"missing": 1}
    assert "missing" not in news_section["gated"]


def test_e37d_the_same_item_gates_when_the_agent_capability_is_declared(tmp_path: Path) -> None:
    golden = _golden_dir(tmp_path, extra_news=[_missing_pl_t02(requires_agent=True)])
    assert _run(tmp_path, golden, capabilities=frozenset({Capability.AGENT})).code == 1


def test_e37e_a_held_out_covered_shift_returns_two_and_writes_nothing(tmp_path: Path) -> None:
    result = _run(tmp_path, _golden_dir(tmp_path, covers=("T01", "T02", "T03")))
    assert result.code == 2
    assert "T03" in result.err
    assert "held out" in result.err
    assert result.summaries == []


def test_e37f_a_missing_registry_returns_two_and_writes_nothing(tmp_path: Path) -> None:
    missing = tmp_path / "nope.sqlite3"
    result = _run(tmp_path, _golden_dir(tmp_path), registry=missing)
    assert result.code == 2
    assert str(missing) in result.err
    assert result.summaries == []
    assert not missing.exists()


def test_e37g_an_os_error_while_loading_returns_two_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A disk fault (not a 'ValueError') must still end as a load error, not a traceback."""

    def boom(*args: object, **kwargs: object) -> object:
        raise PermissionError("disk unreadable")

    monkeypatch.setattr("plant_monitor.evaluation.cli.load_golden", boom)
    result = _run(tmp_path, _golden_dir(tmp_path))
    assert result.code == 2
    assert "disk unreadable" in result.err
    assert result.summaries == []


def test_e37_no_logbook_is_read_when_the_golden_cites_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The plan names 'read_logbook_texts' in 'cli'; a reader that raises proves it is not called."""

    def boom(*args: object, **kwargs: object) -> dict[str, str]:
        raise AssertionError("a logbook was read")

    monkeypatch.setattr("plant_monitor.evaluation.cli.read_logbook_texts", boom)
    assert _run(tmp_path, _golden_dir(tmp_path)).code == 0
