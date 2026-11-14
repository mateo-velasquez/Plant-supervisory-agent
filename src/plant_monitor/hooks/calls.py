"""Lenient readers of emit-call arguments: a malformed argument yields nothing, never an error (I4, X4)."""

from collections.abc import Mapping
from typing import Final

from plant_monitor.domain.notices import Notice
from plant_monitor.hooks.chain import ToolCall
from plant_monitor.hooks.view import SnapshotView
from plant_monitor.mcp_server.types import EMIT_ALERT, EMIT_SHIFT_REPORT

EMIT_TOOLS: Final = (EMIT_ALERT, EMIT_SHIFT_REPORT)


def _items(call: ToolCall) -> tuple[Mapping[str, object], ...]:
    """The well-shaped argument mappings of an emit call: the call itself, or each report item."""
    if call.name == EMIT_ALERT:
        return (call.arguments,)
    if call.name == EMIT_SHIFT_REPORT:
        textos = call.arguments.get("textos")
        if isinstance(textos, list):
            return tuple(item for item in textos if isinstance(item, Mapping))
    return ()


def emitted_case_ids(call: ToolCall) -> tuple[str, ...]:
    """String 'case_id's of an emit call, in order; anything else is skipped."""
    ids = (item.get("case_id") for item in _items(call))
    return tuple(case_id for case_id in ids if isinstance(case_id, str))


def targets(call: ToolCall, view: SnapshotView) -> tuple[tuple[str, Notice, str], ...]:
    """(case_id, notice, texto) per emitted text that has a decided notice and a string 'texto'."""
    notices = view.alerts() if call.name == EMIT_ALERT else view.news()
    by_case = {notice.case_id: notice for notice in notices}
    found: list[tuple[str, Notice, str]] = []
    for item in _items(call):
        case_id, texto = item.get("case_id"), item.get("texto")
        if isinstance(case_id, str) and isinstance(texto, str) and case_id in by_case:
            found.append((case_id, by_case[case_id], texto))
    return tuple(found)
