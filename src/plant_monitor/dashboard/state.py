"""The Planta state as of one position, built from a 'RunView' (014 R3-R7, R13); computes no metrics."""

from collections import Counter
from collections.abc import Mapping
from typing import Literal

from pydantic import JsonValue

from plant_monitor.cases.registry.run_reader import CaseRow, HistoryAt, NoticeAt
from plant_monitor.dashboard.payloads import (
    CaseView,
    CauseView,
    Cell,
    Current,
    Day,
    EvidenceView,
    Kpis,
    NoticeItem,
    ReportItem,
    ShiftCell,
    SnapshotCell,
    StatePayload,
)
from plant_monitor.dashboard.source import (
    Calendar,
    RunView,
    author_of,
    cost_as_of,
    day_label,
    day_lookup,
    deliverables_as_of,
    heldout_of,
)
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.models import Combination
from plant_monitor.domain.notices import Notice, ShiftReport, report_id_for


def build_state(view: RunView, calendar: Calendar, at: int) -> StatePayload:
    """The state payload at position 'at' (already resolved by 'RunView.resolve_at')."""
    seq_of = {row.snapshot_id: row.seq for row in view.rows.processed}
    cells = _cells(view, calendar, at, seq_of)
    latest = view.resolve_at(None)
    total = 2 * len(calendar.shifts)
    return StatePayload(
        at=at,
        latest=latest,
        positions=list(view.positions()),
        total=total,
        complete=at == total,
        registry=view.registry,
        trace_error=view.trace_error,
        heldout=heldout_of(view),
        current=_current(calendar, at, seq_of),
        days=_days(view, calendar, at, seq_of),
        kpis=_kpis(view, calendar, at, cells),
        models=list(dict.fromkeys(str(c.modelo) for c in calendar.combinations)),
        markets=list(dict.fromkeys(str(c.mercado) for c in calendar.combinations)),
        cells=cells,
        feed=_feed(view, at),
    )


def _hhmm(value: object) -> str:
    return value.strftime("%H:%M") if hasattr(value, "strftime") else ""


def _current(calendar: Calendar, at: int, seq_of: Mapping[str, int]) -> Current | None:
    """The snapshot at 'at' with its shift, or 'None' at position 0."""
    snapshot_id = next((sid for sid, seq in seq_of.items() if seq == at), None)
    if at == 0 or snapshot_id is None:
        return None
    shift = next(
        (s for s in calendar.shifts if snapshot_id in (s.snapshot_medio, s.snapshot_cierre)),
        None,
    )
    if shift is None:
        return Current(
            snapshot_id=snapshot_id, seq=at, turno_id=None, turno=None, inicio=None, fin=None, fecha=None
        )
    return Current(
        snapshot_id=snapshot_id,
        seq=at,
        turno_id=shift.turno_id,
        turno=shift.turno,
        inicio=_hhmm(shift.inicio),
        fin=_hhmm(shift.fin),
        fecha=day_label(shift),
    )


def _days(view: RunView, calendar: Calendar, at: int, seq_of: Mapping[str, int]) -> list[Day]:
    """Shifts grouped by day label in calendar order, each with its two snapshot cells."""
    alerts: Counter[str] = Counter()
    reports: set[str] = set()
    for entry in deliverables_as_of(view, at):
        if isinstance(entry.item, ShiftReport):
            reports.add(entry.item.snapshot_id)
        else:
            alerts[entry.item.snapshot_id] += 1

    def snapshot_cell(snapshot_id: str) -> SnapshotCell:
        seq = seq_of.get(snapshot_id)
        shown = seq is not None and seq <= at
        return SnapshotCell(
            snapshot_id=snapshot_id,
            seq=seq if shown else None,
            processed=shown,
            alerts=alerts[snapshot_id],
            report=snapshot_id in reports,
        )

    lookup = day_lookup(calendar)
    days: dict[str, list[ShiftCell]] = {label: [] for label in lookup.labels}
    for shift in calendar.shifts:
        days[lookup.by_shift[shift.turno_id]].append(
            ShiftCell(
                turno_id=shift.turno_id,
                turno=shift.turno,
                inicio=_hhmm(shift.inicio),
                fin=_hhmm(shift.fin),
                snapshots=[snapshot_cell(shift.snapshot_medio), snapshot_cell(shift.snapshot_cierre)],
            )
        )
    return [Day(label=label, shifts=shifts) for label, shifts in days.items()]


