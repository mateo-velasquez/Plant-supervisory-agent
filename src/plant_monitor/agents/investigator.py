"""The investigator's task text and its end-of-turn review through code control (009 R2, R3, R6)."""

import json
from dataclasses import dataclass, field

from plant_monitor.agents.brief import cause_item
from plant_monitor.agents.control import CitationCheck, InvestigatorTask, TaskCase, check_output
from plant_monitor.agents.loop import LoopOutcome
from plant_monitor.domain.proposals import ValidatedProposal

TASK_INSTRUCTION = (
    "Read the pending logbooks listed below and return the cause proposals as the JSON object "
    "the prompt describes."
)
CAUSE_LOOKUP_INSTRUCTION = (
    "Look for the cause of each case listed below in the readable logbooks "
    "('list_available_logbooks', 'get_logbook') and return the cause proposals as the JSON object "
    "the prompt describes."
)
CORRECTION_HEADER = "Code rejected your output. Fix these errors and send the whole JSON again:"


def _case_item(case: TaskCase) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "modelo": case.modelo.value,
        "mercado": case.mercado.value,
        "estado": case.estado.value,
        "etapa": None if case.etapa is None else case.etapa.value,
    }


def render_task(task: InvestigatorTask) -> str:
    """The constant instruction line, a newline, then the task as compact JSON."""
    payload = {
        "snapshot_id": task.snapshot_id,
        "turno_id": task.turno_id,
        "posicion": task.position.value,
        "bitacoras": list(task.logbooks),
        "casos_sin_causa": [_case_item(case) for case in task.cases],
        "causas_activas": [cause_item(cause, case_ids) for cause, case_ids in task.active_causes],
    }
    instruction = CAUSE_LOOKUP_INSTRUCTION if task.cause_lookup else TASK_INSTRUCTION
    return f"{instruction}\n{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"


class NothingRequired:
    """The investigator writes no notice text, so no tool turn ends its loop."""

    def required(self) -> tuple[str, ...]:
        return ()

    def missing(self) -> tuple[str, ...]:
        return ()


@dataclass
class ReviewLog:
    """What control saw, filled as the loop runs so an aborted line keeps it."""

    rejections: list[tuple[str, ...]] = field(default_factory=list)
    accepted: tuple[ValidatedProposal, ...] | None = None


class ProposalReview:
    """The investigator's 'EndReview': control decides; one correction note, then a fallback."""

    def __init__(
        self, task: InvestigatorTask, citations: CitationCheck, max_chars: int, log: ReviewLog
    ) -> None:
        self._task = task
        self._citations = citations
        self._max_chars = max_chars
        self._log = log

    @property
    def exhausted(self) -> LoopOutcome:
        return LoopOutcome.INVALID_OUTPUT

    def review(self, text: str) -> str | None:
        result = check_output(text, self._task, self._citations, self._max_chars)
        if result.accepted is None:
            self._log.rejections.append(result.errors)
            return "\n".join([CORRECTION_HEADER, *(f"- {error}" for error in result.errors)])
        self._log.accepted = result.accepted
        return None
