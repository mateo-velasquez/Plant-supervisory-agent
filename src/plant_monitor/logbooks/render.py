"""Delimited rendering of a logbook for the model (R6, X1)."""

import re

from plant_monitor.logbooks.store import Logbook

_DELIMITER_COLLISION = re.compile(r"<(/?bitacora)", re.IGNORECASE)


def render_logbook(logbook: Logbook) -> str:
    """One '<bitacora>' block; colliding tags in the text get '<' escaped as '&lt;' (R6)."""
    body = _DELIMITER_COLLISION.sub(r"&lt;\1", logbook.text.rstrip("\n"))
    header = f'<bitacora turno_id="{logbook.turno_id}" cerrada_en="{logbook.closed_at}">'
    return "\n".join([header, body, "</bitacora>"])
