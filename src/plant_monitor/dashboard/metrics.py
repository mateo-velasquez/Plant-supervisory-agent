"""The metrics payload as of one position, from a 'RunView' and the fixed panels (015 R1, R3-R9, R11-R13)."""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Final

from plant_monitor.dashboard.panels import AccuracyPanel, RunsPanel
from plant_monitor.dashboard.payloads import (
    AccuracyView,
    Authors,
    CostPoint,
    CostTotals,
    DayBucket,
    DuplicateAlertView,
    MetricsCost,
    MetricsHeldOut,
    MetricsOmitted,
    MetricsPayload,
    NoiseInvalid,
    NoiseOk,
    PointTokens,
    PointUsd,
    RepeatView,
    RunItemView,
    RunsView,
    SectionView,
    SummaryView,
)
from plant_monitor.dashboard.source import (
    Calendar,
    RunView,
    author_of,
    day_lookup,
    deliverables_as_of,
    format_usd,
    lines_as_of,
)
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.evaluation.noise import count_noise
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.telemetry.trace import RunTotals, TraceLine, run_totals

_PERCENT: Final = 100
_CACHE_PCT_STEP: Final = Decimal("0.1")


def build_metrics(
    view: RunView, calendar: Calendar, at: int, accuracy: AccuracyPanel, runs: RunsPanel
) -> MetricsPayload:
    """The metrics payload at position 'at' (already resolved by 'RunView.resolve_at')."""
    return MetricsPayload(
        at=at,
        latest=view.resolve_at(None),
        positions=list(view.positions()),
        registry=view.registry,
        trace_error=view.trace_error,
        heldout=_heldout(view, accuracy, runs),
        cost=_cost(view, at),
        days=_days(view, calendar, at),
        authors=_authors(view, at),
        noise=_noise(view, at),
        accuracy=_accuracy(view, accuracy),
        runs=_runs(runs),
    )


def _cache_pct(totals: RunTotals) -> str | None:
    """Cache-read share of all prompt tokens with one decimal, or 'None' when there are none (R4)."""
    denominator = (
        totals.input_tokens
        + totals.cache_read_tokens
        + totals.cache_write_5m_tokens
        + totals.cache_write_1h_tokens
    )
    if denominator == 0:
        return None
    share = Decimal(_PERCENT * totals.cache_read_tokens) / Decimal(denominator)
    return format(share.quantize(_CACHE_PCT_STEP), "f")


def _latency(lines: Sequence[TraceLine]) -> int:
    """Milliseconds over every model call of 'lines', both agents, aborted attempts included (R5)."""
    return sum(
        call.latency_ms
        for line in lines
        for call in (*line.model_calls, *(line.investigator.model_calls if line.investigator else ()))
    )


def _point(seq: int, snapshot_id: str, lines: Sequence[TraceLine], cumulative: Decimal) -> CostPoint:
    """One position's point; with no line every per-snapshot value is 'None' (I7)."""
    if not lines:
        return CostPoint(
            seq=seq,
            snapshot_id=snapshot_id,
            usd=None,
            cumulative_usd=format_usd(cumulative),
            tokens=None,
            cache_pct=None,
            latency_ms=None,
        )
    totals = run_totals(lines)
    return CostPoint(
        seq=seq,
        snapshot_id=snapshot_id,
        usd=PointUsd(
            investigator=format_usd(totals.by_agent["investigator"].usd),
            coordinator=format_usd(totals.by_agent["coordinator"].usd),
        ),
        cumulative_usd=format_usd(cumulative),
        tokens=PointTokens(
            input=totals.input_tokens,
            output=totals.output_tokens,
            cache_read=totals.cache_read_tokens,
            cache_write_5m=totals.cache_write_5m_tokens,
            cache_write_1h=totals.cache_write_1h_tokens,
        ),
        cache_pct=_cache_pct(totals),
        latency_ms=_latency(lines),
    )


def _cost(view: RunView, at: int) -> MetricsCost:
    """Per-snapshot points with a running sum of line totals; the rest is 'unplaced_usd' (R3-R6)."""
    if view.trace_error:
        return MetricsCost(state="trace_error", points=[], unplaced_usd=None, totals=None)
    if view.mode == "thresholds_only":
        return MetricsCost(state="thresholds_only", points=[], unplaced_usd=None, totals=None)
    lines = lines_as_of(view, at)
    by_snapshot: dict[str, list[TraceLine]] = defaultdict(list)
    for line in lines:
        by_snapshot[line.snapshot_id].append(line)
    points: list[CostPoint] = []
    placed = Decimal(0)
    for row in sorted(view.rows.processed, key=lambda r: r.seq):
        if row.seq > at:
            continue
        own = by_snapshot.get(row.snapshot_id, [])
        placed += run_totals(own).usd
        points.append(_point(row.seq, row.snapshot_id, own, placed))
    totals = run_totals(lines)
    return MetricsCost(
        state="ok",
        points=points,
        unplaced_usd=format_usd(totals.usd - placed),
        totals=CostTotals(
            usd=format_usd(totals.usd),
            model_calls=totals.model_calls,
            input=totals.input_tokens,
            output=totals.output_tokens,
            cache_read=totals.cache_read_tokens,
            cache_write_5m=totals.cache_write_5m_tokens,
            cache_write_1h=totals.cache_write_1h_tokens,
            cache_pct=_cache_pct(totals),
            latency_ms=_latency(lines),
        ),
    )


