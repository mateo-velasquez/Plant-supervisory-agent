"""Brief and reminder texts the model receives (R2, R3, R15)."""

import json
import re
from collections.abc import Sequence

from plant_monitor.domain.causes import ActiveCause
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.notices import Notice, notice_brief_item
from plant_monitor.domain.perspectives import CasePerspective
from plant_monitor.domain.proposals import ValidatedProposal

_TAG_COLLISION = re.compile(r"<(/?propuestas)", re.IGNORECASE)
INSTRUCTION = (
    "Apply the proposals below that fit the notices, with 'apply_proposal' (you may decline any), "
    "then write the Spanish 'texto' for each notice, starting from its 'borrador', "
    "and emit them with the write tools."
)
REMINDER = "Texts are still missing for these notice ids; write them with the write tools: "


def cause_item(cause: ActiveCause, case_ids: Sequence[str]) -> dict[str, object]:
    """One active cause as the brief and the investigator task show it."""
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


def _compact(payload: object) -> str:
    """Compact JSON on one line, non-ASCII kept."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render_proposals(snapshot_id: str, proposals: Sequence[ValidatedProposal]) -> str:
    """The '<propuestas>' block: one compact JSON line per proposal, own tags escaped (R10)."""
    lines = [_TAG_COLLISION.sub(r"&lt;\1", _compact(proposal.item())) for proposal in proposals]
    return "\n".join([f'<propuestas snapshot_id="{snapshot_id}">', *lines, "</propuestas>"])


def render_brief(
    snapshot_id: str,
    turno_id: str,
    position: ShiftPosition,
    alerts: Sequence[Notice],
    news: Sequence[Notice],
    active_causes: Sequence[tuple[ActiveCause, Sequence[str]]] = (),
    perspectives: Sequence[CasePerspective] = (),
    proposals: Sequence[ValidatedProposal] = (),
) -> str:
    """The instruction line, the snapshot's notices as compact JSON, then the proposals block if any."""
    payload = {
        "snapshot_id": snapshot_id,
        "turno_id": turno_id,
        "posicion": position.value,
        "alertas": [notice_brief_item(notice) for notice in alerts],
        "novedades": [notice_brief_item(notice) for notice in news],
        "causas_activas": [cause_item(cause, case_ids) for cause, case_ids in active_causes],
        "perspectivas": [perspective.model_dump(mode="json") for perspective in perspectives],
    }
    parts = [INSTRUCTION, _compact(payload)]
    if proposals:
        parts.append(render_proposals(snapshot_id, proposals))
    return "\n".join(parts)


def render_reminder(missing: Sequence[str]) -> str:
    """A constant sentence plus the missing notice ids, comma-separated."""
    return f"{REMINDER}{', '.join(missing)}"
