"""Scored facts and their tallies, by gating and by question (005, Q-34, Q-35)."""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class Section(StrEnum):
    """The scored sections of a run."""

    ALERTS = "alerts"
    NEWS = "news"
    CAUSES = "causes"


@dataclass(frozen=True)
class Result:
    """One scored fact; contributions are summed by 'tally'."""

    section: Section
    label: str | None  # None for extra, unscored, missing_report and unscored_report
    case_id: str | None
    where: str  # snapshot_id for alerts and causes, turno_id for news
    contributions: Mapping[str, int]
    depends_on: tuple[str, ...] = ()
    gated: bool = True
    ref: str | None = None  # notice_id of an extra or unscored alert


ALERT_ERRORS: Final = frozenset({"missing", "wrong_snapshot", "duplicates", "extra"})
NEWS_ERRORS: Final = frozenset({"missing", "extra", "missing_report"})
CAUSE_ERRORS: Final = frozenset(
    {
        "target_missing",
        "categoria_mismatch",
        "etapa_mismatch",
        "evidence_missing",
        "evidence_not_loaded",
        "evidence_not_available",
        "evidence_not_verbatim",
    }
)


def tally(
    results: Iterable[Result], *, gated: bool | None = None, question: str | None = None
) -> dict[str, int]:
    """Summed contributions of the results matching 'gated' and 'question'; None matches everything."""
    counts: Counter[str] = Counter()
    for result in results:
        if gated is not None and result.gated != gated:
            continue
        if question is not None and question not in result.depends_on:
            continue
        counts.update(result.contributions)
    return dict(counts)


def errors(counts: Mapping[str, int], keys: frozenset[str]) -> int:
    """Sum of the counts under 'keys'; the other keys are attribute or scope buckets."""
    return sum(value for key, value in counts.items() if key in keys)
