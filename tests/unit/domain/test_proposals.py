"""009 T4: proposal schema (R4, E1)."""

from typing import Any

import pytest
from incident_runs import F5
from pydantic import TypeAdapter, ValidationError

from plant_monitor.domain.causes import CauseScope
from plant_monitor.domain.enums import Model, Stage
from plant_monitor.domain.proposals import Proposal, RaiseProposal

RAISE5: dict[str, Any] = {
    "tipo": "raise",
    "categoria": "parada_de_linea",
    "etapa": "montaje",
    "modelo": "Pickup",
    "mercado": None,
    "bitacora": "T05",
    "fragmento": F5,
    "estado_causa": "activa_sin_fecha",
}
LIFT4: dict[str, Any] = {
    "tipo": "lift",
    "causa_activa": "S004-causa-1",
    "bitacora": "T04",
    "fragmento": "La auditoría de homologación terminó a las 8:30",
    "estado_causa": "resuelta",
}


def test_e1a_raise_parses_with_its_scope() -> None:
    proposal = TypeAdapter(Proposal).validate_python(RAISE5)
    assert isinstance(proposal, RaiseProposal)
    assert proposal.scope == CauseScope(modelo=Model.PICKUP, etapa=Stage.ASSEMBLY, mercado=None)


@pytest.mark.parametrize(
    "payload",
    [
        {**RAISE5, "tipo": "close_case"},
        {**RAISE5, "unidades": 4},
        {**LIFT4, "categoria": "parada_de_linea"},
        {**RAISE5, "estado_causa": "abierta"},
    ],
    ids=["b_unknown_tipo", "c_extra_key", "d_lift_extra_key", "e_unknown_estado"],
)
def test_e1bcde_invalid_proposals_are_refused(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Proposal).validate_python(payload)
