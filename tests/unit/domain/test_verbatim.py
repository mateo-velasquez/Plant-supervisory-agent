"""006 T1: one verbatim implementation shared with 005 (E10, R5)."""

from plant_monitor.domain import verbatim
from plant_monitor.evaluation import golden


def test_e10_golden_reexports_the_domain_contains_verbatim() -> None:
    """E10: the 005 name and the domain name are the same object."""
    assert golden.contains_verbatim is verbatim.contains_verbatim
