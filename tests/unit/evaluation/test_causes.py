"""008 T14: 'score_causes' and the cause result keys (E24-E29, R19)."""

from collections.abc import Mapping, Sequence

import pytest
from eval_cause_builders import t21_shifts, with_cause

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import CauseCategory, Evidence
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import Notice
from plant_monitor.evaluation.causes import score_causes
from plant_monitor.evaluation.golden import Capability, GoldenSet
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.evaluation.results import CAUSE_ERRORS, Result, Section, errors, tally

from eval_builders import (
    alert,
    golden_alert,
    golden_cause,
    golden_evidence,
    golden_set,
    news,
    report,
    run_output,
)

SE = "S005-SUV-Europa"
PB = "S010-Pickup-Brasil"
SB = "S005-SUV-Brasil"
F2 = "llegó la auditoría de homologación y retuvo en calidad las SUV de exportación"
RUN_F2 = F2.replace("calidad las", "calidad\nlas")
F3 = "se revisó la estación final"
T02_TEXT = f"Turno tarde T02.\nA las 10 {RUN_F2}.\n"
LOGBOOKS = {"T02": T02_TEXT}
AGENT = frozenset({Capability.AGENT})
NONE: frozenset[Capability] = frozenset()
QUALITY_HOLD, UNDECLARED = CauseCategory.QUALITY_HOLD, CauseCategory.UNDECLARED
RUN_EVIDENCE = Evidence(bitacora="T02", fragmento=RUN_F2)


def _score(
    run: RunOutput,
    golden: GoldenSet,
    logbooks: Mapping[str, str] = LOGBOOKS,
    caps: frozenset[Capability] = AGENT,
) -> tuple[Result, ...]:
    return score_causes(run, golden, t21_shifts(), logbooks, caps)


def _golden_alert_cause(**fields: object) -> GoldenSet:
    cause = golden_cause(
        SE,
        "alerta_inmediata",
        "retencion_de_calidad",
        "calidad",
        requires=["agent"],
        evidencia=golden_evidence("T02", F2),
    )
    cause.update(fields)
    return golden_set(("T03",), alerts=[golden_alert(SE, "S005")], causes=[cause])


def _run_alert(
    categoria: CauseCategory = QUALITY_HOLD,
    etapa: Stage | None = Stage.QUALITY,
    evidence: Sequence[Evidence] = (RUN_EVIDENCE,),
    snapshot: str = "S005",
) -> Notice:
    return with_cause(alert(snapshot, SE), categoria, etapa, evidence)


def _run(*alerts: Notice) -> RunOutput:
    return run_output(alerts, [report("T03", "S006")])


def test_e24_cause_hit_tolerates_a_line_break_in_the_fragment() -> None:
    results = _score(_run(_run_alert()), _golden_alert_cause())
    assert [(r.section, r.case_id, r.where) for r in results] == [(Section.CAUSES, SE, "S005")]
    assert results[0].label == "g.yaml#causes[0]"
    assert tally(results, gated=True) == {"hit": 1}
    assert errors(tally(results), CAUSE_ERRORS) == 0


def test_e25_a_different_categoria_is_a_mismatch() -> None:
    run = _run(_run_alert(CauseCategory.LINE_STOP))
    assert tally(_score(run, _golden_alert_cause())) == {"categoria_mismatch": 1}


@pytest.mark.parametrize(
    ("evidence", "key"),
    [
        pytest.param(
            [Evidence(bitacora="T02", fragmento="retuvo las SUV en calidad")], "evidence_not_verbatim", id="a"
        ),
        pytest.param([Evidence(bitacora="T09", fragmento=F2)], "evidence_not_loaded", id="b"),
        pytest.param([], "evidence_missing", id="c"),
        pytest.param([Evidence(bitacora="T02", fragmento="L" + F2[1:])], "evidence_not_verbatim", id="d"),
        pytest.param([Evidence(bitacora="T03", fragmento=F3)], "evidence_not_available", id="e"),
    ],
)
def test_e26_run_evidence_failures(evidence: list[Evidence], key: str) -> None:
    logbooks = {**LOGBOOKS, "T03": f"Turno noche T03.\n{F3}.\n"}
    results = _score(_run(_run_alert(evidence=evidence)), _golden_alert_cause(), logbooks)
    assert tally(results) == {key: 1}


