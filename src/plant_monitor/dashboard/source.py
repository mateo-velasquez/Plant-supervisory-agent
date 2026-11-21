"""What the dashboard reads, filtered by the held-out guard (014 R2, R3, R12, R13)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal

from plant_monitor.cases.registry.notices import is_deliverable
from plant_monitor.cases.registry.run_reader import NoticeAt, ProcessedRow, RunRows, read_run_rows
from plant_monitor.config import Settings
from plant_monitor.dashboard.heldout import (
    SNAPSHOT_ID,
    case_shown,
    history_shown,
    line_shown,
    notice_ids_valid,
    select_shown,
    shown_ids,
)
from plant_monitor.dashboard.payloads import Cost, HeldOut, OmittedCounts
from plant_monitor.domain.calendar import HeldOutPolicy, calendar_order
from plant_monitor.domain.models import Combination, Shift, all_combinations
from plant_monitor.domain.notices import Notice
from plant_monitor.ingestion.plant import load_plan, load_shifts
from plant_monitor.telemetry.trace import (
    TRACE_GLOB,
    USD_DECIMALS,
    CorruptTraces,
    TextBy,
    TraceFile,
    TraceLine,
    TraceMode,
    index_attempts,
    read_trace_files,
    run_totals,
    text_by,
)

SHIFTS_FILE: Final = "turnos.csv"
_PLAN_FILE: Final = "plan_produccion.csv"
_SNAPSHOT_RE: Final = re.compile(SNAPSHOT_ID)
_UNREADABLE_RE: Final = re.compile(r"^(?P<file>.+) is not a readable trace file \(\w+\)$")
type Attempt = tuple[str, TraceLine]


@dataclass(frozen=True)
class Calendar:
    """The shifts the dashboard may show and the plan's combinations, read once at startup."""

    shifts: tuple[Shift, ...]
    combinations: tuple[Combination, ...]

    @classmethod
    def load(cls, plant_dir: Path, policy: HeldOutPolicy, shifts: list[Shift] | None = None) -> Calendar:
        """Shifts in calendar order without the refused ones; plan combinations in canonical order."""
        shifts = load_shifts(plant_dir / SHIFTS_FILE) if shifts is None else shifts
        plan = load_plan(plant_dir / _PLAN_FILE, shifts)
        planned = {(row.modelo, row.mercado) for row in plan}
        kept = tuple(s for s in calendar_order(shifts) if s.turno_id not in policy.refused_shifts)
        combos = tuple(c for c in all_combinations() if (c.modelo, c.mercado) in planned)
        return cls(shifts=kept, combinations=combos)


def load_calendar(settings: Settings) -> tuple[Calendar, HeldOutPolicy, list[Shift]]:
    """Read 'turnos.csv' once: the calendar, the held-out policy and every shift."""
    shifts = load_shifts(settings.plant_dir / SHIFTS_FILE)
    policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
    return Calendar.load(settings.plant_dir, policy, shifts), policy, shifts


@dataclass(frozen=True)
class Omitted:
    """How many items the held-out guard hid (R13)."""

    snapshots: int
    notices: int
    trace_lines: int


@dataclass(frozen=True)
class RunView:
    """One consistent read of the run: filtered rows, trace lines by attempt and the trace error."""

    registry: Literal["ok", "missing"]
    rows: RunRows
    deliverables: tuple[NoticeAt, ...]
    lines: tuple[Attempt, ...]
    committed: Mapping[str, TraceLine]
    aborted: Mapping[str, tuple[Attempt, ...]]
    trace_error: str | None
    mode: TraceMode
    omitted: Omitted
    policy_open: bool

    def positions(self) -> tuple[int, ...]:
        """The shown 'seq' values in ascending order."""
        return tuple(sorted(row.seq for row in self.rows.processed))

    def resolve_at(self, at: int | None) -> int:
        """'None' gives the latest position; a number gives the greatest position at or below it, or 0."""
        positions = self.positions()
        if at is None:
            return positions[-1] if positions else 0
        return max((p for p in positions if p <= at), default=0)


def load_view(registry_path: Path, traces_dir: Path, policy: HeldOutPolicy) -> RunView:
    """Read the registry and the traces once; 'RegistryBusy' and registry 'ValueError' pass through."""
    raw = read_run_rows(registry_path)
    rows, deliverables, omitted_snapshots, omitted_notices = _filter_rows(raw, policy)
    files, trace_error = _read_traces(traces_dir)
    shown = tuple(
        TraceFile(name=f.name, lines=tuple(ln for ln in f.lines if line_shown(ln, policy))) for f in files
    )
    omitted_lines = sum(len(f.lines) for f in files) - sum(len(f.lines) for f in shown)
    committed: dict[str, TraceLine] = {}
    aborted: dict[str, tuple[Attempt, ...]] = {}
    if trace_error is None:
        try:
            first, aborted = index_attempts(shown)
            committed = {sid: line for sid, (_, line) in first.items()}
        except CorruptTraces as error:
            trace_error = f"traces: {error}"
    lines = () if trace_error else tuple((f.name, ln) for f in shown for ln in f.lines)
    if trace_error:
        omitted_lines = 0
    has_files = any(traces_dir.glob(TRACE_GLOB)) if traces_dir.is_dir() else False
    return RunView(
        registry="missing" if raw is None else "ok",
        rows=rows,
        deliverables=deliverables,
        lines=lines,
        committed=committed,
        aborted=aborted,
        trace_error=trace_error,
        mode="agent" if has_files else "thresholds_only",
        omitted=Omitted(snapshots=omitted_snapshots, notices=omitted_notices, trace_lines=omitted_lines),
        policy_open=policy.is_open,
    )


