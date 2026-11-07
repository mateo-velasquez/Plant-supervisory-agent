"""004 T3: 'CaseFacts' validation of its Q-32 cause row and its current metrics (E20f)."""

import pytest

from plant_monitor.cases.facts import CaseFacts
from plant_monitor.domain.cases import CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics

from builders import PICKUP_BRAZIL, case_with, history_row, measured

CASE_ID = "S020-Pickup-Brasil"
CASE = case_with(CASE_ID, CaseState.OPEN, Severity.HIGH, Severity.HIGH, at="S020")
CURRENT = measured(PICKUP_BRAZIL, -7.0, -23.3, 0.0, Stage.ASSEMBLY, Severity.HIGH, Severity.NONE)
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)


def test_e20f_valid_facts_expose_the_cause_row_stage() -> None:
    facts = CaseFacts(CASE, CURRENT, history_row(CASE_ID, "S020", Stage.ASSEMBLY, minimum=Severity.HIGH))
    assert facts.cause_stage is Stage.ASSEMBLY


@pytest.mark.parametrize(
    ("current", "cause_row"),
    [
        pytest.param(
            CURRENT,
            history_row(CASE_ID, "S020", Stage.ASSEMBLY, minimum=Severity.NONE),
            id="row-without-deviation",
        ),
        pytest.param(
            CURRENT, history_row("S019-Pickup-Brasil", "S020", Stage.ASSEMBLY), id="row-of-another-case"
        ),
        pytest.param(
            measured(SUV_LOCAL, -7.0, -23.3, 0.0, Stage.ASSEMBLY, Severity.HIGH, Severity.NONE),
            history_row(CASE_ID, "S020", Stage.ASSEMBLY),
            id="metrics-of-another-combination",
        ),
    ],
)
def test_e20f_facts_with_an_inconsistent_input_raise_naming_the_case(
    current: CombinationMetrics, cause_row: CaseHistoryRow
) -> None:
    """'metrics-of-another-combination' is the plan's third '__post_init__' check."""
    with pytest.raises(ValueError, match=CASE_ID):
        CaseFacts(CASE, current, cause_row)
