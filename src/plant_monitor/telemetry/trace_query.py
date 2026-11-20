"""Pure view of one notice: registry facts joined with the committed trace lines (013 R4-R11)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal

from pydantic import JsonValue, ValidationError

from plant_monitor.domain.cases import CaseHistoryRow
from plant_monitor.domain.causes import ActiveCause, CitedCause, Evidence, active_cause_id_for
from plant_monitor.domain.notices import Notice
from plant_monitor.domain.proposals import LiftProposal, RaiseProposal, SetCauseProposal, ValidatedProposal
from plant_monitor.domain.stored import StoredNotice
from plant_monitor.telemetry.trace import (
    AgentName,
    TextBy,
    TraceFile,
    TraceHook,
    TraceLine,
    TraceMode,
    TraceToolCall,
    TraceTotals,
    index_attempts,
)
from plant_monitor.telemetry.trace import text_by as text_by_of

OpeningStatus = Literal["found", "no_line", "no_proposal"]
_APPLY: Final = "apply_proposal"
_REPORT: Final = "emit_shift_report"
_CASE_ARG: Final = "case_id"
_ACTIVE_ARG: Final = "active_cause_id"
_LIFT_ARG: Final = "causa_activa"
_ID_ARGS: Final = (_CASE_ARG, _ACTIVE_ARG, _LIFT_ARG)
_LOGBOOK_ARG: Final = "bitacora"
_SHIFT_ARGS: Final = ("turno_id", _LOGBOOK_ARG)
_ITEMS_ARG: Final = "textos"


@dataclass(frozen=True)
class HistoryView:
    """The history row shown, its predecessor and the case's first snapshot."""

    row: CaseHistoryRow
    previous: CaseHistoryRow | None
    at_notice: bool
    opened_at: str


@dataclass(frozen=True)
class CallView:
    """A traced call and whether it concerns the case."""

    call: TraceToolCall
    this_case: bool


@dataclass(frozen=True)
class AgentView:
    """One agent's section of a trace line."""

    agent: AgentName
    outcome: str
    trigger: str | None
    calls: tuple[CallView, ...]
    proposals: tuple[Mapping[str, JsonValue], ...]


@dataclass(frozen=True)
class AbortedAttempt:
    """An aborted line of the notice's snapshot, without tool calls."""

    file: str
    outcome: str
    investigator_outcome: str | None
    totals: TraceTotals


@dataclass(frozen=True)
class LineView:
    """The committed line of the notice's snapshot."""

    file: str
    decision: str
    decision_reason: str | None
    agents: tuple[AgentView, ...]
    no_agent: bool
    hooks: tuple[TraceHook, ...]
    totals: TraceTotals


@dataclass(frozen=True)
class Opening:
    """The proposal and apply call that opened a cause, or why none is shown."""

    snapshot_id: str
    status: OpeningStatus
    file: str | None
    proposal: Mapping[str, JsonValue] | None
    apply: TraceToolCall | None

    def __post_init__(self) -> None:
        shape = (self.file is not None, self.proposal is not None, self.apply is not None)
        expected = {"found": (True, True, True), "no_proposal": (True, False, False)}.get(
            self.status, (False, False, False)
        )
        if shape != expected:
            raise ValueError(f"opening {self.status} has an invalid combination of fields")


@dataclass(frozen=True)
class CauseView:
    """An active cause linked to the case, with its raise opening (None in a threshold-only run)."""

    cause: ActiveCause
    linked_at: str
    lift_shown: bool
    opening: Opening | None


@dataclass(frozen=True)
class NoticeTrace:
    """Everything the renderer prints for one notice."""

    notice: Notice
    history: HistoryView
    cited: CitedCause | None
    causes: tuple[CauseView, ...]
    mode: TraceMode
    line: LineView | None
    aborted: tuple[AbortedAttempt, ...]
    text_by: TextBy

    def _calls(self) -> tuple[TraceToolCall, ...]:
        agents = () if self.line is None else self.line.agents
        return tuple(view.call for agent in agents for view in agent.calls)

    def shown_snapshots(self) -> frozenset[str]:
        """Every snapshot id the view shows (R11)."""
        found = {self.notice.snapshot_id, self.history.opened_at, self.history.row.snapshot_id}
        if self.history.previous is not None:
            found.add(self.history.previous.snapshot_id)
        for view in self.causes:
            found |= {view.cause.opened_at, view.linked_at}
            if view.lift_shown and view.cause.lifted_at is not None:
                found.add(view.cause.lifted_at)
            if view.opening is not None:
                found.add(view.opening.snapshot_id)
        if self.cited is not None:
            found.add(self.cited.set_at)
            if self.cited.active_cause_id is not None:
                found.add(_prefix(self.cited.active_cause_id))
        for call in self._calls():
            found |= {_prefix(value) for value in _case_ids(call, _ID_ARGS)}
        for proposal in self._proposals():
            for key in _ID_ARGS:
                found |= {_prefix(value) for value in _strings(proposal, key)}
        return frozenset(found)

    def _proposals(self) -> tuple[Mapping[str, JsonValue], ...]:
        agents = () if self.line is None else self.line.agents
        openings = tuple(v.opening.proposal for v in self.causes if v.opening and v.opening.proposal)
        return (*(p for agent in agents for p in agent.proposals), *openings)

    def shown_shifts(self) -> frozenset[str]:
        """Every shift id the view shows (R11)."""
        found = {item.bitacora for item in self.notice.evidencia}
        for view in self.causes:
            found.add(view.cause.opened_by.bitacora)
            if view.lift_shown and view.cause.lifted_by is not None:
                found.add(view.cause.lifted_by.bitacora)
        for call in self._calls():
            for key in _SHIFT_ARGS:
                found |= _strings(call.arguments, key)
        for proposal in self._proposals():
            found |= _strings(proposal, _LOGBOOK_ARG)
        return frozenset(found)


