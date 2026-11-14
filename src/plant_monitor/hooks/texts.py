"""Text helpers for the hooks: folding and the severity and cause patterns (R5, R7)."""

import re
import unicodedata
from typing import Final

from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity

_LEVELS: Final = "|".join(severity.value for severity in Severity)
_STATED: Final = re.compile(rf"\bseveridad\s*:?\s+(?:(maxima)\s*:?\s+)?(?:de\s+)?({_LEVELS})\b")
_CHANGE: Final = re.compile(rf"\s*(?:→|->)|\s+a\s+(?:{_LEVELS})\b")
_CATEGORY_PATTERNS: Final = tuple(
    (category, re.compile(rf"\b{'[_\\s]+'.join(map(re.escape, category.value.split('_')))}\b"))
    for category in CauseCategory
    if category is not CauseCategory.UNDECLARED
)


def fold(text: str) -> str:
    """NFKD, combining marks dropped, casefolded."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def stated_severities(folded: str) -> tuple[tuple[bool, Severity], ...]:
    """(is_maxima, level) per severity statement in text order; a change phrase's earlier level is skipped."""
    return tuple(
        (match.group(1) is not None, Severity(match.group(2)))
        for match in _STATED.finditer(folded)
        if _CHANGE.match(folded, match.end()) is None
    )


def named_categories(folded: str) -> tuple[CauseCategory, ...]:
    """Declared cause categories named in the text, in text order."""
    found = [
        (match.start(), category)
        for category, pattern in _CATEGORY_PATTERNS
        for match in pattern.finditer(folded)
    ]
    return tuple(category for _, category in sorted(found, key=lambda pair: pair[0]))
