"""009 builders: investigator tasks over the incident fixture (IF) and its logbook store."""

from incident_runs import AC1, EV_T02, SUV_EUROPE
from judgment_builders import PB_CASE, PL_CASE, incident_tool_context

from plant_monitor.agents.control import InvestigatorTask, TaskCase
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import ActiveCause, CauseCategory
from plant_monitor.domain.enums import Market, Model, ShiftPosition, Stage
from plant_monitor.logbooks.store import LogbookStore

SE_CASE = "S005-SUV-Europa"
S010_TASK = InvestigatorTask(
    snapshot_id="S010",
    turno_id="T05",
    position=ShiftPosition.CLOSING,
    logbooks=("T05",),
    cases=(
        TaskCase(
            case_id=PL_CASE,
            modelo=Model.PICKUP,
            mercado=Market.LOCAL,
            estado=CaseState.OPEN,
            etapa=Stage.ASSEMBLY,
        ),
        TaskCase(
            case_id=PB_CASE,
            modelo=Model.PICKUP,
            mercado=Market.BRAZIL,
            estado=CaseState.OPEN,
            etapa=Stage.ASSEMBLY,
        ),
    ),
    active_causes=(),
)
AC1_CAUSE = ActiveCause(
    active_cause_id=AC1,
    categoria=CauseCategory.QUALITY_HOLD,
    scope=SUV_EUROPE,
    opened_at="S004",
    opened_by=EV_T02,
)
S006_TASK = InvestigatorTask(
    snapshot_id="S006",
    turno_id="T03",
    position=ShiftPosition.CLOSING,
    logbooks=("T03",),
    cases=(),
    active_causes=((AC1_CAUSE, (SE_CASE,)),),
)


def incident_logbooks() -> LogbookStore:
    """The IF logbook store, open policy."""
    return incident_tool_context()[0].logbooks
