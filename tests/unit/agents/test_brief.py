"""007 T7: the brief the model receives for E41's S003 (R2, E2)."""

import json

from incident_runs import AC2, EV_T05, F5, PICKUP_ANY, incident_run

from plant_monitor.agents.brief import render_brief
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity, ShiftPosition
from plant_monitor.domain.notices import NoticeType, notice_brief_item

from notice_builders import make_notice

E22D_TEXT = (
    "Sedán × Local escaló a crítica en S003 por gap: gap −18 u (−50 %), sin retraso. "  # noqa: RUF001
    "Causa no declarada: desvío solo por gap, sin etapa cuello identificada."
)


def test_e2_brief_is_an_instruction_line_then_compact_json() -> None:
    """E2: line 1 is the instruction; line 2 holds the S003 alert with the template as 'borrador'."""
    alert = make_notice(
        "S003",
        NoticeType.ALERT,
        "S001-Sedán-Local",
        severity=Severity.CRITICAL,
        state=CaseState.ESCALATED,
        texto=E22D_TEXT,
        stage=None,
    )
    brief = render_brief("S003", "T02", ShiftPosition.MID, [alert], [])
    instruction, payload = brief.split("\n")
    assert instruction
    assert not instruction.startswith("{")
    parsed = json.loads(payload)
    assert payload == json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    assert parsed["snapshot_id"] == "S003"
    assert parsed["turno_id"] == "T02"
    assert parsed["posicion"] == "mid"
    assert parsed["novedades"] == []
    assert parsed["causas_activas"] == []
    assert parsed["alertas"] == [
        {
            "notice_id": "S003-alerta_inmediata-S001-Sedán-Local",
            "case_id": "S001-Sedán-Local",
            "modelo": "Sedán",
            "mercado": "Local",
            "estado": "escalado",
            "severidad": "critica",
            "severidad_maxima": "critica",
            "motivo": ["gap"],
            "causa": {"categoria": "no_declarada", "etapa": None},
            "evidencia": [],
            "borrador": E22D_TEXT,
        }
    ]


def test_e19_brief_lists_the_causes_in_force_and_shares_the_item_function() -> None:
    """E19, R15: 'causas_activas' from code; PE's alert item has 'evidencia' and equals the shared item."""
    with incident_run() as run:
        run.through(9)
        run.step(10, lambda d: run.raise_cause(d, CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05))
        decision = run.step(11)
    alerts = [n for n in decision.notices.decisions if n.tipo is NoticeType.ALERT]
    brief = render_brief("S011", "T06", decision.position, alerts, (), decision.in_force)
    instruction, payload = brief.split("\n")
    parsed = json.loads(payload)
    assert parsed["causas_activas"] == [
        {
            "causa_activa": AC2,
            "categoria": "parada_de_linea",
            "etapa": "montaje",
            "modelo": "Pickup",
            "mercado": None,
            "bitacora": "T05",
            "fragmento": F5,
            "abierta_en": "S010",
            "casos": ["S010-Pickup-Local", "S010-Pickup-Brasil", "S011-Pickup-Europa"],
        }
    ]
    (pe_alert,) = [n for n in alerts if n.case_id == "S011-Pickup-Europa"]
    (item,) = [a for a in parsed["alertas"] if a["case_id"] == "S011-Pickup-Europa"]
    assert item["evidencia"] == [{"bitacora": "T05", "fragmento": F5}]
    assert item == notice_brief_item(pe_alert)
    lowered = instruction.lower()
    assert lowered.index("logbook") < lowered.index("judgment") < lowered.index("text")
