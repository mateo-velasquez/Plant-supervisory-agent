"""Synthetic builders and golden reader for the 014 HTML report tests."""

from pathlib import Path

import pytest
from cli_builders import cli_deps

from plant_monitor.config import Settings
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory, Evidence
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.notices import (
    ActiveCaseRow,
    Notice,
    NoticeType,
    Origin,
    Reason,
    ShiftReport,
    notice_id_for,
)
from plant_monitor.runner.cli import main

from notice_builders import alert_notice, shift_report

GOLDEN = Path(__file__).resolve().parent / "fixtures" / "html"

N_SE = Notice(
    notice_id=notice_id_for("S010", NoticeType.SHIFT_REPORT, "S005-SUV-Europa"),
    snapshot_id="S010",
    case_id="S005-SUV-Europa",
    modelo=Model.SUV,
    mercado=Market.EUROPE,
    tipo=NoticeType.SHIFT_REPORT,
    severidad=Severity.CRITICAL,
    severidad_maxima=Severity.CRITICAL,
    estado=CaseState.ESCALATED,
    origen=Origin.AGENT,
    motivo=(Reason.LOGBOOK,),
    causa=Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY),
    evidencia=(
        Evidence(
            bitacora="T05",
            fragmento="la auditoría de homologación retuvo en calidad las SUV para Europa",
        ),
    ),
    texto="SUV \N{MULTIPLICATION SIGN} Europa escaló a crítica por bitácora: auditoría en calidad.",
)

N_PB = Notice(
    notice_id=notice_id_for("S010", NoticeType.SHIFT_REPORT, "S009-Pickup-Brasil"),
    snapshot_id="S010",
    case_id="S009-Pickup-Brasil",
    modelo=Model.PICKUP,
    mercado=Market.BRAZIL,
    tipo=NoticeType.SHIFT_REPORT,
    severidad=Severity.MEDIUM,
    severidad_maxima=Severity.HIGH,
    estado=CaseState.FOLLOW_UP,
    origen=Origin.THRESHOLD,
    motivo=(Reason.GAP,),
    causa=Cause(categoria=CauseCategory.UNDECLARED, etapa=None),
    evidencia=(),
    texto=(
        "Pickup \N{MULTIPLICATION SIGN} Brasil: caso nuevo; pico de alta. "
        "Estado en seguimiento, severidad media, máxima alta. "
        "Causa no declarada, sin etapa cuello identificada."
    ),
)

ROW_SE = ActiveCaseRow(
    case_id="S005-SUV-Europa",
    modelo=Model.SUV,
    mercado=Market.EUROPE,
    gap_unidades=-4.0,
    gap_pct=-13.33333,
    retraso_dias=0.0,
    severidad=Severity.CRITICAL,
    severidad_maxima=Severity.CRITICAL,
    estado=CaseState.ESCALATED,
    etapa_cuello=Stage.QUALITY,
)

ROW_PB = ActiveCaseRow(
    case_id="S009-Pickup-Brasil",
    modelo=Model.PICKUP,
    mercado=Market.BRAZIL,
    gap_unidades=-2.5,
    gap_pct=None,
    retraso_dias=None,
    severidad=Severity.MEDIUM,
    severidad_maxima=Severity.HIGH,
    estado=CaseState.FOLLOW_UP,
    etapa_cuello=None,
)

REPORT_T05 = ShiftReport(
    turno_id="T05", snapshot_id="S010", novedades=(N_SE, N_PB), casos_activos=(ROW_SE, ROW_PB)
)
A1 = alert_notice("S009", "S001-Sedán-Local")
EMPTY_T06 = shift_report("T06", "S012")


def variant(notice: Notice, **changes: object) -> Notice:
    """A notice with some fields replaced, validated again (no 'model_copy')."""
    return Notice.model_validate({**notice.model_dump(), **changes})


E6_ALERT = variant(
    alert_notice("S010", "S010-Pickup-Local"),
    origen=Origin.AGENT,
    motivo=(Reason.LOGBOOK,),
    evidencia=(Evidence(bitacora="T05", fragmento="<script>alert(1)</script></style>\x1b[31mrojo"),),
    texto='it\'s x" onmouseover="y',
)


def rendered(settings: Settings, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run 'plant-monitor html' with no model; return the exit code, stdout and stderr."""
    capsys.readouterr()
    code = main(["html"], deps=cli_deps(settings, None))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def golden(name: str) -> str:
    """Text of 'tests/fixtures/html/<name>' as UTF-8 with LF endings kept."""
    return (GOLDEN / name).read_text(encoding="utf-8", newline="")
