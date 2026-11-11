"""Investigator proposal types (009 R4); values keep the data contract's Spanish spelling (ADR-0005)."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field, JsonValue

from plant_monitor.domain.causes import CauseCategory, CauseScope
from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.models import FrozenModel


class ProposalKind(StrEnum):
    """What a proposal asks the coordinator to do."""

    SET_CAUSE = "set_cause"
    RAISE = "raise"
    LIFT = "lift"


class CauseState(StrEnum):
    """State of the cause as the logbook reports it."""

    ACTIVE_NO_DATE = "activa_sin_fecha"
    DATED = "con_fecha"
    RESOLVED = "resuelta"


class _Proposal(FrozenModel):
    """Base of the proposals: unknown keys are refused."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class SetCauseProposal(_Proposal):
    """Set the cited cause of one case."""

    tipo: Literal["set_cause"]
    case_id: str
    categoria: CauseCategory
    etapa: Stage
    bitacora: str
    fragmento: str
    estado_causa: CauseState


class RaiseProposal(_Proposal):
    """Open an active cause over a scope."""

    tipo: Literal["raise"]
    categoria: CauseCategory
    etapa: Stage
    modelo: Model
    mercado: Market | None = None
    bitacora: str
    fragmento: str
    estado_causa: CauseState

    @property
    def scope(self) -> CauseScope:
        return CauseScope(modelo=self.modelo, etapa=self.etapa, mercado=self.mercado)


class LiftProposal(_Proposal):
    """Lift an active cause in force."""

    tipo: Literal["lift"]
    causa_activa: str
    bitacora: str
    fragmento: str
    estado_causa: CauseState


Proposal = Annotated[SetCauseProposal | RaiseProposal | LiftProposal, Field(discriminator="tipo")]


class InvestigatorOutput(_Proposal):
    """The investigator's whole answer."""

    propuestas: tuple[Proposal, ...]


class ValidatedProposal(FrozenModel):
    """A proposal that passed control, with its id."""

    id: str
    proposal: Proposal

    def item(self) -> dict[str, JsonValue]:
        """The brief and trace shape: the id first, then the proposal's fields."""
        return {"id": self.id, **self.proposal.model_dump(mode="json")}


def proposal_id_for(snapshot_id: str, n: int) -> str:
    """Id of the n-th validated proposal of a snapshot."""
    return f"{snapshot_id}-p{n}"