def _read_traces(traces_dir: Path) -> tuple[tuple[TraceFile, ...], str | None]:
    """The trace files, or no files and the one-line error (no stored values, I7)."""
    try:
        return read_trace_files(traces_dir, drop_partial_tail=True), None
    except ValueError as error:
        match = _UNREADABLE_RE.match(str(error))
        name = match["file"] if match else "trace files"
        return (), f"traces: {name} is not a readable trace file"


def _filter_rows(
    raw: RunRows | None, policy: HeldOutPolicy
) -> tuple[RunRows, tuple[NoticeAt, ...], int, int]:
    """The rows the guard lets through, the deliverables among them and the omitted counts."""
    if raw is None:
        return RunRows(processed=(), cases=(), history=(), notices=()), (), 0, 0
    processed = tuple(r for r in raw.processed if _processed_shown(r, policy))
    notices: list[NoticeAt] = []
    deliverables: list[NoticeAt] = []
    omitted_notices = 0
    for entry in raw.notices:
        if is_deliverable(entry.item):
            if select_shown((entry.item,), policy)[0]:
                notices.append(entry)
                deliverables.append(entry)
            else:
                omitted_notices += 1
        elif _decision_shown(entry.item, policy):
            notices.append(entry)
    rows = RunRows(
        processed=processed,
        cases=tuple(c for c in raw.cases if case_shown(c, policy)),
        history=tuple(h for h in raw.history if history_shown(h, policy)),
        notices=tuple(notices),
    )
    return rows, tuple(deliverables), len(raw.processed) - len(processed), omitted_notices


def _processed_shown(row: ProcessedRow, policy: HeldOutPolicy) -> bool:
    """Whether a processed snapshot is not refused and has a well-formed id."""
    return policy.is_open or (
        _SNAPSHOT_RE.fullmatch(row.snapshot_id) is not None
        and row.snapshot_id not in policy.refused_snapshots
    )


def _decision_shown(item: object, policy: HeldOutPolicy) -> bool:
    """Whether a per-case decision notice has valid ids and shows no refused snapshot or shift."""
    if policy.is_open:
        return True
    if not isinstance(item, Notice) or not notice_ids_valid(item):
        return False
    ids = shown_ids(item)
    return not (ids.snapshots & policy.refused_snapshots or ids.shifts & policy.refused_shifts)


def format_usd(value: Decimal) -> str:
    """A USD amount with the trace's fixed decimals."""
    return format(value.quantize(USD_DECIMALS), "f")


def heldout_of(view: RunView) -> HeldOut:
    """The held-out block of a payload: guard state and omitted counts."""
    return HeldOut(
        open=view.policy_open,
        omitted=OmittedCounts(
            snapshots=view.omitted.snapshots,
            notices=view.omitted.notices,
            trace_lines=view.omitted.trace_lines,
        ),
    )


def cost_as_of(view: RunView, at: int) -> Cost | None:
    """'run_totals' over the lines as of 'at'; at 'latest' also lines of snapshots that never committed."""
    if view.trace_error:
        return None
    totals = run_totals(lines_as_of(view, at))
    return Cost(
        usd=format_usd(totals.usd),
        model_calls=totals.model_calls,
        tokens=totals.input_tokens + totals.output_tokens,
    )


def lines_as_of(view: RunView, at: int) -> list[TraceLine]:
    """Every line at 'latest'; else the lines of shown positions up to 'at'."""
    seq_of = {row.snapshot_id: row.seq for row in view.rows.processed}
    latest = view.resolve_at(None)
    return [
        line
        for _, line in view.lines
        if at == latest or (line.snapshot_id in seq_of and seq_of[line.snapshot_id] <= at)
    ]


def day_label(shift: Shift) -> str:
    """'fecha' as stored, or the 'M/D/YYYY' date of 'inicio' when it is empty."""
    return shift.fecha or f"{shift.inicio.month}/{shift.inicio.day}/{shift.inicio.year}"


def deliverables_as_of(view: RunView, at: int) -> tuple[NoticeAt, ...]:
    """The deliverables with 'seq' up to 'at', in order."""
    return tuple(entry for entry in view.deliverables if entry.seq <= at)


def author_of(view: RunView, notice: Notice) -> TextBy:
    """Who wrote the text of 'notice', from its snapshot's committed trace line."""
    return text_by(notice.notice_id, view.committed.get(notice.snapshot_id), view.mode)


@dataclass(frozen=True)
class DayLookup:
    """Day labels in calendar order and the label of each snapshot and shift."""

    labels: tuple[str, ...]
    by_snapshot: Mapping[str, str]
    by_shift: Mapping[str, str]


def day_lookup(calendar: Calendar) -> DayLookup:
    """The day label of every shown shift and of its two snapshots."""
    by_snapshot: dict[str, str] = {}
    by_shift: dict[str, str] = {}
    for shift in calendar.shifts:
        label = day_label(shift)
        by_shift[shift.turno_id] = label
        by_snapshot[shift.snapshot_medio] = label
        by_snapshot[shift.snapshot_cierre] = label
    labels = tuple(dict.fromkeys(by_shift.values()))
    return DayLookup(labels=labels, by_snapshot=by_snapshot, by_shift=by_shift)
