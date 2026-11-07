"""004 T7: Spanish number formatting and the exact notice texts (E21, E22)."""

# ruff: noqa: RUF001

import pytest

from plant_monitor.cases.facts import CaseFacts
from plant_monitor.cases.novelty import NewsReason
from plant_monitor.cases.templates import (
    alert_text,
    format_delay,
    format_pct,
    format_units,
    news_text,
    silent_text,
)
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import Reason

from builders import case_with, combination_of, history_row, measured

OPEN = CaseState.OPEN
FOLLOW_UP = CaseState.FOLLOW_UP
ESCALATED = CaseState.ESCALATED
RESOLVED = CaseState.RESOLVED
NONE = Severity.NONE
MEDIUM = Severity.MEDIUM
HIGH = Severity.HIGH
CRITICAL = Severity.CRITICAL


def cause(stage: Stage | None) -> Cause:
    """The 'no_declarada' cause with 'stage'."""
    return Cause(categoria=CauseCategory.UNDECLARED, etapa=stage)


def facts(
    case_id: str,
    state: CaseState,
    minimum: Severity,
    peak: Severity | None,
    *,
    at: str,
    current: tuple[float, float | None, float | None, Stage | None, Severity, Severity] | None,
    cause_at: str,
    cause_stage: Stage | None,
    raised: bool = False,
    reported: tuple[CaseState, Severity, str] | None = None,
    clean_streak: int = 0,
) -> CaseFacts:
    """Facts from a spec line: case values, the facts tuple at 'at' and the cause row."""
    case = case_with(
        case_id, state, minimum, peak, at=at, raised=raised, reported=reported, clean_streak=clean_streak
    )
    metrics = None if current is None else measured(combination_of(case_id), *current)
    row_minimum = max(minimum, MEDIUM) if cause_at == at else MEDIUM
    row = history_row(case_id, cause_at, cause_stage, minimum=row_minimum, raised=raised and cause_at == at)
    return CaseFacts(case, metrics, row)


# --- E21 · Formatting ---


@pytest.mark.parametrize(
    ("value", "text"),
    [(-12.0, "−12 u"), (-2.5, "−2,5 u"), (-2.25, "−2,3 u"), (6.0, "+6 u"), (0.0, "0 u"), (-0.04, "0 u")],
)
def test_e21_units(value: float, text: str) -> None:
    assert format_units(value) == text


@pytest.mark.parametrize(
    ("value", "text"),
    [(-37.5, "−38 %"), (-33.333, "−33 %"), (16.67, "+17 %"), (-0.4, "0 %"), (None, "sin plan en el turno")],
)
def test_e21_pct(value: float | None, text: str) -> None:
    assert format_pct(value) == text


@pytest.mark.parametrize(
    ("days", "text"),
    [
        (0.0, "sin retraso"),
        (1.0, "retraso 1 día"),
        (2.0, "retraso 2 días"),
        (1.5, "retraso 1,5 días"),
        (None, "retraso fuera del horizonte de embarques"),
    ],
)
def test_e21_delay(days: float | None, text: str) -> None:
    assert format_delay(days) == text


# --- E22 · Alert texts ---


@pytest.mark.parametrize(
    ("f", "snapshot_id", "motivo", "text"),
    [
        pytest.param(
            facts(
                "S015-Pickup-Brasil",
                ESCALATED,
                CRITICAL,
                CRITICAL,
                at="S020",
                current=(-12.0, -40.0, 1.0, Stage.ASSEMBLY, CRITICAL, HIGH),
                cause_at="S020",
                cause_stage=Stage.ASSEMBLY,
            ),
            "S020",
            (Reason.GAP,),
            "Pickup × Brasil escaló a crítica en S020 por gap: gap −12 u (−40 %), retraso 1 día. "
            "Causa no declarada, etapa montaje.",
            id="a",
        ),
        pytest.param(
            facts(
                "S018-SUV-Local",
                ESCALATED,
                CRITICAL,
                CRITICAL,
                at="S020",
                current=(-9.0, -37.5, 3.0, Stage.PAINT, CRITICAL, CRITICAL),
                cause_at="S020",
                cause_stage=Stage.PAINT,
            ),
            "S020",
            (Reason.GAP, Reason.DELAY),
            "SUV × Local escaló a crítica en S020 por gap y retraso: gap −9 u (−38 %), retraso 3 días. "
            "Causa no declarada, etapa pintura.",
            id="b",
        ),
        pytest.param(
            facts(
                "S018-Pickup-Brasil",
                ESCALATED,
                MEDIUM,
                CRITICAL,
                at="S020",
                current=(-4.0, -13.33, 0.0, Stage.ASSEMBLY, MEDIUM, NONE),
                cause_at="S020",
                cause_stage=Stage.ASSEMBLY,
                raised=True,
            ),
            "S020",
            (Reason.LOGBOOK,),
            "Pickup × Brasil escaló a crítica en S020 por bitácora: gap −4 u (−13 %), sin retraso. "
            "Causa no declarada, etapa montaje.",
            id="c",
        ),
        pytest.param(
            facts(
                "S001-Sedán-Local",
                ESCALATED,
                CRITICAL,
                CRITICAL,
                at="S003",
                current=(-18.0, -50.0, 0.0, None, CRITICAL, NONE),
                cause_at="S003",
                cause_stage=None,
            ),
            "S003",
            (Reason.GAP,),
            "Sedán × Local escaló a crítica en S003 por gap: gap −18 u (−50 %), sin retraso. "
            "Causa no declarada: desvío solo por gap, sin etapa cuello identificada.",
            id="d",
        ),
    ],
)
def test_e22_alert_text(f: CaseFacts, snapshot_id: str, motivo: tuple[Reason, ...], text: str) -> None:
    assert alert_text(f, snapshot_id, motivo, cause(f.cause_stage)) == text


