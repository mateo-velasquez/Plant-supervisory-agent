"""007 T7: the brief the model receives for E41's S003 (R2, E2)."""

import json

from plant_monitor.agents.brief import render_brief
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.enums import Severity, ShiftPosition
from plant_monitor.domain.notices import NoticeType

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
            "borrador": E22D_TEXT,
        }
    ]
