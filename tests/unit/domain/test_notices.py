"""004 T2: notice and report contract validators, enum values, JSON keys and deterministic IDs (E1-E3)."""

import pytest

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import (
    ActiveCaseRow,
    Notice,
    NoticeType,
    Origin,
    Reason,
    ShiftReport,
    notice_id_for,
    report_id_for,
)

E22A_TEXT = (
    "Pickup × Brasil escaló a crítica en S020 por gap: gap −12 u (−40 %), retraso 1 día. "  # noqa: RUF001
    "Causa no declarada, etapa montaje."
)
NOTICE_KEYS = {
    "notice_id",
    "snapshot_id",
    "case_id",
    "modelo",
    "mercado",
    "tipo",
    "severidad",
    "severidad_maxima",
    "estado",
    "origen",
    "motivo",
    "causa",
    "evidencia",
    "texto",
}


def alert_payload(**overrides: object) -> dict[str, object]:
    """The E23 alert for 'S015-Pickup-Brasil' at S020."""
    payload: dict[str, object] = {
        "notice_id": "S020-alerta_inmediata-S015-Pickup-Brasil",
        "snapshot_id": "S020",
        "case_id": "S015-Pickup-Brasil",
        "modelo": "Pickup",
        "mercado": "Brasil",
        "tipo": NoticeType.ALERT,
        "severidad": Severity.CRITICAL,
        "severidad_maxima": Severity.CRITICAL,
        "estado": CaseState.ESCALATED,
        "origen": Origin.THRESHOLD,
        "motivo": (Reason.GAP,),
        "causa": Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY),
        "evidencia": (),
        "texto": E22A_TEXT,
    }
    payload.update(overrides)
    return payload


def news_payload(
    snapshot_id: str = "S010", case_id: str = "S010-Pickup-Brasil", **overrides: object
) -> dict[str, object]:
    """A valid 'informe_de_turno' notice: 'en_seguimiento' / 'media' / max 'media', motivo gap."""
    payload: dict[str, object] = {
        "notice_id": f"{snapshot_id}-informe_de_turno-{case_id}",
        "snapshot_id": snapshot_id,
        "case_id": case_id,
        "modelo": "Pickup",
        "mercado": "Brasil",
        "tipo": NoticeType.SHIFT_REPORT,
        "severidad": Severity.MEDIUM,
        "severidad_maxima": Severity.MEDIUM,
        "estado": CaseState.FOLLOW_UP,
        "origen": Origin.THRESHOLD,
        "motivo": (Reason.GAP,),
        "causa": Cause(categoria=CauseCategory.UNDECLARED, etapa=None),
        "evidencia": (),
        "texto": "Pickup × Brasil: caso nuevo.",  # noqa: RUF001
    }
    payload.update(overrides)
    return payload


def row_payload(**overrides: object) -> dict[str, object]:
    """A valid 'casos_activos' row for 'S010-Pickup-Brasil'."""
    payload: dict[str, object] = {
        "case_id": "S010-Pickup-Brasil",
        "modelo": "Pickup",
        "mercado": "Brasil",
        "gap_unidades": -5.0,
        "gap_pct": -16.67,
        "retraso_dias": 0.0,
        "severidad": Severity.MEDIUM,
        "severidad_maxima": Severity.MEDIUM,
        "estado": CaseState.FOLLOW_UP,
        "etapa_cuello": Stage.ASSEMBLY,
    }
    payload.update(overrides)
    return payload


# --- E1 · Notice contract ---


