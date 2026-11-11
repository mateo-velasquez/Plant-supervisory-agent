"""Code control of the investigator's output: schema, size, states, scope and citations (009 R5)."""

import json
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import ActiveCause, CauseCategory
from plant_monitor.domain.enums import Market, Model, ShiftPosition, Stage
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.proposals import (
    CauseState,
    InvestigatorOutput,
    LiftProposal,
    Proposal,
    RaiseProposal,
    SetCauseProposal,
    ValidatedProposal,
    proposal_id_for,
)

FENCE = "```"
FENCE_OPENERS = (f"{FENCE}json", FENCE)
NOT_AN_OBJECT = "output is not a JSON object"
LOOKUP_ONLY_SET_CAUSE = "only set_cause is proposed when looking up a cause"
NO_DECLARADA_REFUSAL = "no_declarada is never proposed: code keeps it when no logbook names a cause"


class CitationCheck(Protocol):
    """Verifies a logbook citation; 'LogbookStore' satisfies it."""

    def verify_citation(self, turno_id: str, fragment: str, snapshot_id: str) -> None: ...


@dataclass(frozen=True)
class TaskCase:
    """A case evaluated at the snapshot that has no cited cause."""

    case_id: str
    modelo: Model
    mercado: Market
    estado: CaseState
    etapa: Stage | None


@dataclass(frozen=True)
class InvestigatorTask:
    """What the investigator is asked at one snapshot."""

    snapshot_id: str
    turno_id: str
    position: ShiftPosition
    logbooks: tuple[str, ...]
    cases: tuple[TaskCase, ...]
    active_causes: tuple[tuple[ActiveCause, tuple[str, ...]], ...]
    cause_lookup: bool = False


@dataclass(frozen=True)
class ControlResult:
    """The accepted proposals, or the errors; 'accepted' is None iff there are errors."""

    accepted: tuple[ValidatedProposal, ...] | None
    errors: tuple[str, ...]


def _unfenced(text: str) -> str:
    """Drop one leading code-fence line and one trailing one."""
    lines = text.strip().splitlines()
    if len(lines) >= 2 and lines[0].strip() in FENCE_OPENERS and lines[-1].strip() == FENCE:
        return "\n".join(lines[1:-1])
    return text


def _schema_errors(error: ValidationError) -> tuple[str, ...]:
    return tuple(
        f"schema: {'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )


def _state_error(proposal: Proposal) -> str | None:
    state: CauseState = proposal.estado_causa
    if isinstance(proposal, RaiseProposal) and state is not CauseState.ACTIVE_NO_DATE:
        return f"raise needs estado_causa {CauseState.ACTIVE_NO_DATE.value}, got {state.value}"
    if isinstance(proposal, LiftProposal) and state is not CauseState.RESOLVED:
        return f"lift needs estado_causa {CauseState.RESOLVED.value}, got {state.value}"
    return None


def _scope_error(proposal: Proposal, task: InvestigatorTask) -> str | None:
    if isinstance(proposal, SetCauseProposal) and proposal.case_id not in {c.case_id for c in task.cases}:
        return f"case {proposal.case_id} is not in this task"
    if isinstance(proposal, LiftProposal) and proposal.causa_activa not in {
        cause.active_cause_id for cause, _ in task.active_causes
    }:
        return f"active cause {proposal.causa_activa} is not in this task"
    return None


def _proposal_error(proposal: Proposal, task: InvestigatorTask, citations: CitationCheck) -> str | None:
    """The first failing check of one proposal, in R5 order."""
    if task.cause_lookup and not isinstance(proposal, SetCauseProposal):
        return f"{LOOKUP_ONLY_SET_CAUSE}; got {proposal.tipo}"
    if not isinstance(proposal, LiftProposal) and proposal.categoria is CauseCategory.UNDECLARED:
        return NO_DECLARADA_REFUSAL
    if (error := _state_error(proposal)) or (error := _scope_error(proposal, task)):
        return error
    try:
        citations.verify_citation(proposal.bitacora, proposal.fragmento.strip(), task.snapshot_id)
    except RejectedRequest as refusal:
        return str(refusal)
    return None


def check_output(
    text: str, task: InvestigatorTask, citations: CitationCheck, max_chars: int
) -> ControlResult:
    """Accept the investigator's final text as validated proposals, or return every error found."""
    if len(text) > max_chars:
        return ControlResult(None, (f"output is {len(text)} characters, over the maximum of {max_chars}",))
    try:
        data = json.loads(_unfenced(text))
    except json.JSONDecodeError:
        return ControlResult(None, (NOT_AN_OBJECT,))
    if not isinstance(data, dict):
        return ControlResult(None, (NOT_AN_OBJECT,))
    try:
        output = InvestigatorOutput.model_validate(data)
    except ValidationError as error:
        return ControlResult(None, _schema_errors(error))
    errors = tuple(
        f"propuestas[{i}]: {message}"
        for i, proposal in enumerate(output.propuestas)
        if (message := _proposal_error(proposal, task, citations))
    )
    if errors:
        return ControlResult(None, errors)
    accepted = tuple(
        ValidatedProposal(id=proposal_id_for(task.snapshot_id, n), proposal=proposal)
        for n, proposal in enumerate(output.propuestas, start=1)
    )
    return ControlResult(accepted, ())
