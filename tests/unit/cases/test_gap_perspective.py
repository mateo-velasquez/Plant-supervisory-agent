"""009 T12: the gap perspective of a case (R10, E15a-b)."""

import pytest

from plant_monitor.cases.perspectives import gap_perspective
from plant_monitor.domain.cases import CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination
from plant_monitor.domain.perspectives import GapAtReport, GapPerspective

from builders import case_with, history_row, metrics_with

SE = Combination(modelo=Model.SUV, mercado=Market.EUROPE)
SE_CASE = "S005-SUV-Europa"


def _row(snapshot_id: str, units: float, pct: float | None) -> CaseHistoryRow:
    row = history_row(SE_CASE, snapshot_id, Stage.QUALITY)
    return row.model_copy(update={"gap_units": units, "gap_pct": pct})


def test_e15a_gap_now_and_at_the_last_report_are_rounded() -> None:
    """E15a: SE at S008, reported at S006: 'en_ultimo_informe' comes from the S006 history row."""
    case = case_with(
        SE_CASE,
        CaseState.FOLLOW_UP,
        Severity.MEDIUM,
        Severity.MEDIUM,
        at="S008",
        reported=(CaseState.OPEN, Severity.MEDIUM, "S006"),
    )
    history = [
        _row("S005", -4.0, -13.3333),
        _row("S006", -4.0, -13.3333),
        _row("S007", 0.0, 0.0),
        _row("S008", 0.0, 0.0),
    ]
    now = metrics_with(Severity.NONE, combination=SE, gap_units=0.0, gap_pct=0.0)
    assert gap_perspective(case, now, history) == GapPerspective(
        unidades=0.0,
        pct_plan_diario=0.0,
        en_ultimo_informe=GapAtReport(snapshot_id="S006", unidades=-4.0, pct_plan_diario=-13.3),
    )


def test_e15b_a_case_never_reported_has_no_last_report() -> None:
    """E15b: SE@S005, never reported: 'en_ultimo_informe' is None and the gap is rounded."""
    case = case_with(SE_CASE, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM)
    now = metrics_with(Severity.MEDIUM, combination=SE, gap_units=-4.0, gap_pct=-13.3333)
    assert gap_perspective(case, now, [_row("S005", -4.0, -13.3333)]) == GapPerspective(
        unidades=-4.0, pct_plan_diario=-13.3, en_ultimo_informe=None
    )


def test_risk_a_report_with_no_history_row_raises_instead_of_inventing_a_gap() -> None:
    """Risk: 'last_reported_at' with no stored row must raise, not show a made-up report gap."""
    case = case_with(
        SE_CASE,
        CaseState.FOLLOW_UP,
        Severity.MEDIUM,
        Severity.MEDIUM,
        at="S008",
        reported=(CaseState.OPEN, Severity.MEDIUM, "S006"),
    )
    now = metrics_with(Severity.MEDIUM, combination=SE, gap_units=-4.0, gap_pct=-13.3)
    with pytest.raises(ValueError, match="S006"):
        gap_perspective(case, now, [_row("S005", -4.0, -13.3)])
