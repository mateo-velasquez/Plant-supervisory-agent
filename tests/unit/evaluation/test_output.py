"""005 T6: 'RunOutput' validators (E10)."""

import pytest

from plant_monitor.domain.notices import NoticeType
from plant_monitor.evaluation.output import RunOutput

from eval_builders import PL, SEL, alert, news, report


def test_e10a_an_informe_de_turno_among_the_alerts_is_rejected() -> None:
    with pytest.raises(ValueError):
        RunOutput(alerts=(news("S003", SEL, tipo=NoticeType.SHIFT_REPORT),), reports=())


def test_e10b_two_reports_with_one_turno_id_are_rejected() -> None:
    with pytest.raises(ValueError, match="T01"):
        RunOutput(alerts=(), reports=(report("T01", "S002"), report("T01", "S002")))


def test_e10c_the_same_alert_twice_is_rejected() -> None:
    with pytest.raises(ValueError, match="S003-alerta_inmediata"):
        RunOutput(alerts=(alert("S003", SEL), alert("S003", SEL)), reports=())


def test_e10d_alerts_for_one_case_at_two_snapshots_build() -> None:
    run = RunOutput(alerts=(alert("S003", SEL), alert("S005", SEL)), reports=())
    assert [a.snapshot_id for a in run.alerts] == ["S003", "S005"]


def test_run_output_accepts_distinct_cases_and_reports_in_order() -> None:
    """Happy path: processing order is kept."""
    run = RunOutput(
        alerts=(alert("S003", PL), alert("S003", SEL)),
        reports=(report("T02", "S004"), report("T01", "S002")),
    )
    assert [r.turno_id for r in run.reports] == ["T02", "T01"]
    assert [a.case_id for a in run.alerts] == [PL, SEL]
