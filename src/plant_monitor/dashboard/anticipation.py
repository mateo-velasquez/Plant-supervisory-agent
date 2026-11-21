"""Anticipación: how stored warnings fared against the crossings that followed (016 R14, I9); pure."""

from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Final, Literal

from plant_monitor.dashboard.payloads import AccuracyBlock, AccuracyCounts, EpisodeView
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import Combination, all_combinations

_SECONDS_PER_HOUR: Final = 3600
_ONE_DECIMAL: Final = Decimal("0.1")
_ANNOUNCING: Final = frozenset({"no_crossing", "warning"})


def hours_number(hours: float) -> int | float:
    """Hours as a JSON number: an integer when whole, else one decimal (I11)."""
    rounded = Decimal(str(hours)).quantize(_ONE_DECIMAL, rounding=ROUND_HALF_EVEN)
    return int(rounded) if rounded == rounded.to_integral_value() else float(rounded)


def format_hours(hours: float) -> str:
    """Hours as text: an integer when whole, else one decimal (I11)."""
    return str(hours_number(hours))


def _hours_between(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / _SECONDS_PER_HOUR


def _episodes(rows: Sequence[ForecastRow]) -> list[list[ForecastRow]]:
    """Maximal runs of consecutive warning rows with one target level."""
    runs: list[list[ForecastRow]] = []
    for row in rows:
        if row.status != "warning":
            continue
        last = runs[-1][-1] if runs else None
        if last is not None and last.seq == row.seq - 1 and last.target_level == row.target_level:
            runs[-1].append(row)
        else:
            runs.append([row])
    return runs


def _crossings(rows: Sequence[ForecastRow]) -> list[tuple[ForecastRow, ForecastRow]]:
    """Pairs (previous, row) where the gap severity rose between consecutive positions."""
    by_seq = {row.seq: row for row in rows}
    return [
        (by_seq[row.seq - 1], row)
        for row in rows
        if row.seq - 1 in by_seq and row.gap_severity > by_seq[row.seq - 1].gap_severity
    ]


def score_episodes(rows: Sequence[ForecastRow], at: int) -> AccuracyBlock:
    """Episodes and unannounced crossings over the rows with seq up to 'at'."""
    shown: dict[Combination, list[ForecastRow]] = defaultdict(list)
    for row in sorted(rows, key=lambda r: r.seq):
        if row.seq <= at:
            shown[row.combination].append(row)
    counts = AccuracyCounts(fulfilled=0, not_fulfilled=0, pending=0, missed=0, no_forecast=0)
    episodes: list[EpisodeView] = []
    leads: list[Decimal] = []
    for combo in all_combinations():
        combo_rows = shown.get(combo, [])
        crossings = _crossings(combo_rows)
        fulfilling: set[int] = set()
        for run in _episodes(combo_rows):
            first, last = run[0], run[-1]
            level = last.target_level
            assert level is not None  # a warning row always has a target
            deadline = last.points[-1].scheduled_at
            fulfils = [
                row
                for _, row in crossings
                if row.gap_severity >= level and first.scheduled_at < row.scheduled_at <= deadline
            ]
            fulfilling.update(row.seq for row in fulfils)
            outcome: Literal["fulfilled", "not_fulfilled", "pending"]
            lead: float | None = None
            if fulfils:
                outcome = "fulfilled"
                lead = _hours_between(first.scheduled_at, fulfils[0].scheduled_at)
                leads.append(Decimal(str(lead)))
            elif any(row.scheduled_at >= deadline for row in combo_rows):
                outcome = "not_fulfilled"
            else:
                outcome = "pending"
            counts[outcome] += 1
            episodes.append(
                EpisodeView(
                    modelo=str(combo.modelo),
                    mercado=str(combo.mercado),
                    level=level.value,
                    first=first.snapshot_id,
                    last=last.snapshot_id,
                    outcome=outcome,
                    crossing=fulfils[0].snapshot_id if fulfils else None,
                    lead_hours=None if lead is None else hours_number(lead),
                )
            )
        for previous, row in crossings:
            if row.seq not in fulfilling:
                counts["missed" if previous.status in _ANNOUNCING else "no_forecast"] += 1
    mean = None
    if leads:
        mean = format((sum(leads, Decimal(0)) / len(leads)).quantize(_ONE_DECIMAL, ROUND_HALF_EVEN), "f")
    return AccuracyBlock(counts=counts, mean_lead_hours=mean, episodes=episodes)
