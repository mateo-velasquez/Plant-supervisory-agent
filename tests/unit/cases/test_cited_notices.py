"""008 T5: notices carry the cited cause and its template sentence (E15, R12)."""

# ruff: noqa: RUF001

import pytest

from plant_monitor.cases.facts import CaseFacts
from plant_monitor.cases.notice_builder import build_snapshot_notices, case_notice
from plant_monitor.cases.templates import cause_text
from plant_monitor.cases.tracker import CaseDelta, TrackedEvent
from plant_monitor.domain.cases import CaseEvent, CaseState
from plant_monitor.domain.causes import Cause, CauseCategory, CitedCause, Evidence
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import NoticeType

from builders import PICKUP_BRAZIL, case_with, combination_of, history_row, measured

F2 = "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
CITED = CitedCause(
    categoria=CauseCategory.QUALITY_HOLD,
    etapa=Stage.QUALITY,
    evidence=Evidence(bitacora="T02", fragmento=F2),
    set_at="S018",
)
E23_TEXT = (
    "Pickup × Brasil escaló a crítica en S020 por gap: gap −12 u (−40 %), retraso 1 día. "
    "Causa no declarada, etapa montaje."
)


def e23_facts(cited: CitedCause | None) -> CaseFacts:
    """004 E23's case and metrics at S020 with cause row 'montaje', optionally with a cited cause."""
    case = case_with(
        "S015-Pickup-Brasil", CaseState.ESCALATED, Severity.CRITICAL, Severity.CRITICAL, at="S020"
    )
    current = measured(PICKUP_BRAZIL, -12.0, -40.0, 1.0, Stage.ASSEMBLY, Severity.CRITICAL, Severity.HIGH)
    row = history_row(case.case_id, "S020", Stage.ASSEMBLY, minimum=Severity.CRITICAL)
    return CaseFacts(case, current, row, cited=cited)


@pytest.mark.parametrize(
    ("cited", "causa", "evidencia", "text"),
    [
        (
            CITED,
            {"categoria": "retencion_de_calidad", "etapa": "calidad"},
            [{"bitacora": "T02", "fragmento": F2}],
            E23_TEXT.removesuffix("Causa no declarada, etapa montaje.")
            + "Causa: retención de calidad, etapa calidad (bitácora T02).",
        ),
        (None, {"categoria": "no_declarada", "etapa": "montaje"}, [], E23_TEXT),
    ],
    ids=["a_cited", "b_none_equals_004_e23"],
)
def test_e15ab_alert_carries_the_cited_cause_or_the_default(
    cited: CitedCause | None, causa: dict[str, str], evidencia: list[dict[str, str]], text: str
) -> None:
    notice = case_notice(NoticeType.ALERT, e23_facts(cited), "S020").model_dump(mode="json")
    assert (notice["causa"], notice["evidencia"], notice["texto"]) == (causa, evidencia, text)


@pytest.mark.parametrize(
    ("categoria", "label"),
    [
        (CauseCategory.LINE_STOP, "parada de línea"),
        (CauseCategory.MISSING_PARTS, "faltante de piezas"),
        (CauseCategory.REWORK, "retrabajo"),
        (CauseCategory.QUALITY_HOLD, "retención de calidad"),
        (CauseCategory.ABSENTEEISM, "ausentismo"),
    ],
)
def test_e15c_cause_text_for_each_declared_category(categoria: CauseCategory, label: str) -> None:
    cited = CitedCause(
        categoria=categoria,
        etapa=Stage.ASSEMBLY,
        evidence=Evidence(bitacora="T05", fragmento="se paró la línea"),
        set_at="S010",
    )
    text = cause_text(cited.cause, e23_facts(cited))
    assert text == f"Causa: {label}, etapa montaje (bitácora T05)."


def test_snapshot_notices_apply_the_cited_mapping_only_to_the_cases_in_it() -> None:
    """Risk: the mapping is ignored or applied to every case, so an uncited alert gets a made-up cause."""
    ids = ("S010-Pickup-Brasil", "S010-Pickup-Local")
    cases = tuple(case_with(i, CaseState.ESCALATED, Severity.CRITICAL, Severity.CRITICAL) for i in ids)
    delta = CaseDelta(
        "S010",
        tuple(
            e
            for c in cases
            for e in (TrackedEvent(c.case_id, CaseEvent.OPENED), TrackedEvent(c.case_id, CaseEvent.ESCALATED))
        ),
        cases,
    )
    metrics = {
        combination_of(i): measured(
            combination_of(i), -11.0, -36.7, 0.0, Stage.ASSEMBLY, Severity.CRITICAL, Severity.NONE
        )
        for i in ids
    }
    rows = {
        i: history_row(i, "S010", Stage.ASSEMBLY, minimum=Severity.CRITICAL, state=CaseState.ESCALATED)
        for i in ids
    }
    built = build_snapshot_notices(delta, metrics, rows, None, cited={ids[0]: CITED})
    by_case = {n.case_id: n for n in built.decisions}
    assert by_case[ids[0]].causa == CITED.cause
    assert by_case[ids[0]].evidencia == (CITED.evidence,)
    assert by_case[ids[1]].causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY)
    assert by_case[ids[1]].evidencia == ()
