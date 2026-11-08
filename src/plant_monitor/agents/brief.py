"""Brief and reminder texts the model receives (R2, R3)."""

import json
from collections.abc import Sequence

from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.notices import Notice

INSTRUCTION = (
    "Write the Spanish 'texto' for each notice below, starting from its 'borrador', "
    "and emit them with the write tools."
)
REMINDER = "Texts are still missing for these notice ids; write them with the write tools: "


def _item(notice: Notice) -> dict[str, object]:
    data = notice.model_dump(mode="json")
    return {
        "notice_id": data["notice_id"],
        "case_id": data["case_id"],
        "modelo": data["modelo"],
        "mercado": data["mercado"],
        "estado": data["estado"],
        "severidad": data["severidad"],
        "severidad_maxima": data["severidad_maxima"],
        "motivo": data["motivo"],
        "causa": data["causa"],
        "borrador": data["texto"],
    }


def render_brief(
    snapshot_id: str,
    turno_id: str,
    position: ShiftPosition,
    alerts: Sequence[Notice],
    news: Sequence[Notice],
) -> str:
    """The instruction line, a newline, then the snapshot's notices as compact JSON."""
    payload = {
        "snapshot_id": snapshot_id,
        "turno_id": turno_id,
        "posicion": position.value,
        "alertas": [_item(notice) for notice in alerts],
        "novedades": [_item(notice) for notice in news],
    }
    return f"{INSTRUCTION}\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


def render_reminder(missing: Sequence[str]) -> str:
    """A constant sentence plus the missing notice ids, comma-separated."""
    return f"{REMINDER}{', '.join(missing)}"
