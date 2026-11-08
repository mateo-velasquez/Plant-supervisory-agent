"""Verbatim citation check shared by the golden loader and the logbook store (005 E30, 006 R5)."""

import re

_WHITESPACE = re.compile(r"\s+")


def normalize_whitespace(value: str) -> str:
    """'value' with every whitespace run replaced by one space and the ends stripped."""
    return _WHITESPACE.sub(" ", value).strip()


def contains_verbatim(text: str, fragment: str) -> bool:
    """True iff 'fragment' occurs in 'text' with whitespace runs collapsed; case-sensitive (Q-36)."""
    needle = normalize_whitespace(fragment)
    return bool(needle) and needle in normalize_whitespace(text)
