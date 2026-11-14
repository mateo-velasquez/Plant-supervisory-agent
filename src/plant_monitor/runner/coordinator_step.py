"""The coordinator step: brief, proposal book and loop in one frame with the snapshot writer (009 R1, R10)."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import partial

from plant_monitor.agents.brief import render_brief
from plant_monitor.agents.loop import Coordinator, LoopLog, LoopOutcome
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import Notice, NoticeType
from plant_monitor.domain.perspectives import CasePerspective
from plant_monitor.domain.proposals import ValidatedProposal
from plant_monitor.mcp_server.context import FrameHolder, ProposalBook, SnapshotFrame
from plant_monitor.runner.bridge import run_in_frame
from plant_monitor.runner.judgment import SnapshotWriter
from plant_monitor.runner.pipeline import SnapshotDecision

PerspectiveBuilder = Callable[[SnapshotDecision, Sequence[str]], tuple[CasePerspective, ...]]


@dataclass(frozen=True)
class CoordinatorOutcome:
    """How the coordinator loop ended and which proposals it applied or left."""

    outcome: LoopOutcome
    applied: tuple[str, ...]
    declined: tuple[str, ...]


class DecisionView:
    """What the hooks may know of the snapshot, read from the writer's decision (structural, R1)."""

    def __init__(self, writer: SnapshotWriter) -> None:
        self._writer = writer

    def alerts(self) -> tuple[Notice, ...]:
        """The alert notices code decided."""
        return tuple(n for n in self._writer.final().notices.decisions if n.tipo is NoticeType.ALERT)

    def news(self) -> tuple[Notice, ...]:
        """The shift report's news, or none."""
        report = self._writer.final().notices.report
        return () if report is None else tuple(report.novedades)

    def floors(self) -> Mapping[str, Severity]:
        """Computed minimum severity per case id."""
        delta = self._writer.final().delta
        return {} if delta is None else {c.case_id: c.minimum_severity for c in delta.cases}

    def missing(self) -> tuple[str, ...]:
        """Notice ids still without a text."""
        return self._writer.missing()


class _ProposalGate:
    """Loop progress that hides 'required' while proposals are unapplied, so no early stop (Q-53)."""

    def __init__(self, writer: SnapshotWriter, book: ProposalBook) -> None:
        self._writer = writer
        self._book = book

    def required(self) -> tuple[str, ...]:
        """Empty while the book holds unapplied proposals, else the writer's own."""
        return () if self._book.declined() else self._writer.required()

    def missing(self) -> tuple[str, ...]:
        """The writer's real missing ids."""
        return self._writer.missing()


class CoordinatorStep:
    """Runs the single writer over the notices code decided, with the validated proposals as data."""

    def __init__(
        self, coordinator: Coordinator, frames: FrameHolder, perspectives: PerspectiveBuilder
    ) -> None:
        self._coordinator = coordinator
        self._frames = frames
        self._perspectives = perspectives

    def run(
        self,
        decision: SnapshotDecision,
        writer: SnapshotWriter,
        accepted: Sequence[ValidatedProposal],
        log: LoopLog,
        on_start: Callable[[], None] | None = None,
    ) -> CoordinatorOutcome:
        """Run the loop in a frame carrying 'writer' and the proposal book; 'on_start' fires before it."""
        snapshot = decision.snapshot
        notices = decision.notices
        alerts = [n for n in notices.decisions if n.tipo is NoticeType.ALERT]
        news = notices.report.novedades if notices.report is not None else ()
        brief = render_brief(
            snapshot.snapshot_id,
            decision.shift.turno_id,
            decision.position,
            alerts,
            news,
            decision.in_force,
            self._perspectives(decision, writer.required()),
            accepted,
        )
        book = ProposalBook(accepted)
        frame = SnapshotFrame.with_writer(
            snapshot.snapshot_id, snapshot.timestamp, decision.metrics, snapshot.unidades, writer, book
        )
        if on_start is not None:
            on_start()
        progress = _ProposalGate(writer, book)
        outcome = run_in_frame(
            self._frames,
            frame,
            partial(self._coordinator.run, view=DecisionView(writer)),
            snapshot.snapshot_id,
            brief,
            progress,
            log,
        )
        return CoordinatorOutcome(outcome, book.applied(), book.declined())
