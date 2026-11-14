"""Synthetic snapshot view V and call builders for the 010 hook tests (spec 010 worked examples)."""

from collections.abc import Mapping
from dataclasses import dataclass

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import Notice, NoticeType, Origin, Reason, notice_id_for
from plant_monitor.hooks.chain import ToolCall

from builders import combination_of

PL = "S010-Pickup-Local"
SL = "S008-SUV-Local"
SE = "S005-SUV-Europa"
SEDAN_LOCAL = "S004-Sedán-Local"


def hook_notice(
    case_id: str,
    tipo: NoticeType,
    severity: Severity,
    maximum: Severity,
    state: CaseState,
    category: CauseCategory,
    stage: Stage,
) -> Notice:
    """A valid notice of snapshot S010 with the given severities and cause."""
    combo = combination_of(case_id)
    return Notice(
        notice_id=notice_id_for("S010", tipo, case_id),
        snapshot_id="S010",
        case_id=case_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        tipo=tipo,
        severidad=severity,
        severidad_maxima=maximum,
        estado=state,
        origen=Origin.THRESHOLD,
        motivo=() if severity is Severity.NONE else (Reason.GAP,),
        causa=Cause(categoria=category, etapa=stage),
        evidencia=(),
        texto="borrador",
    )


def a_pl() -> Notice:
    """The alert for PL: 'critica', 'escalado', 'parada_de_linea' at 'montaje'."""
    return hook_notice(
        PL,
        NoticeType.ALERT,
        Severity.CRITICAL,
        Severity.CRITICAL,
        CaseState.ESCALATED,
        CauseCategory.LINE_STOP,
        Stage.ASSEMBLY,
    )


def n_pl() -> Notice:
    """PL's news with the same values as its alert."""
    return hook_notice(
        PL,
        NoticeType.SHIFT_REPORT,
        Severity.CRITICAL,
        Severity.CRITICAL,
        CaseState.ESCALATED,
        CauseCategory.LINE_STOP,
        Stage.ASSEMBLY,
    )


def n_sl(severity: Severity = Severity.HIGH) -> Notice:
    """News for SL: 'en_seguimiento', max 'critica', 'no_declarada' at 'pintura'."""
    return hook_notice(
        SL,
        NoticeType.SHIFT_REPORT,
        severity,
        Severity.CRITICAL,
        CaseState.FOLLOW_UP,
        CauseCategory.UNDECLARED,
        Stage.PAINT,
    )


def n_se() -> Notice:
    """News for SE: 'en_seguimiento', 'media'/'media', 'no_declarada' at 'calidad'."""
    return hook_notice(
        SE,
        NoticeType.SHIFT_REPORT,
        Severity.MEDIUM,
        Severity.MEDIUM,
        CaseState.FOLLOW_UP,
        CauseCategory.UNDECLARED,
        Stage.QUALITY,
    )


@dataclass(frozen=True)
class FakeView:
    """A fake 'SnapshotView' holding fixed tuples."""

    alert_notices: tuple[Notice, ...] = ()
    news_notices: tuple[Notice, ...] = ()
    floor_levels: Mapping[str, Severity] | None = None
    missing_ids: tuple[str, ...] = ()

    def alerts(self) -> tuple[Notice, ...]:
        return self.alert_notices

    def news(self) -> tuple[Notice, ...]:
        return self.news_notices

    def floors(self) -> Mapping[str, Severity]:
        return self.floor_levels if self.floor_levels is not None else {}

    def missing(self) -> tuple[str, ...]:
        return self.missing_ids


def view_v(*, sl: Severity = Severity.HIGH, missing: tuple[str, ...] = ()) -> FakeView:
    """The spec's V at closing S010/T05; 'sl' sets nSL's severity."""
    return FakeView(
        alert_notices=(a_pl(),),
        news_notices=(n_pl(), n_sl(sl), n_se()),
        floor_levels={PL: Severity.MEDIUM, SL: Severity.HIGH, SE: Severity.MEDIUM},
        missing_ids=missing,
    )


def sa(case_id: str, texto: str) -> ToolCall:
    """'emit_alert' with a case id and text."""
    return ToolCall("emit_alert", {"case_id": case_id, "texto": texto})


def sr(*items: tuple[str, object]) -> ToolCall:
    """'emit_shift_report' with (case_id, texto) items."""
    return ToolCall("emit_shift_report", {"textos": [{"case_id": c, "texto": t} for c, t in items]})
