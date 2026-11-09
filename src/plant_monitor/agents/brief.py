"""Brief and reminder texts the model receives (R2, R3, R15)."""

import json
from collections.abc import Sequence

from plant_monitor.domain.causes import ActiveCause
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.notices import Notice, notice_brief_item

INSTRUCTION = (
    "Review the newly readable logbooks, record causes and raises with the judgment tools, "
    "then write the Spanish 'texto' for each notice below, starting from its 'borrador', "
    "and emit them with the write tools."
)
REMINDER = "Texts are still missing for these notice ids; write them with the write tools: "


def _cause_item(cause: ActiveCause, case_ids: Sequence[str]) -> dict[str, object]:
    return {
        "causa_activa": cause.active_cause_id,
        "categoria": cause.categoria.value,
        "etapa": cause.scope.etapa.value,
        "modelo": cause.scope.modelo.value,
        "mercado": None if cause.scope.mercado is None else cause.scope.mercado.value,
        "bitacora": cause.opened_by.bitacora,
        "fragmento": cause.opened_by.fragmento,
        "abierta_en": cause.opened_at,
        "casos": list(case_ids),
    }


def render_brief(
    snapshot_id: str,
    turno_id: str,
    position: ShiftPosition,
    alerts: Sequence[Notice],
    news: Sequence[Notice],
    active_causes: Sequence[tuple[ActiveCause, Sequence[str]]] = (),
) -> str:
    """The instruction line, a newline, then the snapshot's notices as compact JSON."""
    payload = {
        "snapshot_id": snapshot_id,
        "turno_id": turno_id,
        "posicion": position.value,
        "alertas": [notice_brief_item(notice) for notice in alerts],
        "novedades": [notice_brief_item(notice) for notice in news],
        "causas_activas": [_cause_item(cause, case_ids) for cause, case_ids in active_causes],
    }
    return f"{INSTRUCTION}\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


def render_reminder(missing: Sequence[str]) -> str:
    """A constant sentence plus the missing notice ids, comma-separated."""
    return f"{REMINDER}{', '.join(missing)}"
