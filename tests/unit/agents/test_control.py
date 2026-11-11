"""009 T8: the code control of the investigator's output (R5, E2-E4, X2, X3)."""

from dataclasses import replace

import pytest
from agent_builders import RAISE5, lift_proposal, output_text, set_cause_proposal
from control_builders import S006_TASK, S010_TASK, incident_logbooks
from incident_runs import AC1, F3, F5, F6
from judgment_builders import PL_CASE

from plant_monitor.agents.control import InvestigatorTask, check_output

MAX_CHARS = 2000
NO_DECLARADA = "no_declarada is never proposed: code keeps it when no logbook names a cause"
NOT_FOUND = "se detuvo la línea de montaje de Pickup"
OBJECT_ERROR = "output is not a JSON object"


def padded(length: int) -> str:
    """'{"propuestas":[]}' padded with trailing spaces to 'length' characters."""
    return output_text().ljust(length)


@pytest.mark.parametrize(
    ("text", "ids", "errors"),
    [
        pytest.param(output_text(), (), (), id="a-empty"),
        pytest.param(f"```json\n{output_text(RAISE5)}\n```", ("S010-p1",), (), id="b-fenced"),
        pytest.param("Sin causas.", None, (OBJECT_ERROR,), id="c-prose"),
        pytest.param(padded(2000), (), (), id="d-at-the-cap"),
        pytest.param(
            padded(2001), None, ("output is 2001 characters, over the maximum of 2000",), id="d-over-the-cap"
        ),
        pytest.param('{"propuestas":[{"tipo":"close_case"}]}', None, ("schema: ",), id="e-schema"),
    ],
)
def test_e2_control_accepts_or_returns_the_r5_errors(
    text: str, ids: tuple[str, ...] | None, errors: tuple[str, ...]
) -> None:
    """E2: accepted proposals get ids '<snapshot>-p<n>'; each failure gives its own error."""
    result = check_output(text, S010_TASK, incident_logbooks(), MAX_CHARS)
    assert (None if result.accepted is None else tuple(p.id for p in result.accepted)) == ids
    assert len(result.errors) == len(errors)
    assert all(error.startswith(prefix) for error, prefix in zip(result.errors, errors, strict=True))


@pytest.mark.parametrize(
    ("third", "third_error"),
    [
        pytest.param({**RAISE5, "fragmento": NOT_FOUND}, "fragment not found in T05", id="fragment"),
        pytest.param(
            {**RAISE5, "bitacora": "T06", "fragmento": F6},
            "logbook T06 is not available at S010: it closes at S012",
            id="variant-t06",
        ),
    ],
)
def test_e3_every_proposal_is_checked_and_the_first_failure_of_each_is_reported(
    third: dict[str, object], third_error: str
) -> None:
    """E3: four failing proposals give four errors in order, and nothing is accepted."""
    proposals = [
        set_cause_proposal(PL_CASE, "no_declarada", "T05", F5, "activa_sin_fecha"),
        {**RAISE5, "estado_causa": "con_fecha"},
        third,
        set_cause_proposal("S010-Sedán-Local", "parada_de_linea", "T05", F5, "con_fecha"),
    ]
    result = check_output(output_text(*proposals), S010_TASK, incident_logbooks(), MAX_CHARS)
    assert result.accepted is None
    assert result.errors == (
        f"propuestas[0]: {NO_DECLARADA}",
        "propuestas[1]: raise needs estado_causa activa_sin_fecha, got con_fecha",
        f"propuestas[2]: {third_error}",
        "propuestas[3]: case S010-Sedán-Local is not in this task",
    )


@pytest.mark.parametrize(
    ("task", "proposal", "ids", "errors"),
    [
        pytest.param(
            S006_TASK,
            lift_proposal(AC1, "T03", F3, "con_fecha"),
            None,
            ("propuestas[0]: lift needs estado_causa resuelta, got con_fecha",),
            id="a-lift-dated",
        ),
        pytest.param(
            S006_TASK, lift_proposal(AC1, "T03", F3, "resuelta"), ("S006-p1",), (), id="b-lift-judgment-x2"
        ),
        pytest.param(
            S006_TASK,
            lift_proposal("S099-causa-1", "T03", F3, "resuelta"),
            None,
            ("propuestas[0]: active cause S099-causa-1 is not in this task",),
            id="c-unknown-cause",
        ),
        pytest.param(
            S010_TASK,
            set_cause_proposal(PL_CASE, "parada_de_linea", "T05", F5, "con_fecha"),
            ("S010-p1",),
            (),
            id="d-set-cause-any-state",
        ),
    ],
)
def test_e4_estado_causa_and_scope_checks(
    task: InvestigatorTask, proposal: dict[str, object], ids: tuple[str, ...] | None, errors: tuple[str, ...]
) -> None:
    """E4: 'lift' needs 'resuelta', scope ids must belong to the task, 'set_cause' takes any state."""
    result = check_output(output_text(proposal), task, incident_logbooks(), MAX_CHARS)
    assert (None if result.accepted is None else tuple(p.id for p in result.accepted)) == ids
    assert result.errors == errors


@pytest.mark.parametrize(
    ("task", "proposal", "kind"),
    [
        pytest.param(S010_TASK, RAISE5, "raise", id="raise"),
        pytest.param(S006_TASK, lift_proposal(AC1, "T03", F3, "resuelta"), "lift", id="lift"),
    ],
)
def test_r2b_r5_cause_lookup_mode_refuses_raise_and_lift_and_accepts_set_cause(
    task: InvestigatorTask, proposal: dict[str, object], kind: str
) -> None:
    """R2b, R5: with 'cause_lookup' on the task, only 'set_cause' passes; the check comes first."""
    refused = check_output(
        output_text(proposal), replace(task, cause_lookup=True), incident_logbooks(), MAX_CHARS
    )
    assert refused.accepted is None
    assert refused.errors == (
        f"propuestas[0]: only set_cause is proposed when looking up a cause; got {kind}",
    )
    good = set_cause_proposal(PL_CASE, "parada_de_linea", "T05", F5, "con_fecha")
    accepted = check_output(
        output_text(good), replace(S010_TASK, cause_lookup=True), incident_logbooks(), MAX_CHARS
    )
    assert accepted.accepted is not None
    assert [p.id for p in accepted.accepted] == ["S010-p1"]