def _prefix(identifier: str) -> str:
    """The snapshot id at the start of a case or cause id."""
    return identifier.split("-", 1)[0]


def _strings(data: Mapping[str, JsonValue], key: str) -> set[str]:
    """The value of 'key' when it is a string, as a set."""
    value = data.get(key)
    return {value} if isinstance(value, str) else set()


def _case_ids(call: TraceToolCall, keys: Sequence[str] = (_CASE_ARG,)) -> tuple[str, ...]:
    """Every string argument of a call under 'keys', top-level or inside 'textos'."""
    found: list[str] = []
    for key in keys:
        found.extend(_strings(call.arguments, key))
    items = call.arguments.get(_ITEMS_ARG)
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                for key in keys:
                    found.extend(_strings(item, key))
    return tuple(found)


def _seq(order: Mapping[str, int], snapshot_id: str) -> int:
    """Processing position of a snapshot; a missing one is an error."""
    if snapshot_id not in order:
        raise ValueError(f"snapshot {snapshot_id} is not in the processed order")
    return order[snapshot_id]


def _history(stored: StoredNotice) -> HistoryView:
    """The last row at or before the notice's snapshot (R4, R5)."""
    snapshot_id = stored.notice.snapshot_id
    limit = _seq(stored.order, snapshot_id)
    rows = sorted(stored.history, key=lambda row: _seq(stored.order, row.snapshot_id))
    upto = [row for row in rows if _seq(stored.order, row.snapshot_id) <= limit]
    if not upto:
        raise ValueError(f"no history row at or before {snapshot_id}")
    row = upto[-1]
    previous = upto[-2] if len(upto) > 1 else None
    return HistoryView(
        row=row, previous=previous, at_notice=row.snapshot_id == snapshot_id, opened_at=rows[0].snapshot_id
    )


def _applied(line: TraceLine) -> tuple[tuple[TraceToolCall, ValidatedProposal, Mapping[str, JsonValue]], ...]:
    """Successful 'apply_proposal' calls whose proposal parses (R6 step 1)."""
    if line.investigator is None:
        return ()
    by_id = {p.get("id"): p for p in line.investigator.proposals}
    found: list[tuple[TraceToolCall, ValidatedProposal, Mapping[str, JsonValue]]] = []
    for call in line.tool_calls:
        if call.name != _APPLY or call.is_error:
            continue
        stored = by_id.get(call.arguments.get("propuesta"))
        if stored is None:
            continue
        rest = {key: value for key, value in stored.items() if key != "id"}
        try:
            parsed = ValidatedProposal.model_validate({"id": stored["id"], "proposal": rest})
        except ValidationError:
            continue
        found.append((call, parsed, stored))
    return tuple(found)


def _raise_match(line: TraceLine, cause: ActiveCause) -> tuple[TraceToolCall, Mapping[str, JsonValue]] | None:
    """The single raise apply that opened 'cause', cross-checked by ordinal (R6 steps 2-4)."""
    raises = [
        (call, parsed.proposal, stored)
        for call, parsed, stored in _applied(line)
        if isinstance(parsed.proposal, RaiseProposal)
    ]
    candidates = [
        (k, call, stored)
        for k, (call, proposal, stored) in enumerate(raises, start=1)
        if isinstance(proposal, RaiseProposal)
        and proposal.categoria == cause.categoria
        and proposal.scope == cause.scope
        and Evidence(bitacora=proposal.bitacora, fragmento=proposal.fragmento.strip()) == cause.opened_by
    ]
    if len(candidates) != 1:
        return None
    k, call, stored = candidates[0]
    if active_cause_id_for(line.snapshot_id, k) != cause.active_cause_id:
        return None
    return call, stored


def _opening(committed: Mapping[str, tuple[str, TraceLine]], cause: ActiveCause) -> Opening:
    """The raise opening of a cause from its opening snapshot's committed line (R6)."""
    picked = committed.get(cause.opened_at)
    if picked is None:
        return Opening(cause.opened_at, "no_line", None, None, None)
    file, line = picked
    match = _raise_match(line, cause)
    if match is None:
        return Opening(cause.opened_at, "no_proposal", file, None, None)
    return Opening(cause.opened_at, "found", file, match[1], match[0])


