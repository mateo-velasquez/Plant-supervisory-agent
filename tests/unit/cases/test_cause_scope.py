"""008 T3: which cases a raise reaches (E4)."""

import pytest

from plant_monitor.cases.causes import Candidate, link_targets, matches
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import ActiveCause, CauseCategory, CauseScope, CitedCause, Evidence
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination

from builders import case_with

PICKUP_ANY = CauseScope(modelo=Model.PICKUP, etapa=Stage.ASSEMBLY, mercado=None)
SUV_EUROPE = CauseScope(modelo=Model.SUV, etapa=Stage.QUALITY, mercado=Market.EUROPE)
PL = Combination(modelo=Model.PICKUP, mercado=Market.LOCAL)
PB = Combination(modelo=Model.PICKUP, mercado=Market.BRAZIL)
SEL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SE = Combination(modelo=Model.SUV, mercado=Market.EUROPE)
SB = Combination(modelo=Model.SUV, mercado=Market.BRAZIL)
EVIDENCE = Evidence(bitacora="T05", fragmento="se paró la línea de montaje de Pickup")


@pytest.mark.parametrize(
    ("scope", "combination", "stage", "expected"),
    [
        (PICKUP_ANY, PL, Stage.ASSEMBLY, True),
        (PICKUP_ANY, PB, None, True),
        (PICKUP_ANY, PL, Stage.PAINT, False),
        (PICKUP_ANY, SEL, Stage.ASSEMBLY, False),
        (SUV_EUROPE, SE, Stage.QUALITY, True),
        (SUV_EUROPE, SE, None, True),
        (SUV_EUROPE, SB, None, False),
        (SUV_EUROPE, SE, Stage.PAINT, False),
    ],
    ids=[
        "same",
        "null_stage",
        "other_stage",
        "other_model",
        "eu_same",
        "eu_null_stage",
        "market",
        "eu_stage",
    ],
)
def test_e4_matches_by_model_market_and_stage(
    scope: CauseScope, combination: Combination, stage: Stage | None, expected: bool
) -> None:
    assert matches(scope, combination, stage) is expected


def test_e4_link_targets_skips_linked_and_other_cited_cause() -> None:
    """Risk: a raise attaches its cause over a case that already has a different cited cause (Q-48)."""
    cause = ActiveCause(
        active_cause_id="S010-causa-1",
        categoria=CauseCategory.LINE_STOP,
        scope=PICKUP_ANY,
        opened_at="S010",
        opened_by=EVIDENCE,
    )
    ids = ("S010-Sedán-Local", "S010-Pickup-Local", "S010-Pickup-Brasil", "S011-Pickup-Europa")
    candidates = [
        Candidate(case=case_with(i, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM), stage=Stage.ASSEMBLY)
        for i in ids
    ]

    def cited(categoria: CauseCategory) -> dict[str, CitedCause]:
        return {
            ids[3]: CitedCause(categoria=categoria, etapa=Stage.ASSEMBLY, evidence=EVIDENCE, set_at="S008")
        }

    other = link_targets(cause, candidates, cited(CauseCategory.MISSING_PARTS), {ids[2]})
    same = link_targets(cause, candidates, cited(CauseCategory.LINE_STOP), {ids[2]})
    assert other == (ids[1],)
    assert same == (ids[1], ids[3])