def _days(view: RunView, calendar: Calendar, at: int) -> list[DayBucket]:
    """One bucket per calendar day with its alerts and reports as of 'at' (R7)."""
    lookup = day_lookup(calendar)
    buckets = {
        label: DayBucket(label=label, alerts=0, reports=0, reports_with_news=0, reports_without_news=0)
        for label in lookup.labels
    }
    for entry in deliverables_as_of(view, at):
        item = entry.item
        if isinstance(item, ShiftReport):
            report_day = lookup.by_shift.get(item.turno_id)
            if report_day is None:
                continue
            buckets[report_day]["reports"] += 1
            if item.novedades:
                buckets[report_day]["reports_with_news"] += 1
            else:
                buckets[report_day]["reports_without_news"] += 1
        else:
            alert_day = lookup.by_snapshot.get(item.snapshot_id)
            if alert_day is not None:
                buckets[alert_day]["alerts"] += 1
    return list(buckets.values())


def _authors(view: RunView, at: int) -> Authors:
    """Who wrote every alert and news item as of 'at' (R8)."""
    counts: Counter[str] = Counter()
    for entry in deliverables_as_of(view, at):
        item = entry.item
        notices = item.novedades if isinstance(item, ShiftReport) else (item,)
        counts.update(author_of(view, notice) for notice in notices)
    return Authors(agent=counts["agent"], template=counts["template"], unknown=counts["unknown"])


def _noise(view: RunView, at: int) -> NoiseOk | NoiseInvalid:
    """Live noise over the deliverables as of 'at'; an invalid run output degrades only this panel (R9)."""
    shown = [entry.item for entry in deliverables_as_of(view, at)]
    alerts = tuple(item for item in shown if isinstance(item, Notice))
    reports = tuple(item for item in shown if isinstance(item, ShiftReport))
    try:
        score = count_noise(RunOutput(alerts=alerts, reports=reports))
    except ValueError as error:
        return NoiseInvalid(state="invalid", error=type(error).__name__)
    return NoiseOk(
        state="ok",
        errors=score.errors,
        repeats=[
            RepeatView(turno_id=r.turno_id, case_id=r.case_id, previous_turno_id=r.previous_turno_id)
            for r in score.repeats
        ],
        duplicate_alerts=[
            DuplicateAlertView(case_id=case, alerts=count) for case, count in score.duplicate_alerts
        ],
    )


def _section(gated: Mapping[str, int], not_gated: Mapping[str, int]) -> SectionView:
    return SectionView(gated=dict(gated), not_gated=dict(not_gated))


def _accuracy(view: RunView, panel: AccuracyPanel) -> AccuracyView:
    """The stored evaluation as the page reads it, with staleness against the unfiltered count (R11)."""
    stored = panel.summary
    summary: SummaryView | None = None
    stale: bool | None = None
    current: int | None = None
    if stored is not None:
        summary = SummaryView(
            capabilities=list(stored.capabilities),
            covered_shifts=list(stored.covered_shifts),
            sections={
                "alerts": _section(stored.alerts.gated, stored.alerts.not_gated),
                "news": _section(stored.news.gated, stored.news.not_gated),
                "causes": _section(stored.causes.gated, stored.causes.not_gated),
            },
            noise_errors=stored.noise.errors,
            gating_errors=stored.gating_errors,
            exit_code=stored.exit_code,
        )
        current = len(view.deliverables) + view.omitted.notices
        stale = None if stored.deliverables is None else stored.deliverables != current
    return AccuracyView(
        state=panel.state,
        file=panel.file,
        evaluated_at=panel.evaluated_at,
        earlier=panel.earlier,
        unreadable=panel.unreadable,
        stale=stale,
        deliverables=None if stored is None else stored.deliverables,
        current_deliverables=current,
        summary=summary,
    )


def _runs(panel: RunsPanel) -> RunsView:
    return RunsView(
        unreadable=panel.unreadable,
        items=[
            RunItemView(
                file=item.file,
                mode=item.mode,
                status=item.status,
                started_at=item.started_at,
                duration_seconds=item.duration_seconds,
            )
            for item in panel.items
        ],
    )


def _heldout(view: RunView, accuracy: AccuracyPanel, runs: RunsPanel) -> MetricsHeldOut:
    """Guard state and every omitted count, the eval and run-report ones from the fixed panels (R12)."""
    return MetricsHeldOut(
        open=view.policy_open,
        omitted=MetricsOmitted(
            snapshots=view.omitted.snapshots,
            notices=view.omitted.notices,
            trace_lines=view.omitted.trace_lines,
            evals=int(accuracy.state == "omitted"),
            run_reports=runs.omitted,
        ),
    )