def test_e1a_alert_builds_and_dumps_exactly_the_contract_keys() -> None:
    dumped = Notice.model_validate(alert_payload()).model_dump(mode="json")
    assert set(dumped) == NOTICE_KEYS
    assert dumped["motivo"] == ["gap"]
    assert dumped["causa"] == {"categoria": "no_declarada", "etapa": "montaje"}
    assert dumped["evidencia"] == []


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"origen": Origin.AGENT, "motivo": (Reason.GAP,)}, id="b-agente-without-bitacora"),
        pytest.param({"origen": Origin.THRESHOLD, "motivo": (Reason.LOGBOOK,)}, id="b-umbral-with-bitacora"),
        pytest.param({"motivo": (Reason.DELAY, Reason.GAP)}, id="c-out-of-order"),
        pytest.param({"motivo": (Reason.GAP, Reason.GAP)}, id="c-duplicate"),
        pytest.param({"severidad_maxima": Severity.HIGH}, id="d-max-below-current"),
        pytest.param({"notice_id": "S020-alerta-S015-Pickup-Brasil"}, id="f-wrong-notice-id"),
        pytest.param({"estado": CaseState.FOLLOW_UP}, id="g-alert-not-escalado"),
    ],
)
def test_e1_alert_with_an_inconsistent_field_raises(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        Notice.model_validate(alert_payload(**overrides))


@pytest.mark.parametrize(
    "overrides",
    [
        pytest.param({"severidad": Severity.MEDIUM, "motivo": ()}, id="media-with-empty-motivo"),
        pytest.param({"severidad": Severity.NONE, "motivo": (Reason.GAP,)}, id="ninguna-with-motivo"),
    ],
)
def test_e1e_motivo_must_be_empty_exactly_when_severity_is_ninguna(overrides: dict[str, object]) -> None:
    """Built on a valid news notice so only the 'motivo' rule is broken, not the alert rule."""
    Notice.model_validate(news_payload())
    with pytest.raises(ValueError):
        Notice.model_validate({**news_payload(), **overrides})


def test_e1h_enum_values_are_the_contract_values() -> None:
    assert [t.value for t in NoticeType] == ["alerta_inmediata", "informe_de_turno", "sin_aviso"]
    assert [o.value for o in Origin] == ["umbral", "agente"]
    assert [r.value for r in Reason] == ["gap", "retraso", "bitacora"]
    assert [c.value for c in CauseCategory] == [
        "parada_de_linea",
        "faltante_de_piezas",
        "retrabajo",
        "retencion_de_calidad",
        "ausentismo",
        "no_declarada",
    ]


# --- E2 · Report contract ---


def test_e2a_empty_report_builds_with_the_contract_keys() -> None:
    report = ShiftReport(turno_id="T05", snapshot_id="S010", novedades=(), casos_activos=())
    dumped = report.model_dump(mode="json")
    assert set(dumped) == {"turno_id", "snapshot_id", "novedades", "casos_activos"}
    assert dumped["novedades"] == []
    assert dumped["casos_activos"] == []


@pytest.mark.parametrize(
    ("snapshot_id", "novedades", "casos_activos"),
    [
        pytest.param("S020", [alert_payload()], [], id="b-alert-as-news"),
        pytest.param("S010", [news_payload(snapshot_id="S009")], [], id="c-news-of-another-snapshot"),
        pytest.param("S010", [], [row_payload(), row_payload()], id="d-duplicate-active-row"),
        pytest.param("S010", [news_payload(), news_payload()], [], id="duplicate-news-case"),
    ],
)
def test_e2_report_with_an_inconsistent_item_raises(
    snapshot_id: str, novedades: list[dict[str, object]], casos_activos: list[dict[str, object]]
) -> None:
    """'duplicate-news-case' covers the Behavior rule that 'case_id's are unique within 'novedades'."""
    with pytest.raises(ValueError):
        ShiftReport.model_validate(
            {
                "turno_id": "T05",
                "snapshot_id": snapshot_id,
                "novedades": [Notice.model_validate(n) for n in novedades],
                "casos_activos": [ActiveCaseRow.model_validate(r) for r in casos_activos],
            }
        )


def test_active_case_row_rejects_a_resolved_state() -> None:
    """Plan validator: a resolved case is never in 'casos_activos'."""
    ActiveCaseRow.model_validate(row_payload())
    with pytest.raises(ValueError):
        ActiveCaseRow.model_validate(row_payload(estado=CaseState.RESOLVED, severidad=Severity.NONE))


# --- E3 · IDs ---


def test_e3_notice_and_report_ids_are_deterministic() -> None:
    for _ in range(2):
        assert (
            notice_id_for("S020", NoticeType.ALERT, "S015-Pickup-Brasil")
            == "S020-alerta_inmediata-S015-Pickup-Brasil"
        )
        assert (
            notice_id_for("S003", NoticeType.NO_NOTICE, "S002-SUV-Local") == "S003-sin_aviso-S002-SUV-Local"
        )
        assert report_id_for("T01") == "T01-informe"
