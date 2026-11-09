"""Snapshot judgment adapter: ledger writes that re-decide and rebase, behind a failure guard (R10, R13)."""

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Protocol

from plant_monitor.cases.draft import NoticeDraft
from plant_monitor.cases.ledger import CauseLedger
from plant_monitor.domain.causes import Cause, CauseCategory, CauseScope, Evidence
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.mcp_server.context import FrameWriter, JudgmentResult
from plant_monitor.runner.pipeline import SnapshotDecision


class WritesClosed(RejectedRequest):
    """An internal error was stored, so no further write is accepted at this snapshot."""

    def __init__(self, snapshot_id: str) -> None:
        super().__init__(f"writes are closed at {snapshot_id} after an internal error")


class Redecider(Protocol):
    """Re-runs the lifecycle and notices after a judgment write; 'ThresholdPipeline' satisfies it."""

    def redecide(self, decision: SnapshotDecision) -> SnapshotDecision: ...


class SnapshotWriter(FrameWriter, Protocol):
    """The frame's writers plus what the pipeline reads back once the loop ends."""

    def required(self) -> tuple[str, ...]:
        """Ids of the notices that need a text."""
        ...

    def written(self) -> tuple[str, ...]:
        """Ids of the notices written so far."""
        ...

    def final(self) -> SnapshotDecision:
        """The last decision with the written texts in its notices."""
        ...

    def failure(self) -> Exception | None:
        """The first internal error a write raised, if any."""
        ...


JudgmentFactory = Callable[[SnapshotDecision], SnapshotWriter]


class SnapshotJudgment:
    """The snapshot's draft and ledger behind one object; every write runs inside the failure guard."""

    def __init__(
        self, steps: Redecider, decision: SnapshotDecision, ledger: CauseLedger, max_chars: int
    ) -> None:
        self._steps = steps
        self._decision = decision
        self._ledger = ledger
        self._draft = NoticeDraft(decision.notices, max_chars)
        self._failure: Exception | None = None

    @property
    def _snapshot_id(self) -> str:
        return self._decision.snapshot.snapshot_id

    def _guarded[T](self, write: Callable[[], T]) -> T:
        """Run a write: refusals propagate, other errors are stored once and close later writes."""
        if self._failure is not None:
            raise WritesClosed(self._snapshot_id)
        try:
            return write()
        except RejectedRequest:
            raise
        except Exception as error:
            self._failure = error
            raise

    def _judged(
        self, case_ids: tuple[str, ...], cause_id: str | None, lifted_at: str | None
    ) -> JudgmentResult:
        """Re-decide after a ledger write, rebase the draft and describe what changed."""
        self._decision = self._steps.redecide(self._decision)
        changed = self._draft.rebase(self._decision.notices)
        return JudgmentResult(case_ids, cause_id, lifted_at, changed, self._draft.missing())

    def set_cause(self, case_id: str, cause: Cause, evidence: Evidence) -> JudgmentResult:
        """Store a case's cited cause, then re-decide (R3, R10)."""

        def write() -> JudgmentResult:
            candidates = self._decision.candidates
            self._ledger.set_cause(self._snapshot_id, case_id, cause, evidence, candidates)
            return self._judged((case_id,), None, None)

        return self._guarded(write)

    def raise_severity(
        self, categoria: CauseCategory, scope: CauseScope, evidence: Evidence
    ) -> JudgmentResult:
        """Open an active cause, then re-decide (R5, R10)."""

        def write() -> JudgmentResult:
            candidates = self._decision.candidates
            outcome = self._ledger.raise_severity(self._snapshot_id, categoria, scope, evidence, candidates)
            return self._judged(outcome.linked, outcome.active_cause_id, None)

        return self._guarded(write)

    def lift(self, active_cause_id: str, evidence: Evidence) -> JudgmentResult:
        """Lift an active cause, then re-decide (R9, R10)."""

        def write() -> JudgmentResult:
            self._ledger.lift(self._snapshot_id, active_cause_id, evidence)
            return self._judged((), active_cause_id, self._snapshot_id)

        return self._guarded(write)

    def write_alert(self, case_id: str, texto: str) -> str:
        """Store an alert text through the draft."""
        return self._guarded(lambda: self._draft.write_alert(case_id, texto))

    def write_news(self, texts: Sequence[tuple[str, str]]) -> tuple[str, ...]:
        """Store the report's texts through the draft."""
        return self._guarded(lambda: self._draft.write_news(texts))

    def missing(self) -> tuple[str, ...]:
        """Required ids without a text."""
        return self._draft.missing()

    def required(self) -> tuple[str, ...]:
        """Ids of the notices that need a text."""
        return self._draft.required()

    def written(self) -> tuple[str, ...]:
        """Ids written so far."""
        return self._draft.written()

    def final(self) -> SnapshotDecision:
        """The last decision with the draft's texts."""
        return replace(self._decision, notices=self._draft.build())

    def failure(self) -> Exception | None:
        """The first stored internal error."""
        return self._failure


def judgment_factory(steps: Redecider, ledger: CauseLedger, max_chars: int) -> JudgmentFactory:
    """A factory that builds one 'SnapshotJudgment' per decided snapshot."""

    def build(decision: SnapshotDecision) -> SnapshotWriter:
        return SnapshotJudgment(steps, decision, ledger, max_chars)

    return build
