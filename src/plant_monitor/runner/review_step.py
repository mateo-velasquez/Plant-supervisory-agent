"""The investigator step: plans pending logbooks, reads them and records the review marks (009 R2, R6-R8)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from plant_monitor.agents.control import InvestigatorTask, TaskCase
from plant_monitor.agents.investigator import NothingRequired, ProposalReview, ReviewLog, render_task
from plant_monitor.agents.loop import Coordinator, LoopLog, LoopOutcome
from plant_monitor.cases.registry import ReviewStore
from plant_monitor.cases.reviews import ReviewMark, next_review, pending_logbooks, review_succeeded
from plant_monitor.domain.notices import NoticeType
from plant_monitor.domain.proposals import ValidatedProposal
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.mcp_server.context import FrameHolder, SnapshotFrame
from plant_monitor.runner.bridge import run_in_frame
from plant_monitor.runner.pipeline import SnapshotDecision


@dataclass(frozen=True)
class ReviewPlan:
    """The pending logbooks of a snapshot, split into readable and missing ones."""

    present: tuple[str, ...]
    missing: tuple[str, ...]
    lookup: tuple[str, ...] = ()

    @property
    def pending(self) -> tuple[str, ...]:
        return (*self.present, *self.missing)


@dataclass(frozen=True)
class ReviewOutcome:
    """What the investigator step did: whether it ran, how it ended and what control accepted."""

    plan: ReviewPlan
    ran: bool
    outcome: LoopOutcome | None
    accepted: tuple[ValidatedProposal, ...]

    @property
    def valid(self) -> bool:
        """The loop ended 'done', so control accepted its output."""
        return self.ran and self.outcome is LoopOutcome.DONE


class LogbookReviewStep(Protocol):
    """The pipeline's view of the investigator step; 'InvestigatorStep' satisfies it."""

    def plan(self, decision: SnapshotDecision) -> ReviewPlan: ...

    def run(
        self, plan: ReviewPlan, decision: SnapshotDecision, log: LoopLog, review_log: ReviewLog
    ) -> ReviewOutcome: ...

    def record(
        self,
        outcome: ReviewOutcome,
        coordinator: LoopOutcome | None,
        snapshot_id: str,
        applied: Sequence[str] = (),
    ) -> Mapping[str, ReviewMark]: ...


class InvestigatorStep:
    """Runs the read-only investigator over the pending logbooks; only 'record' writes, and only marks."""

    def __init__(
        self,
        investigator: Coordinator,
        frames: FrameHolder,
        logbooks: LogbookStore,
        reviews: ReviewStore,
        max_attempts: int,
        max_chars: int,
    ) -> None:
        self._investigator = investigator
        self._frames = frames
        self._logbooks = logbooks
        self._reviews = reviews
        self._max_attempts = max_attempts
        self._max_chars = max_chars

    def plan(self, decision: SnapshotDecision) -> ReviewPlan:
        """Available logbooks not yet settled, split by whether their file exists."""
        sid = decision.snapshot.snapshot_id
        available = [turno_id for turno_id, _ in self._logbooks.available(sid)]
        pending = pending_logbooks(available, self._reviews.get(available))
        absent = self._logbooks.missing(pending, sid)
        present = tuple(t for t in pending if t not in absent)
        return ReviewPlan(present, absent, self._lookup(decision) if available and not present else ())

    @staticmethod
    def _lookup(decision: SnapshotDecision) -> tuple[str, ...]:
        """Alert cases with no cited cause, to look up in the readable logbooks (R2b)."""
        return tuple(
            n.case_id
            for n in decision.notices.decisions
            if n.tipo is NoticeType.ALERT and n.case_id not in decision.cited
        )

    def run(
        self, plan: ReviewPlan, decision: SnapshotDecision, log: LoopLog, review_log: ReviewLog
    ) -> ReviewOutcome:
        """Run the investigator on the present logbooks; nothing is written."""
        if not (plan.present or plan.lookup):
            return ReviewOutcome(plan, False, None, ())
        snapshot = decision.snapshot
        sid = snapshot.snapshot_id
        task = self._task(decision, plan)
        frame = SnapshotFrame(sid, snapshot.timestamp, decision.metrics, snapshot.unidades)
        review = ProposalReview(task, self._logbooks, self._max_chars, review_log)
        outcome = run_in_frame(
            self._frames,
            frame,
            self._investigator.run,
            sid,
            render_task(task),
            NothingRequired(),
            log,
            review,
        )
        accepted = (review_log.accepted or ()) if outcome is LoopOutcome.DONE else ()
        return ReviewOutcome(plan, True, outcome, accepted)

    def record(
        self,
        outcome: ReviewOutcome,
        coordinator: LoopOutcome | None,
        snapshot_id: str,
        applied: Sequence[str] = (),
    ) -> Mapping[str, ReviewMark]:
        """One attempt per pending logbook; a success waits for the coordinator's outcome (Q-53)."""
        unapplied = sum(1 for p in outcome.accepted if p.id not in applied)
        done = None if coordinator is None else coordinator is LoopOutcome.DONE
        present_ok = review_succeeded(outcome.valid, unapplied, done)
        pending = outcome.plan.pending
        current = self._reviews.get(pending)
        marks: dict[str, ReviewMark] = {}
        for turno_id in pending:
            succeeded = present_ok and turno_id in outcome.plan.present
            review, mark = next_review(
                current.get(turno_id), turno_id, snapshot_id, succeeded, self._max_attempts
            )
            self._reviews.save(review)
            marks[turno_id] = mark
        return marks

    def _task(self, decision: SnapshotDecision, plan: ReviewPlan) -> InvestigatorTask:
        cases = tuple(
            TaskCase(
                c.case.case_id, c.case.combination.modelo, c.case.combination.mercado, c.case.state, c.stage
            )
            for c in decision.candidates
            if c.case.case_id not in decision.cited and (not plan.lookup or c.case.case_id in plan.lookup)
        )
        return InvestigatorTask(
            snapshot_id=decision.snapshot.snapshot_id,
            turno_id=decision.shift.turno_id,
            position=decision.position,
            logbooks=plan.present,
            cases=cases,
            active_causes=decision.in_force,
            cause_lookup=bool(plan.lookup),
        )