# --- E22 · News and silent texts ---


@pytest.mark.parametrize(
    ("f", "reasons", "text"),
    [
        pytest.param(
            facts(
                "S001-Pickup-Brasil",
                OPEN,
                MEDIUM,
                MEDIUM,
                at="S001",
                current=(-5.0, -16.67, 0.0, Stage.ASSEMBLY, MEDIUM, NONE),
                cause_at="S001",
                cause_stage=Stage.ASSEMBLY,
            ),
            (NewsReason.NEW,),
            "Pickup × Brasil: caso nuevo. Estado abierto, severidad media, máxima media. "
            "Causa no declarada, etapa montaje.",
            id="e",
        ),
        pytest.param(
            facts(
                "S001-Pickup-Brasil",
                FOLLOW_UP,
                NONE,
                MEDIUM,
                at="S002",
                current=(0.0, 0.0, 0.0, None, NONE, NONE),
                cause_at="S001",
                cause_stage=Stage.ASSEMBLY,
                clean_streak=1,
            ),
            (NewsReason.NEW, NewsReason.PEAK),
            "Pickup × Brasil: caso nuevo; pico de media. Estado en seguimiento, severidad ninguna, "
            "máxima media. Causa no declarada, etapa montaje.",
            id="f",
        ),
        pytest.param(
            facts(
                "S001-Sedán-Local",
                ESCALATED,
                CRITICAL,
                CRITICAL,
                at="S004",
                current=(-24.0, -66.67, 0.0, None, CRITICAL, NONE),
                cause_at="S004",
                cause_stage=None,
                reported=(FOLLOW_UP, HIGH, "S002"),
            ),
            (NewsReason.STATE_CHANGED, NewsReason.SEVERITY_CHANGED),
            "Sedán × Local: estado en seguimiento → escalado; severidad alta → crítica. "
            "Estado escalado, severidad crítica, máxima crítica. "
            "Causa no declarada: desvío solo por gap, sin etapa cuello identificada.",
            id="g",
        ),
        pytest.param(
            facts(
                "S001-Pickup-Local",
                FOLLOW_UP,
                MEDIUM,
                HIGH,
                at="S004",
                current=(-4.0, -13.33, 0.0, None, MEDIUM, NONE),
                cause_at="S004",
                cause_stage=None,
                reported=(FOLLOW_UP, MEDIUM, "S002"),
            ),
            (NewsReason.PEAK,),
            "Pickup × Local: pico de alta. Estado en seguimiento, severidad media, máxima alta. "
            "Causa no declarada: desvío solo por gap, sin etapa cuello identificada.",
            id="h",
        ),
        pytest.param(
            facts(
                "S001-Pickup-Brasil",
                RESOLVED,
                NONE,
                NONE,
                at="S003",
                current=(0.0, 0.0, 0.0, None, NONE, NONE),
                cause_at="S001",
                cause_stage=Stage.ASSEMBLY,
                reported=(FOLLOW_UP, NONE, "S002"),
                clean_streak=2,
            ),
            (NewsReason.RESOLVED,),
            "Pickup × Brasil: resuelto en S003. Estado resuelto, severidad ninguna, máxima ninguna. "
            "Causa no declarada, etapa montaje.",
            id="i",
        ),
        pytest.param(
            facts(
                "S008-Pickup-Brasil",
                RESOLVED,
                NONE,
                CRITICAL,
                at="S012",
                current=(0.0, 0.0, 0.0, None, NONE, NONE),
                cause_at="S010",
                cause_stage=Stage.ASSEMBLY,
                reported=(FOLLOW_UP, MEDIUM, "S010"),
                clean_streak=2,
            ),
            (NewsReason.RESOLVED, NewsReason.SEVERITY_CHANGED, NewsReason.PEAK),
            "Pickup × Brasil: resuelto en S012; pico de crítica. Estado resuelto, severidad ninguna, "
            "máxima crítica. Causa no declarada, etapa montaje.",
            id="k-resolved-omits-severity-change",
        ),
        pytest.param(
            facts(
                "S009-Pickup-Local",
                FOLLOW_UP,
                NONE,
                NONE,
                at="S011",
                current=(0.0, 0.0, 0.0, None, NONE, NONE),
                cause_at="S010",
                cause_stage=None,
                reported=(FOLLOW_UP, MEDIUM, "S010"),
                clean_streak=1,
            ),
            (NewsReason.SEVERITY_CHANGED,),
            "Pickup × Local: severidad media → ninguna. Estado en seguimiento, severidad ninguna, "
            "máxima ninguna. Causa no declarada, sin etapa cuello identificada.",
            id="l-older-cause-row-has-no-gap-only-phrase",
        ),
    ],
)
def test_e22_news_text(f: CaseFacts, reasons: tuple[NewsReason, ...], text: str) -> None:
    assert news_text(f, reasons, cause(f.cause_stage)) == text


def test_e22j_silent_text() -> None:
    case = case_with("S002-SUV-Local", FOLLOW_UP, HIGH, HIGH, at="S003", reported=(FOLLOW_UP, HIGH, "S002"))
    assert silent_text(case) == "SUV × Local: sin cambios desde el informe de S002."


@pytest.mark.parametrize(
    ("days", "text"),
    [(0.04, "sin retraso"), (1.04, "retraso 1 día")],
)
def test_e21_delay_wording_follows_the_rounded_value(days: float, text: str) -> None:
    """Review finding: 'sin retraso' and the singular are decided after rounding to one decimal."""
    assert format_delay(days) == text