def test_e27_gap_only_alert_with_a_stage_is_an_etapa_mismatch() -> None:
    golden = golden_set(("T05",), alerts=[golden_alert(PB, "S010")], causes=[golden_cause(PB)])
    run = run_output([with_cause(alert("S010", PB), UNDECLARED, Stage.ASSEMBLY)], [report("T05", "S010")])
    results = _score(run, golden, {}, NONE)
    assert tally(results, gated=True) == {"etapa_mismatch": 1}


def test_e28a_no_run_alert_for_the_case_is_target_missing() -> None:
    assert tally(_score(_run(), _golden_alert_cause())) == {"target_missing": 1}


def test_e28b_a_report_without_the_case_is_target_missing() -> None:
    cause = golden_cause(
        SE,
        "informe_de_turno",
        "retencion_de_calidad",
        "calidad",
        turno_id="T03",
        requires=["agent"],
        evidencia=golden_evidence("T02", F2),
    )
    golden = golden_set(("T03",), causes=[cause])
    assert tally(_score(_run(), golden)) == {"target_missing": 1}


def _t04_golden() -> GoldenSet:
    cause = golden_cause(
        SE,
        "informe_de_turno",
        "retencion_de_calidad",
        "calidad",
        turno_id="T04",
        requires=["agent"],
        evidencia=golden_evidence("T02", F2),
    )
    return golden_set(("T04",), causes=[cause])


def _t04_run(categoria: CauseCategory, evidence: Sequence[Evidence]) -> RunOutput:
    resolved = news("S008", SE, CaseState.RESOLVED, Severity.NONE)
    item = with_cause(resolved, categoria, Stage.QUALITY, evidence)
    return run_output([], [report("T04", "S008", [item])])


def test_e29a_resolution_news_must_keep_the_origin_cause() -> None:
    lost = _score(_t04_run(UNDECLARED, []), _t04_golden())
    kept = _score(_t04_run(QUALITY_HOLD, [RUN_EVIDENCE]), _t04_golden())
    assert tally(lost) == {"categoria_mismatch": 1}
    assert tally(kept) == {"hit": 1}


def test_e29b_a_news_cause_is_cited_from_the_shift_logbook() -> None:
    fragment = "Vuelven a la cabina de repintado."
    logbooks = {"T03": "Se separaron las SUV en Gris Grafito. Vuelven a la cabina de repintado."}
    cause = golden_cause(
        SB,
        "informe_de_turno",
        "retrabajo",
        "pintura",
        turno_id="T03",
        requires=["agent"],
        evidencia=golden_evidence("T03", fragment),
    )
    golden = golden_set(("T03",), causes=[cause])

    def run_with(categoria: CauseCategory, etapa: Stage | None, evidence: Sequence[Evidence]) -> RunOutput:
        item = with_cause(news("S006", SB), categoria, etapa, evidence)
        return run_output([], [report("T03", "S006", [item])])

    cited = Evidence(bitacora="T03", fragmento=fragment)
    hit = _score(run_with(CauseCategory.REWORK, Stage.PAINT, [cited]), golden, logbooks)
    miss = _score(run_with(UNDECLARED, None, []), golden, logbooks)
    assert tally(hit) == {"hit": 1}
    assert tally(miss) == {"categoria_mismatch": 1, "etapa_mismatch": 1}


def test_a_later_alert_of_the_case_does_not_replace_the_alert_at_the_expected_snapshot() -> None:
    """Risk: scoring the last alert of a repeating case would turn a correct cause into a miss."""
    later = _run_alert(UNDECLARED, Stage.ASSEMBLY, (), "S006")
    assert tally(_score(_run(_run_alert(), later), _golden_alert_cause())) == {"hit": 1}
