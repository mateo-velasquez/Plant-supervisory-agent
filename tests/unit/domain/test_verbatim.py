"""006 T1: one verbatim implementation shared with 005 (E10, R5)."""

import pytest

from plant_monitor.domain import verbatim
from plant_monitor.evaluation import golden

_TEXT = "Turno T05.\nse paró la línea\nde montaje.\nFin."


def test_e10_golden_reexports_the_domain_contains_verbatim() -> None:
    """E10: the 005 name and the domain name are the same object."""
    assert golden.contains_verbatim is verbatim.contains_verbatim


@pytest.mark.parametrize(
    ("text", "fragment", "expected"),
    [
        (_TEXT, "se paró la línea de montaje", ((11, 38),)),
        (_TEXT, "montaje.", ((31, 39),)),
        (_TEXT, "no está", ()),
        (_TEXT, "SE PARÓ", ()),
        (_TEXT, "   ", ()),
        ("falla y falla", "falla", ((0, 5), (8, 13))),
    ],
)
def test_e10_verbatim_spans_whitespace_tolerant_case_sensitive(
    text: str, fragment: str, expected: tuple[tuple[int, int], ...]
) -> None:
    """014 E10 (Q-36): spans of whitespace-tolerant, case-sensitive matches; blank or absent give ()."""
    assert verbatim.verbatim_spans(text, fragment) == expected
    assert bool(expected) == verbatim.contains_verbatim(text, fragment)
