"""JSON shapes of the dashboard API (014 plan, API); keys keep the data contract's names (ADR-0005)."""

from typing import Literal, TypedDict

from pydantic import JsonValue


class OmittedCounts(TypedDict):
    snapshots: int
    notices: int
    trace_lines: int


class HeldOut(TypedDict):
    open: bool
    omitted: OmittedCounts


class Cost(TypedDict):
    usd: str
    model_calls: int
    tokens: int


class Current(TypedDict):
    """The snapshot at the shown position; the shift fields are 'None' when 'turnos.csv' lacks it (X4)."""

    snapshot_id: str
    seq: int
    turno_id: str | None
    turno: str | None
    inicio: str | None
    fin: str | None
    fecha: str | None


class SnapshotCell(TypedDict):
    snapshot_id: str
    seq: int | None
    processed: bool
    alerts: int
    report: bool


class ShiftCell(TypedDict):
    turno_id: str
    turno: str | None
    inicio: str
    fin: str
    snapshots: list[SnapshotCell]


class Day(TypedDict):
    label: str
    shifts: list[ShiftCell]


class Kpis(TypedDict):
    active: int
    combinations: int
    critical: int
    critical_combinations: list[str]
    alerts: int
    reports: int
    shifts: int
    cost: Cost | None


class CauseView(TypedDict):
    categoria: str
    etapa: str | None


class EvidenceView(TypedDict):
    bitacora: str
    fragmento: str


class CaseView(TypedDict):
    case_id: str
    estado: str
    severidad: str
    gap_unidades: float
    gap_pct: float | None
    retraso_dias: float | None
    etapa_cuello: str | None
    causa: str
    etapa: str | None
    opened_at: str
    resolved_at: str | None


class Cell(TypedDict):
    modelo: str
    mercado: str
    status: Literal["calm", "active", "resolved"]
    case: CaseView | None
    series: list[float | None]


class NoticeItem(TypedDict):
    kind: Literal["alert", "news"]
    seq: int
    notice_id: str
    snapshot_id: str
    case_id: str
    modelo: str
    mercado: str
    severidad: str
    severidad_maxima: str
    estado: str
    motivo: list[str]
    origen: str
    causa: CauseView
    evidencia: list[EvidenceView]
    texto: str
    author: Literal["agent", "template", "unknown"]


class ReportItem(TypedDict):
    kind: Literal["report"]
    seq: int
    report_id: str
    turno_id: str
    snapshot_id: str
    novedades: list[NoticeItem]
    casos_activos: list[JsonValue]


class AgentsKpis(TypedDict):
    investigator: int
    coordinator: int
    hook_blocks: int
    cost: Cost | None


class SnapshotEntry(TypedDict):
    snapshot_id: str
    seq: int
    turno_id: str | None
    agents: list[str]
    hook_blocks: int
    model_calls: int
    usd: str
    previous_attempts: int
    traced: bool


class Segment(TypedDict):
    text: str
    mark: bool


class LogbookText(TypedDict):
    segments: list[Segment]


class DecisionEvent(TypedDict):
    lane: Literal["code"]
    kind: Literal["decision"]
    decision: str
    decision_reason: str | None
    required: int
    agents: list[str]


class ThinkingEvent(TypedDict):
    lane: str
    kind: Literal["thinking"]
    texts: list[str]


class LogbookReadEvent(TypedDict):
    lane: str
    kind: Literal["logbook_read"]
    turn: int
    turno_id: str | None
    is_error: bool
    error: str | None
    logbook: LogbookText | None
    note: str | None


class ProposalEvent(TypedDict):
    lane: str
    kind: Literal["proposal"]
    proposal: JsonValue


class NoProposalsEvent(TypedDict):
    lane: str
    kind: Literal["no_proposals"]


class AgentCostEvent(TypedDict):
    lane: str
    kind: Literal["agent_cost"]
    agent: str
    model_calls: int
    usd: str


class ControlErrorEvent(TypedDict):
    lane: Literal["code"]
    kind: Literal["control_error"]
    messages: list[str]


class ValidationEvent(TypedDict):
    lane: Literal["code"]
    kind: Literal["validation"]
    applied: list[str]
    declined: list[str]


class ApplyCallEvent(TypedDict):
    lane: str
    kind: Literal["tool_call"]
    turn: int
    name: Literal["apply_proposal"]
    proposal: str | None
    is_error: bool
    error: str | None


class AlertCallEvent(TypedDict):
    lane: str
    kind: Literal["tool_call"]
    turn: int
    name: Literal["emit_alert"]
    case_id: str | None
    texto: str | None
    is_error: bool
    error: str | None


class ReportText(TypedDict):
    case_id: str | None
    texto: str | None


class ReportCallEvent(TypedDict):
    lane: str
    kind: Literal["tool_call"]
    turn: int
    name: Literal["emit_shift_report"]
    items: list[ReportText]
    is_error: bool
    error: str | None


class OtherCallEvent(TypedDict):
    lane: str
    kind: Literal["tool_call"]
    turn: int
    name: str
    arguments_json: str
    is_error: bool
    error: str | None


class HookBlockEvent(TypedDict):
    lane: Literal["code"]
    kind: Literal["hook_block"]
    agent: str
    phase: str
    hook: str
    tool: str | None
    turn: int
    reason: str
    reason_es: str | None


class RegistrationEvent(TypedDict):
    lane: Literal["code"]
    kind: Literal["registration"]
    agent: int
    template: int
    report_id: str | None


type Event = (
    DecisionEvent
    | ThinkingEvent
    | LogbookReadEvent
    | ProposalEvent
    | NoProposalsEvent
    | AgentCostEvent
    | ControlErrorEvent
    | ValidationEvent
    | ApplyCallEvent
    | AlertCallEvent
    | ReportCallEvent
    | OtherCallEvent
    | HookBlockEvent
    | RegistrationEvent
)


class Selected(TypedDict):
    snapshot_id: str
    seq: int
    turno_id: str | None
    previous_attempts: int
    model_calls: int
    usd: str
    events: list[Event]


class AgentsPayload(TypedDict):
    at: int
    latest: int
    trace_error: str | None
    heldout: HeldOut
    kpis: AgentsKpis
    snapshots: list[SnapshotEntry]
    selected: Selected | None


class StatePayload(TypedDict):
    at: int
    latest: int
    positions: list[int]
    total: int
    complete: bool
    registry: Literal["ok", "missing"]
    trace_error: str | None
    heldout: HeldOut
    current: Current | None
    days: list[Day]
    kpis: Kpis
    models: list[str]
    markets: list[str]
    cells: list[Cell]
    feed: list[NoticeItem | ReportItem]