def _cells(view: RunView, calendar: Calendar, at: int, seq_of: Mapping[str, int]) -> list[Cell]:
    """One cell per combination: its case as of 'at' (R6 tie-break), cause as of 'at' and sparkline."""
    newest: dict[str, HistoryAt] = {}
    gaps: dict[Combination, dict[int, float]] = {}
    combination_of = {case.case_id: case.combination for case in view.rows.cases}
    for entry in view.rows.history:
        if entry.seq > at or entry.row.case_id not in combination_of:
            continue
        newest[entry.row.case_id] = entry
        gaps.setdefault(combination_of[entry.row.case_id], {})[entry.seq] = entry.row.gap_units
    causes: dict[str, CauseView] = {}
    for notice_at in view.rows.notices:
        item = notice_at.item
        if notice_at.seq <= at and isinstance(item, Notice):
            causes[item.case_id] = CauseView(
                categoria=item.causa.categoria.value,
                etapa=None if item.causa.etapa is None else item.causa.etapa.value,
            )
    positions = [p for p in view.positions() if p <= at]
    cells: list[Cell] = []
    for combo in calendar.combinations:
        candidates = [c for c in view.rows.cases if c.combination == combo and c.case_id in newest]
        chosen = _pick(candidates, newest, seq_of)
        series: list[float | None] = [gaps.get(combo, {}).get(p) for p in positions]
        if chosen is None:
            cells.append(_cell(combo, "calm", None, series))
            continue
        case_row, history = chosen
        row = history.row
        resolved = row.state is CaseState.RESOLVED
        bottleneck = None if row.bottleneck is None else row.bottleneck.value
        undeclared = CauseView(categoria=CauseCategory.UNDECLARED.value, etapa=bottleneck)
        cause = causes.get(case_row.case_id, undeclared)
        case = CaseView(
            case_id=case_row.case_id,
            estado=row.state.value,
            severidad=row.effective_severity.value,
            gap_unidades=row.gap_units,
            gap_pct=row.gap_pct,
            retraso_dias=row.delay_days,
            etapa_cuello=bottleneck,
            causa=cause["categoria"],
            etapa=cause["etapa"],
            opened_at=case_row.opened_at,
            resolved_at=row.snapshot_id if resolved else None,
        )
        cells.append(_cell(combo, "resolved" if resolved else "active", case, series))
    return cells


def _pick(
    candidates: list[CaseRow], newest: Mapping[str, HistoryAt], seq_of: Mapping[str, int]
) -> tuple[CaseRow, HistoryAt] | None:
    """The case with the newest history row; a tie goes to the later 'opened_at', with one active at most."""
    if not candidates:
        return None
    top = max(newest[c.case_id].seq for c in candidates)
    tied = [c for c in candidates if newest[c.case_id].seq == top]
    if sum(newest[c.case_id].row.state.is_active for c in tied) > 1:
        raise ValueError("dashboard: two active cases for one combination")
    positions = [seq_of.get(c.opened_at, 0) for c in tied]
    if len(tied) > 1 and positions.count(max(positions)) > 1:
        raise ValueError("dashboard: two cases for one combination share their opened_at")
    best = tied[positions.index(max(positions))]
    return best, newest[best.case_id]


def _cell(
    combo: Combination,
    status: Literal["calm", "active", "resolved"],
    case: CaseView | None,
    series: list[float | None],
) -> Cell:
    return Cell(
        modelo=str(combo.modelo),
        mercado=str(combo.mercado),
        status=status,
        case=case,
        series=series,
    )


def _kpis(
    view: RunView,
    calendar: Calendar,
    at: int,
    cells: list[Cell],
) -> Kpis:
    """Counts as of 'at': active and critical cases, alerts, reports and the model cost."""
    active = [c for c in cells if c["status"] == "active" and c["case"] is not None]
    critical = [
        c for c in active if c["case"] is not None and c["case"]["severidad"] == Severity.CRITICAL.value
    ]
    shown = deliverables_as_of(view, at)
    reports = sum(isinstance(e.item, ShiftReport) for e in shown)
    return Kpis(
        active=len(active),
        combinations=len(calendar.combinations),
        critical=len(critical),
        critical_combinations=[f"{c['modelo']} × {c['mercado']}" for c in critical],  # noqa: RUF001
        alerts=len(shown) - reports,
        reports=reports,
        shifts=len(calendar.shifts),
        cost=cost_as_of(view, at),
    )


def _notice_item(view: RunView, entry: NoticeAt, notice: Notice, kind: str) -> NoticeItem:
    author = author_of(view, notice)
    return NoticeItem(
        kind="alert" if kind == "alert" else "news",
        seq=entry.seq,
        notice_id=notice.notice_id,
        snapshot_id=notice.snapshot_id,
        case_id=notice.case_id,
        modelo=str(notice.modelo),
        mercado=str(notice.mercado),
        severidad=notice.severidad.value,
        severidad_maxima=notice.severidad_maxima.value,
        estado=notice.estado.value,
        motivo=[reason.value for reason in notice.motivo],
        origen=notice.origen.value,
        causa=CauseView(
            categoria=notice.causa.categoria.value,
            etapa=None if notice.causa.etapa is None else notice.causa.etapa.value,
        ),
        evidencia=[EvidenceView(bitacora=e.bitacora, fragmento=e.fragmento) for e in notice.evidencia],
        texto=notice.texto,
        author=author,
    )


def _feed(view: RunView, at: int) -> list[NoticeItem | ReportItem]:
    """Deliverables as of 'at', newest first."""
    feed: list[NoticeItem | ReportItem] = []
    for entry in reversed(deliverables_as_of(view, at)):
        item = entry.item
        if isinstance(item, ShiftReport):
            active_rows: list[JsonValue] = [row.model_dump(mode="json") for row in item.casos_activos]
            feed.append(
                ReportItem(
                    kind="report",
                    seq=entry.seq,
                    report_id=report_id_for(item.turno_id),
                    turno_id=item.turno_id,
                    snapshot_id=item.snapshot_id,
                    novedades=[_notice_item(view, entry, news, "news") for news in item.novedades],
                    casos_activos=active_rows,
                )
            )
        else:
            feed.append(_notice_item(view, entry, item, "alert"))
    return feed
