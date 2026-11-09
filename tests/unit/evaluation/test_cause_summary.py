"""008 T15: causes in the summary, the table, the JSON, gating and 'run_eval' (E30, E31, R19, R20)."""

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_cause_builders import t21_shifts, with_cause

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import CauseCategory, Evidence
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.models import SnapshotCommit
from plant_monitor.evaluation.cli import run_eval
from plant_monitor.evaluation.golden import Capability
from plant_monitor.evaluation.results import tally
from plant_monitor.evaluation.summary import EvalSummary, evaluate, exit_code, render_table

from builders import FIXTURE_PLANT
from eval_builders import (
    SEL,
    alert,
    fixture_shifts,
    golden_alert,
    golden_cause,
    golden_evidence,
    golden_file,
    golden_news,
    golden_set,
    news,
    report,
    run_output,
    write_golden,
)

SE = "S005-SUV-Europa"
PL10 = "S010-Pickup-Local"
PB10 = "S010-Pickup-Brasil"
F2 = "llegó la auditoría de homologación y retuvo en calidad las SUV de exportación"
T02_TEXT = f"Turno tarde T02.\nA las 10 {F2}.\n"
AGENT = frozenset({Capability.AGENT})
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)


def _golden_cause(case_id: str = SE) -> dict[str, object]:
    return golden_cause(
        case_id,
        "alerta_inmediata",
        "retencion_de_calidad",
        "calidad",
        requires=["agent"],
        evidencia=golden_evidence("T02", F2),
    )


def _e25_summary(caps: frozenset[Capability]) -> EvalSummary:
    """E25's categoria miss on a 'requires [agent]' item, evaluated with 'caps'."""
    golden = golden_set(("T03",), alerts=[golden_alert(SE, "S005")], causes=[_golden_cause()])
    cited = [Evidence(bitacora="T02", fragmento=F2)]
    miss = with_cause(alert("S005", SE), CauseCategory.LINE_STOP, Stage.QUALITY, cited)
    return evaluate(
        run_output([miss], [report("T03", "S006")]),
        golden,
        fixture_shifts(),
        capabilities=caps,
        registry="r",
        golden_dir="g",
        logbooks={"T02": T02_TEXT},
    )


def test_e30a_an_unmet_requires_cause_error_is_not_gated_until_the_capability_is_declared() -> None:
    released = _e25_summary(frozenset())
    assert tally(released.causes, gated=False) == {"categoria_mismatch": 1}
    assert released.gating_errors == 0

    gated = _e25_summary(AGENT)
    assert tally(gated.causes, gated=True) == {"categoria_mismatch": 1}
    assert (gated.gating_errors, exit_code(gated)) == (1, 1)


def test_e30b_the_table_and_the_json_have_a_causes_section() -> None:
    summary = _e25_summary(frozenset())
    assert any(line.startswith("causes") for line in render_table(summary).splitlines())
    data: dict[str, Any] = summary.to_json()
    assert data["causes"]["gated"] == {}
    assert data["causes"]["not_gated"] == {"categoria_mismatch": 1}
    assert [r["label"] for r in data["causes"]["results"]] == ["g.yaml#causes[0]"]


def _write_registry(path: Path) -> None:
    """S001 to S004 where the S004 alert of the Sedán case cites T02 (loaded) and T99 (unknown)."""
    cited = [Evidence(bitacora="T02", fragmento=F2), Evidence(bitacora="T99", fragmento="x")]
    target = with_cause(alert("S004", SEL), CauseCategory.QUALITY_HOLD, Stage.QUALITY, cited)
    with SqliteRegistry(path) as registry:
        for snapshot in ("S001", "S002", "S003", "S004"):
            commit = SnapshotCommit(
                snapshot_id=snapshot, content_hash=f"hash-{snapshot}", anomalies=(), new_units={}
            )
            with registry.processing(commit):
                if snapshot == "S004":
                    registry.notices.save(snapshot, (target,), report("T02", "S004"))
                else:
                    registry.notices.save(snapshot, (), None)


def test_e30c_run_evidence_of_an_unloaded_logbook_gates_without_a_load_error(tmp_path: Path) -> None:
    registry = tmp_path / "registry.sqlite3"
    _write_registry(registry)
    logbooks = tmp_path / "logbooks"
    logbooks.mkdir()
    (logbooks / "T02.txt").write_text(T02_TEXT, encoding="utf-8")
    golden_dir = tmp_path / "golden"
    golden_dir.mkdir()
    golden = golden_file(["T02"], alerts=[golden_alert(SEL, "S004")], causes=[_golden_cause(SEL)])
    write_golden(golden_dir, "day_01.yaml", golden)
    out, err = io.StringIO(), io.StringIO()

    code = run_eval(
        registry=registry,
        golden_dir=golden_dir,
        shifts_path=FIXTURE_PLANT / "turnos.csv",
        logbooks_dir=logbooks,
        first_held_out_shift="T03",
        held_out_open=False,
        capabilities=AGENT,
        out_dir=tmp_path / "evals",
        now=NOW,
        out=out,
        err=err,
    )

    (summary,) = (tmp_path / "evals").glob("eval-*.json")
    causes = json.loads(summary.read_text(encoding="utf-8"))["causes"]
    assert err.getvalue() == ""
    assert code == 1
    assert causes["gated"] == {"evidence_not_loaded": 1}


def test_e31_an_unmet_raise_item_releases_only_its_own_case() -> None:
    golden = golden_set(
        ("T05",),
        alerts=[golden_alert(PL10, "S010", requires=["agent"])],
        news=[golden_news("T05", PL10, "escalado", "critica", "critica", requires=["agent"])],
    )
    extra = news("S010", PB10, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM)
    summary = evaluate(
        run_output([], [report("T05", "S010", [extra])]),
        golden,
        t21_shifts(),
        capabilities=frozenset(),
        registry="r",
        golden_dir="g",
    )
    results = [*summary.alerts, *summary.news]
    assert {r.gated for r in results if r.case_id == PL10} == {False}
    assert tally(summary.news, gated=True) == {"extra": 1}
    assert tally(summary.alerts, gated=True) == {}
    assert summary.gating_errors == 1