def _marked(line: TraceLine, case_id: str, linked: Sequence[ActiveCause]) -> frozenset[int]:
    """Identities of the successful applies that concern the case (R8)."""
    ids = {cause.active_cause_id for cause in linked}
    matched = {id(match[0]) for cause in linked if (match := _raise_match(line, cause)) is not None}
    marked = set(matched)
    for call, parsed, _ in _applied(line):
        proposal = parsed.proposal
        own_cause = isinstance(proposal, SetCauseProposal) and proposal.case_id == case_id
        own_lift = isinstance(proposal, LiftProposal) and proposal.causa_activa in ids
        if own_cause or own_lift:
            marked.add(id(call))
    return frozenset(marked)


def _concerns(call: TraceToolCall, case_id: str, marked: frozenset[int]) -> bool:
    """True when the call names the case, by argument, report item or applied proposal."""
    if call.arguments.get(_CASE_ARG) == case_id:
        return True
    if call.name == _REPORT and case_id in _case_ids(call):
        return True
    return id(call) in marked


def _line_view(
    file: str, line: TraceLine, case_id: str, linked: Sequence[ActiveCause], text_by: TextBy
) -> LineView:
    """The committed line as sections, calls marked for the case (R8)."""
    marked = _marked(line, case_id, linked)
    agents: list[AgentView] = []
    investigator = line.investigator
    if investigator is not None:
        agents.append(
            AgentView(
                agent="investigator",
                outcome=investigator.outcome,
                trigger=investigator.trigger,
                calls=tuple(CallView(c, _concerns(c, case_id, marked)) for c in investigator.tool_calls),
                proposals=tuple(investigator.proposals),
            )
        )
    if "coordinator" in line.ran:
        agents.append(
            AgentView(
                agent="coordinator",
                outcome=line.outcome,
                trigger=None,
                calls=tuple(CallView(c, _concerns(c, case_id, marked)) for c in line.tool_calls),
                proposals=(),
            )
        )
    return LineView(
        file=file,
        decision=line.decision,
        decision_reason=line.decision_reason,
        agents=tuple(agents),
        no_agent=not line.ran and text_by == "template",
        hooks=tuple(line.hooks),
        totals=line.totals,
    )


def _cited(stored: StoredNotice) -> CitedCause | None:
    """The cited cause, only when it matches the notice's cause and was set by its snapshot (R4)."""
    cited, notice = stored.cited, stored.notice
    if cited is None or notice.causa != cited.cause or notice.evidencia != (cited.evidence,):
        return None
    if _seq(stored.order, cited.set_at) > _seq(stored.order, notice.snapshot_id):
        return None
    return cited


def _only(files: Sequence[TraceFile], snapshots: set[str]) -> list[TraceFile]:
    """The files reduced to the lines of 'snapshots'."""
    return [TraceFile(f.name, tuple(row for row in f.lines if row.snapshot_id in snapshots)) for f in files]


def build_notice_trace(stored: StoredNotice, traces: Sequence[TraceFile] | None) -> NoticeTrace:
    """Join the stored notice with the trace files; 'None' or no files means a threshold-only run."""
    notice = stored.notice
    limit = _seq(stored.order, notice.snapshot_id)
    files = traces or ()
    mode: TraceMode = "agent" if files else "thresholds_only"
    linked: list[tuple[ActiveCause, str]] = []
    for cause in stored.causes:
        at = stored.links.get(cause.active_cause_id)
        if at is not None and _seq(stored.order, at) <= limit:
            linked.append((cause, at))
    # Only the snapshots the view uses are indexed, so a duplicate elsewhere stays harmless (013 R7).
    # The notice's own snapshot is checked first, so its duplicate is the one reported.
    own = {notice.snapshot_id}
    committed, aborted_by = index_attempts(_only(files, own))
    picked = committed.get(notice.snapshot_id)
    aborted = aborted_by.get(notice.snapshot_id, ())
    committed, _ = index_attempts(_only(files, own | {cause.opened_at for cause, _ in linked}))
    causes = tuple(
        CauseView(
            cause=cause,
            linked_at=at,
            lift_shown=cause.lifted_at is not None and _seq(stored.order, cause.lifted_at) <= limit,
            opening=_opening(committed, cause) if files else None,
        )
        for cause, at in linked
    )
    line = None if picked is None else picked[1]
    text_by = text_by_of(notice.notice_id, line, mode)
    line_view = (
        None
        if picked is None
        else _line_view(picked[0], picked[1], notice.case_id, [cause for cause, _ in linked], text_by)
    )
    return NoticeTrace(
        notice=notice,
        history=_history(stored),
        cited=_cited(stored),
        causes=causes,
        mode=mode,
        line=line_view,
        aborted=tuple(
            AbortedAttempt(
                file=file,
                outcome=row.outcome,
                investigator_outcome=None if row.investigator is None else row.investigator.outcome,
                totals=row.totals,
            )
            for file, row in aborted
        ),
        text_by=text_by,
    )
