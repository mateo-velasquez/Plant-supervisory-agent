"""The dashboard held-out filter: id patterns, validation and what may be shown (014 R13, I5)."""

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Final

from plant_monitor.cases.registry.run_reader import CaseRow, HistoryAt
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import case_snapshot_id
from plant_monitor.domain.enums import Market, Model
from plant_monitor.domain.notices import Notice, NoticeType, ShiftReport
from plant_monitor.domain.text import escape_controls
from plant_monitor.telemetry.trace import TraceLine

SNAPSHOT_ID: Final = r"S[0-9]{3}"
SHIFT_ID: Final = r"T[0-9]{2}"
CASE_ID: Final = (
    rf"{SNAPSHOT_ID}-(?:{'|'.join(re.escape(m.value) for m in Model)})"
    rf"-(?:{'|'.join(re.escape(m.value) for m in Market)})"
)
NOTICE_ID: Final = (
    rf"{SNAPSHOT_ID}-(?:{re.escape(NoticeType.ALERT.value)}|{re.escape(NoticeType.SHIFT_REPORT.value)})"
    rf"-{CASE_ID}"
)
DECISION_ID: Final = rf"{SNAPSHOT_ID}-(?:{'|'.join(re.escape(t.value) for t in NoticeType)})-{CASE_ID}"
_DECISION_RE: Final = re.compile(DECISION_ID)
_SNAPSHOT_RE: Final = re.compile(SNAPSHOT_ID)
_SHIFT_RE: Final = re.compile(SHIFT_ID)
_CASE_RE: Final = re.compile(CASE_ID)
_NOTICE_RE: Final = re.compile(NOTICE_ID)
_TOKEN_RE: Final = re.compile(rf"\b(?:{SNAPSHOT_ID}|{SHIFT_ID})\b")

type Deliverable = Notice | ShiftReport


class UnsafeId(ValueError):
    """An id outside its allowed pattern; the message names the field and the escaped value."""


@dataclass(frozen=True)
class ShownIds:
    """The snapshot and shift ids an item would show."""

    snapshots: frozenset[str]
    shifts: frozenset[str]


def _check(field: str, value: str, pattern: re.Pattern[str]) -> None:
    """Raise 'UnsafeId' unless 'value' fully matches 'pattern'."""
    if pattern.fullmatch(value) is None:
        raise UnsafeId(f"dashboard: invalid {field}: {escape_controls(value)}")


def _validate_notice(notice: Notice, notice_pattern: re.Pattern[str] = _NOTICE_RE) -> None:
    """The id checks of one notice: snapshot, case, notice id, then each evidence logbook."""
    _check("snapshot_id", notice.snapshot_id, _SNAPSHOT_RE)
    _check("case_id", notice.case_id, _CASE_RE)
    _check("notice_id", notice.notice_id, notice_pattern)
    for item in notice.evidencia:
        _check("bitacora", item.bitacora, _SHIFT_RE)


def validate_ids(item: Deliverable) -> None:
    """Raise 'UnsafeId' for the first id outside its pattern."""
    if isinstance(item, ShiftReport):
        _check("turno_id", item.turno_id, _SHIFT_RE)
        _check("snapshot_id", item.snapshot_id, _SNAPSHOT_RE)
        for news in item.novedades:
            _validate_notice(news)
        for row in item.casos_activos:
            _check("case_id", row.case_id, _CASE_RE)
        return
    if item.tipo is not NoticeType.ALERT:
        raise UnsafeId(f"dashboard: invalid tipo: {escape_controls(item.tipo)}")
    _validate_notice(item)


def notice_ids_valid(notice: Notice) -> bool:
    """Whether the ids of a per-case 'notice' match their patterns."""
    try:
        _validate_notice(notice, _DECISION_RE)
    except UnsafeId:
        return False
    return True


def shown_ids(item: Deliverable) -> ShownIds:
    """The snapshot and shift ids 'item' would show; never raises."""
    if isinstance(item, ShiftReport):
        snapshots = {item.snapshot_id}
        shifts = {item.turno_id}
        for news in item.novedades:
            snapshots |= {news.snapshot_id, case_snapshot_id(news.case_id)}
            shifts |= {e.bitacora for e in news.evidencia}
        snapshots |= {case_snapshot_id(row.case_id) for row in item.casos_activos}
        return ShownIds(frozenset(snapshots), frozenset(shifts))
    return ShownIds(
        frozenset({item.snapshot_id, case_snapshot_id(item.case_id)}),
        frozenset(e.bitacora for e in item.evidencia),
    )


def _is_unverifiable(item: Deliverable) -> bool:
    """Whether 'validate_ids' rejects 'item'."""
    try:
        validate_ids(item)
    except UnsafeId:
        return True
    return False


def select_shown(items: Sequence[Deliverable], policy: HeldOutPolicy) -> tuple[tuple[Deliverable, ...], int]:
    """The items to show, in order, and how many were omitted (held out or unverifiable)."""
    kept: list[Deliverable] = []
    for item in items:
        shown = shown_ids(item)
        refused = bool(shown.snapshots & policy.refused_snapshots) or bool(
            shown.shifts & policy.refused_shifts
        )
        if refused or (not policy.is_open and _is_unverifiable(item)):
            continue
        kept.append(item)
    return tuple(kept), len(items) - len(kept)


def case_shown(row: CaseRow, policy: HeldOutPolicy) -> bool:
    """Whether a case row may be shown: ids well formed and no refused snapshot."""
    if policy.is_open:
        return True
    ids_ok = _CASE_RE.fullmatch(row.case_id) is not None and _SNAPSHOT_RE.fullmatch(row.opened_at) is not None
    return ids_ok and not ({case_snapshot_id(row.case_id), row.opened_at} & policy.refused_snapshots)


def history_shown(row: HistoryAt, policy: HeldOutPolicy) -> bool:
    """Whether a history row may be shown: ids well formed and no refused snapshot."""
    if policy.is_open:
        return True
    case_id, snapshot_id = row.row.case_id, row.row.snapshot_id
    ids_ok = _CASE_RE.fullmatch(case_id) is not None and _SNAPSHOT_RE.fullmatch(snapshot_id) is not None
    return ids_ok and not ({case_snapshot_id(case_id), snapshot_id} & policy.refused_snapshots)


def line_shown(line: TraceLine, policy: HeldOutPolicy) -> bool:
    """Whether a trace line may be shown: open guard, or well-formed ids and no refused token."""
    if policy.is_open:
        return True
    if _SNAPSHOT_RE.fullmatch(line.snapshot_id) is None or _SHIFT_RE.fullmatch(line.turno_id) is None:
        return False
    return json_shown(line.model_dump(mode="json"), policy)


def json_shown(value: object, policy: HeldOutPolicy) -> bool:
    """Whether no string in a decoded JSON value holds a refused snapshot or shift token."""
    if policy.is_open:
        return True
    refused = policy.refused_snapshots | policy.refused_shifts
    return not any(token in refused for text in _strings(value) for token in _TOKEN_RE.findall(text))


def _strings(value: object) -> Iterator[str]:
    """Every string in a decoded JSON value, dictionary keys included."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _strings(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
