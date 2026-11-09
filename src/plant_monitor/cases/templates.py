"""Spanish 'texto' templates and number formatting (FR-25); pure, plant-facing text."""

# ruff: noqa: RUF001, RUF002

from decimal import ROUND_HALF_UP, Decimal

from plant_monitor.cases.facts import CaseFacts
from plant_monitor.cases.novelty import NewsReason
from plant_monitor.domain.cases import Case, CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import Reason

MINUS = "−"
TIMES = "×"
ONE_DECIMAL = Decimal("0.1")
INTEGER = Decimal(1)

_SEVERITY_TEXT = {
    Severity.NONE: "ninguna",
    Severity.MEDIUM: "media",
    Severity.HIGH: "alta",
    Severity.CRITICAL: "crítica",
}
_STATE_TEXT = {
    CaseState.OPEN: "abierto",
    CaseState.FOLLOW_UP: "en seguimiento",
    CaseState.ESCALATED: "escalado",
    CaseState.RESOLVED: "resuelto",
}
_CATEGORY_TEXT = {
    CauseCategory.LINE_STOP: "parada de línea",
    CauseCategory.MISSING_PARTS: "faltante de piezas",
    CauseCategory.REWORK: "retrabajo",
    CauseCategory.QUALITY_HOLD: "retención de calidad",
    CauseCategory.ABSENTEEISM: "ausentismo",
}
_REASON_TEXT = {Reason.GAP: "gap", Reason.DELAY: "retraso", Reason.LOGBOOK: "bitácora"}


def _round(value: float, quantum: Decimal) -> Decimal:
    """Round on 'Decimal(str(value))', halves away from zero."""
    return Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)


def _decimal_comma(magnitude: Decimal) -> str:
    """Magnitude with a decimal comma and no trailing ',0'."""
    text = f"{magnitude:f}".replace(".", ",")
    return text.removesuffix(",0")


def _signed(rounded: Decimal, text: str) -> str:
    """Sign decided after rounding: minus, plus, or none for zero."""
    if rounded < 0:
        return f"{MINUS}{text}"
    if rounded > 0:
        return f"+{text}"
    return text


def format_units(value: float) -> str:
    """Gap units to one decimal, e.g. '−12 u', '−2,5 u', '+6 u', '0 u'."""
    rounded = _round(value, ONE_DECIMAL)
    return f"{_signed(rounded, _decimal_comma(abs(rounded)))} u"


def format_pct(value: float | None) -> str:
    """Gap percentage as an integer, e.g. '−38 %'; None (plan 0, Q-16) has its own phrase."""
    if value is None:
        return "sin plan en el turno"
    rounded = _round(value, INTEGER)
    return f"{_signed(rounded, str(abs(rounded)))} %"


def format_delay(days: float | None) -> str:
    """Delay phrase; 'sin retraso' and the singular are decided on the displayed rounded value."""
    if days is None:
        return "retraso fuera del horizonte de embarques"
    rounded = _round(days, ONE_DECIMAL)
    if rounded == 0:
        return "sin retraso"
    if rounded == 1:
        return "retraso 1 día"
    return f"retraso {_decimal_comma(rounded)} días"


def _combination(case: Case) -> str:
    return f"{case.combination.modelo} {TIMES} {case.combination.mercado}"


def cause_text(cause: Cause, facts: CaseFacts) -> str:
    """Cause sentence; the gap-only phrase only when 'facts' knows it (Q-17, Q-32)."""
    if cause.categoria is not CauseCategory.UNDECLARED:
        if facts.cited is None or cause.etapa is None:
            raise ValueError(f"{facts.case.case_id}: no template for cause {cause.categoria}")
        label, logbook = _CATEGORY_TEXT[cause.categoria], facts.cited.evidence.bitacora
        return f"Causa: {label}, etapa {cause.etapa} (bitácora {logbook})."
    if cause.etapa is not None:
        return f"Causa no declarada, etapa {cause.etapa}."
    if facts.cause_gap_only:
        return "Causa no declarada: desvío solo por gap, sin etapa cuello identificada."
    return "Causa no declarada, sin etapa cuello identificada."


def alert_text(facts: CaseFacts, snapshot_id: str, motivo: tuple[Reason, ...], cause: Cause) -> str:
    """Text of an 'alerta_inmediata'."""
    case, current = facts.case, facts.current
    if current is None:
        raise ValueError(f"{case.case_id}: an alert needs current metrics")
    why = " y ".join(_REASON_TEXT[reason] for reason in motivo)
    return (
        f"{_combination(case)} escaló a {_SEVERITY_TEXT[case.current_severity]} en {snapshot_id} por {why}: "
        f"gap {format_units(current.gap_units)} ({format_pct(current.gap_pct)}), "
        f"{format_delay(current.delay_days)}. {cause_text(cause, facts)}"
    )


def _change_phrases(case: Case, reasons: tuple[NewsReason, ...]) -> list[str]:
    """One phrase per reason; a resolved case omits 'severidad x → ninguna' (resolution implies it)."""
    resolved = case.state is CaseState.RESOLVED
    phrases: list[str] = []
    for reason in reasons:
        if reason is NewsReason.NEW:
            phrases.append("caso nuevo")
        elif reason is NewsReason.RESOLVED:
            phrases.append(f"resuelto en {case.resolved_at}")
        elif reason is NewsReason.STATE_CHANGED and case.last_reported_state is not None:
            phrases.append(f"estado {_STATE_TEXT[case.last_reported_state]} → {_STATE_TEXT[case.state]}")
        elif (
            reason is NewsReason.SEVERITY_CHANGED and not resolved and case.last_reported_severity is not None
        ):
            before = _SEVERITY_TEXT[case.last_reported_severity]
            phrases.append(f"severidad {before} → {_SEVERITY_TEXT[case.current_severity]}")
        elif reason is NewsReason.PEAK and case.max_severity_since_report is not None:
            phrases.append(f"pico de {_SEVERITY_TEXT[case.max_severity_since_report]}")
    return phrases


def news_text(facts: CaseFacts, reasons: tuple[NewsReason, ...], cause: Cause) -> str:
    """Text of a per-case 'informe_de_turno' entry."""
    case = facts.case
    peak = case.max_severity_since_report
    if peak is None:
        raise ValueError(f"{case.case_id}: a news item needs a max severity")
    changes = "; ".join(_change_phrases(case, reasons))
    return (
        f"{_combination(case)}: {changes}. Estado {_STATE_TEXT[case.state]}, "
        f"severidad {_SEVERITY_TEXT[case.current_severity]}, máxima {_SEVERITY_TEXT[peak]}. "
        f"{cause_text(cause, facts)}"
    )


def silent_text(case: Case) -> str:
    """Text of a 'sin_aviso' decision."""
    if case.last_reported_at is None:
        raise ValueError(f"{case.case_id}: a silent case was reported before")
    return f"{_combination(case)}: sin cambios desde el informe de {case.last_reported_at}."
