"""JSON shapes of the dashboard API (014 plan, API); keys keep the data contract's names (ADR-0005)."""

from typing import Literal, TypedDict

from pydantic import JsonValue

from plant_monitor.telemetry.trace import TraceMode


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


class CellForecast(TypedDict):
    """The active early warning of a combination (016 R16)."""

    target_level: str
    label: str


class Cell(TypedDict):
    modelo: str
    mercado: str
    status: Literal["calm", "active", "resolved"]
    case: CaseView | None
    series: list[float | None]
    forecast: CellForecast | None


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


class MetricsOmitted(TypedDict):
    snapshots: int
    notices: int
    trace_lines: int
    evals: int
    run_reports: int


class MetricsHeldOut(TypedDict):
    open: bool
    omitted: MetricsOmitted


class PointUsd(TypedDict):
    investigator: str
    coordinator: str


class PointTokens(TypedDict):
    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int


class CostPoint(TypedDict):
    """One position's cost; every per-snapshot field is 'None' when the snapshot has no trace line (I7)."""

    seq: int
    snapshot_id: str
    usd: PointUsd | None
    cumulative_usd: str
    tokens: PointTokens | None
    cache_pct: str | None
    latency_ms: int | None


class CostTotals(TypedDict):
    usd: str
    model_calls: int
    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int
    cache_pct: str | None
    latency_ms: int


class MetricsCost(TypedDict):
    state: Literal["ok", "thresholds_only", "trace_error"]
    points: list[CostPoint]
    unplaced_usd: str | None
    totals: CostTotals | None


class DayBucket(TypedDict):
    label: str
    alerts: int
    reports: int
    reports_with_news: int
    reports_without_news: int


class Authors(TypedDict):
    agent: int
    template: int
    unknown: int


class RepeatView(TypedDict):
    turno_id: str
    case_id: str
    previous_turno_id: str


class DuplicateAlertView(TypedDict):
    case_id: str
    alerts: int


class NoiseOk(TypedDict):
    state: Literal["ok"]
    errors: int
    repeats: list[RepeatView]
    duplicate_alerts: list[DuplicateAlertView]


class NoiseInvalid(TypedDict):
    state: Literal["invalid"]
    error: str


class SectionView(TypedDict):
    gated: dict[str, int]
    not_gated: dict[str, int]


class SummaryView(TypedDict):
    capabilities: list[str]
    covered_shifts: list[str]
    sections: dict[str, SectionView]
    noise_errors: int
    gating_errors: int
    exit_code: int


class AccuracyView(TypedDict):
    state: Literal["ok", "none", "omitted"]
    file: str | None
    evaluated_at: str | None
    earlier: int
    unreadable: int
    stale: bool | None
    deliverables: int | None
    current_deliverables: int | None
    summary: SummaryView | None


class RunItemView(TypedDict):
    file: str | None
    mode: TraceMode
    status: Literal["ok", "aborted", "interrupted", "running"]
    started_at: str
    duration_seconds: float | None


class RunsView(TypedDict):
    unreadable: int
    items: list[RunItemView]


class MetricsPayload(TypedDict):
    at: int
    latest: int
    positions: list[int]
    registry: Literal["ok", "missing"]
    trace_error: str | None
    heldout: MetricsHeldOut
    cost: MetricsCost
    days: list[DayBucket]
    authors: Authors
    noise: NoiseOk | NoiseInvalid
    accuracy: AccuracyView
    runs: RunsView


class ForecastOmitted(TypedDict):
    snapshots: int
    notices: int
    trace_lines: int
    forecast_rows: int


class ForecastHeldOut(TypedDict):
    open: bool
    omitted: ForecastOmitted


class BasisView(TypedDict):
    rate: str
    plan_per_snapshot: str | None
    window: str
    threshold: str | None


class WarningView(TypedDict):
    modelo: str
    mercado: str
    target_level: str
    label: str
    hours: int | float
    basis: BasisView


class Lines(TypedDict):
    """Threshold lines as gap values (at most 0)."""

    media: float
    alta: float
    critica: float


class HistoryPoint(TypedDict):
    seq: int
    snapshot_id: str
    gap: float
    lines: Lines | None


class ProjectionPoint(TypedDict):
    snapshot_id: str
    time: str
    gap: float
    lines: Lines | None


class CombinationWarning(TypedDict):
    target_level: str
    label: str


class ForecastCombination(TypedDict):
    modelo: str
    mercado: str
    status: str | None
    gap_severity: str | None
    effective_severity: str | None
    target_level: str | None
    history: list[HistoryPoint]
    projection: list[ProjectionPoint]
    warning: CombinationWarning | None


class AccuracyCounts(TypedDict):
    fulfilled: int
    not_fulfilled: int
    pending: int
    missed: int
    no_forecast: int


class EpisodeView(TypedDict):
    modelo: str
    mercado: str
    level: str
    first: str
    last: str
    outcome: Literal["fulfilled", "not_fulfilled", "pending"]
    crossing: str | None
    lead_hours: int | float | None


class AccuracyBlock(TypedDict):
    counts: AccuracyCounts
    mean_lead_hours: str | None
    episodes: list[EpisodeView]


class ForecastPayload(TypedDict):
    at: int
    latest: int
    positions: list[int]
    registry: Literal["ok", "missing"]
    state: Literal["ok", "unavailable"]
    heldout: ForecastHeldOut
    warnings: list[WarningView]
    combinations: list[ForecastCombination]
    accuracy: AccuracyBlock


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
