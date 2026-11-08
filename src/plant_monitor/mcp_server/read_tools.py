"""Read tools as pure sync functions over the frame and the stores; no 'mcp' import (R2, R3, R12)."""

import logging

from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.models import Combination
from plant_monitor.logbooks import render_logbook
from plant_monitor.mcp_server.budget import OverBudget, check_budget, fit_list, to_text
from plant_monitor.mcp_server.context import FrameHolder, ToolContext, UnknownCase
from plant_monitor.mcp_server.views import (
    AvailableLogbook,
    CaseView,
    DelayedUnitsView,
    LogbooksView,
    active_cases_view,
    case_view,
    delayed_units_view,
    deviations_view,
)

logger = logging.getLogger(__name__)


def list_available_logbooks(ctx: ToolContext, frames: FrameHolder) -> str:
    """Logbooks closed at the current snapshot, in calendar order (R2)."""
    snapshot_id = frames.current().snapshot_id
    rows = tuple(
        AvailableLogbook(turno_id=turno_id, cerrada_en=closed_at)
        for turno_id, closed_at in ctx.logbooks.available(snapshot_id)
    )
    view = LogbooksView(snapshot_id=snapshot_id, disponibles=rows)
    return check_budget(to_text(view), "list_available_logbooks", ctx.view_max_chars)


def get_logbook(ctx: ToolContext, frames: FrameHolder, turno_id: str) -> str:
    """One delimited logbook block readable at the current snapshot (R3, R6)."""
    snapshot_id = frames.current().snapshot_id
    text = render_logbook(ctx.logbooks.get(turno_id, snapshot_id))
    try:
        return check_budget(text, "get_logbook", ctx.logbook_max_chars)
    except OverBudget:
        logger.warning("get_logbook output over the logbook budget; raise LOGBOOK_MAX_CHARS")
        raise


def get_deviations(ctx: ToolContext, frames: FrameHolder) -> str:
    """Metric rows of every combination at the current snapshot (R8)."""
    view = deviations_view(frames.current(), ctx.cases.active_cases())
    return check_budget(to_text(view), "get_deviations", ctx.view_max_chars)


def get_active_cases(ctx: ToolContext, frames: FrameHolder) -> str:
    """Active cases with the current snapshot's values (R9)."""
    view = active_cases_view(frames.current(), ctx.cases.active_cases())
    return check_budget(to_text(view), "get_active_cases", ctx.view_max_chars)


def get_case(ctx: ToolContext, frames: FrameHolder, case_id: str) -> str:
    """One case with its last report and its history, newest first (R10)."""
    frames.current()
    case = ctx.cases.get_case(case_id)
    if case is None:
        raise UnknownCase(case_id)
    history = ctx.cases.history(case_id)

    def build(kept: int | None) -> CaseView:
        return case_view(case, history, kept)

    return fit_list(build(None), build, len(history), "get_case", ctx.view_max_chars)


def get_delayed_units(ctx: ToolContext, frames: FrameHolder, modelo: Model, mercado: Market) -> str:
    """FR-10 delayed units of one combination at the current snapshot (R11)."""
    frame = frames.current()
    combination = Combination(modelo=modelo, mercado=mercado)

    def build(kept: int | None) -> DelayedUnitsView:
        return delayed_units_view(frame, combination, ctx.plant, kept)

    full = build(None)
    return fit_list(full, build, len(full.unidades), "get_delayed_units", ctx.view_max_chars)
