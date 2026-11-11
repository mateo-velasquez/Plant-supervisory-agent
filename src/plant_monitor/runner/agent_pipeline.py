"""Agent snapshot pipeline: investigator, then coordinator, inside the unit of work (009 R1, R9, R12)."""

from collections.abc import Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from functools import partial
from typing import Literal, Protocol

from plant_monitor.agents.factory import (
    COORDINATOR_TOOLS,
    INVESTIGATOR_TOOLS,
    build_coordinator,
    build_investigator,
)
from plant_monitor.agents.investigator import ReviewLog
from plant_monitor.agents.loop import LoopLog, ToolPort
from plant_monitor.agents.model import ModelPort
from plant_monitor.cases.ledger import CauseLedger
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.reviews import ReviewMark
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Shift, Snapshot
from plant_monitor.domain.perspectives import CasePerspective
from plant_monitor.domain.proposals import ValidatedProposal
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import FrameHolder, ToolContext
from plant_monitor.mcp_server.server import build_server
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.runner.coordinator_step import CoordinatorOutcome, CoordinatorStep
from plant_monitor.runner.judgment import JudgmentFactory, SnapshotWriter, judgment_factory
from plant_monitor.runner.perspectives import case_perspectives
from plant_monitor.runner.pipeline import SnapshotDecision, ThresholdPipeline
from plant_monitor.runner.review_step import InvestigatorStep, LogbookReviewStep, ReviewOutcome, ReviewPlan
from plant_monitor.telemetry.trace import (
    DecisionReason,
    InvestigatorRecord,
    TraceLine,
    TraceWriter,
    abort_outcome,
    build_line,
)
from plant_monitor.telemetry.usage import PriceCard

REPORT_ID_SUFFIX = "informe"
NO_TEXT_REASON: DecisionReason = "no_text_needed"
COORDINATOR_REASONS: tuple[DecisionReason, ...] = ("text_needed", "proposals")
SKIPPED_INVESTIGATOR = "skipped"


class OpenUnit(Protocol):
    """The id of the snapshot whose unit of work is open, or None."""

    def current_snapshot(self) -> str | None: ...


class NoticeSteps(Protocol):
    """The deterministic steps around the texts; 'ThresholdPipeline' satisfies it."""

    def decide(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> SnapshotDecision: ...

    def redecide(self, decision: SnapshotDecision) -> SnapshotDecision: ...

    def finish(self, decision: SnapshotDecision) -> None: ...


def _kind(reason: DecisionReason | None) -> Literal["call", "skip"]:
    """The trace's 'decision' for a reason: every reason but 'no_text_needed' calls an agent."""
    return "skip" if reason is None or reason == NO_TEXT_REASON else "call"


def _reason(writer: SnapshotWriter, plan: ReviewPlan) -> DecisionReason:
    """Why an agent is called before the investigator ran, or 'no_text_needed' when none is (R9)."""
    if writer.required():
        return "text_needed"
    if plan.present:
        return "investigator_only"
    return NO_TEXT_REASON


@dataclass
class _Run:
    """What one snapshot has done so far, so an aborted line keeps the partial records."""

    writer: SnapshotWriter | None = None
    reason: DecisionReason | None = None
    plan: ReviewPlan | None = None
    review: ReviewOutcome | None = None
    in_investigator: bool = False
    agents_run: list[str] = field(default_factory=list)
    inv_log: LoopLog = field(default_factory=LoopLog)
    review_log: ReviewLog = field(default_factory=ReviewLog)
    log: LoopLog = field(default_factory=LoopLog)
    coordinator: CoordinatorOutcome | None = None
    marks: dict[str, ReviewMark] = field(default_factory=dict)


class AgentPipeline:
    """SnapshotPipeline: the investigator reads logbooks, the coordinator writes what code decided."""

    def __init__(
        self,
        steps: NoticeSteps,
        unit: OpenUnit,
        frames: FrameHolder,
        trace: TraceWriter,
        prices: PriceCard,
        judgment: JudgmentFactory,
        review: LogbookReviewStep,
        coordinator: CoordinatorStep,
    ) -> None:
        self._steps = steps
        self._unit = unit
        self._frames = frames
        self._trace = trace
        self._prices = prices
        self._judgment = judgment
        self._review = review
        self._coordinator = coordinator

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        """Database writes only; the trace line is staged for the post-commit step (X2)."""
        run = _Run()
        try:
            self._sequence(run, snapshot, shift, position)
        except Exception as error:
            self._trace.write_now(self._aborted(snapshot, shift, error, run))
            raise

    def _sequence(self, run: _Run, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        decision = self._steps.decide(snapshot, shift, position)
        writer = self._judgment(decision)
        run.writer = writer
        plan = self._review.plan(decision)
        run.plan = plan
        run.reason = _reason(writer, plan)
        if run.reason != NO_TEXT_REASON:
            self._check_unit(snapshot.snapshot_id)
        outcome = ReviewOutcome(plan, False, None, ())
        if plan.present or plan.lookup:
            run.in_investigator = True
            run.agents_run.append("investigator")
            outcome = self._review.run(plan, decision, run.inv_log, run.review_log)
            run.in_investigator = False
        run.review = outcome
        if run.reason != "text_needed" and outcome.accepted:
            run.reason = "proposals"
        if run.reason in COORDINATOR_REASONS:
            run.coordinator = self._coordinator.run(
                decision, writer, outcome.accepted, run.log, lambda: run.agents_run.append("coordinator")
            )
        failure = writer.failure()
        if failure is not None:
            raise failure
        if plan.pending:
            coordinated = None if run.coordinator is None else run.coordinator.outcome
            applied = () if run.coordinator is None else run.coordinator.applied
            run.marks = dict(self._review.record(outcome, coordinated, snapshot.snapshot_id, applied))
        final = writer.final()
        self._steps.finish(final)
        self._stage(final, run)

    def _check_unit(self, snapshot_id: str) -> None:
        current = self._unit.current_snapshot()
        if current is None:
            raise ValueError(f"no unit of work is open for snapshot {snapshot_id}")
        if current != snapshot_id:
            raise ValueError(f"snapshot {snapshot_id} is processed but the open unit is {current}")

    def _investigator(self, run: _Run, error: BaseException | None) -> InvestigatorRecord | None:
        """The investigator's entry: none when no logbook was pending and no cause lookup ran."""
        plan = run.plan
        if plan is None or not (plan.pending or plan.lookup):
            return None
        review = run.review
        accepted: Sequence[ValidatedProposal] = (
            review.accepted if review is not None else (run.review_log.accepted or ())
        )
        if error is not None and run.in_investigator:
            outcome = abort_outcome(error)
        elif review is None or not review.ran or review.outcome is None:
            outcome = SKIPPED_INVESTIGATOR
        else:
            outcome = review.outcome.value
        return InvestigatorRecord(
            outcome=outcome,
            logbooks=plan.present,
            missing=plan.missing,
            marks={} if error is not None else {turno: mark.value for turno, mark in run.marks.items()},
            proposals=[p.item() for p in accepted],
            control_errors=run.review_log.rejections,
            model_calls=run.inv_log.model_calls,
            tool_calls=run.inv_log.tool_calls,
            thinking=run.inv_log.thinking,
            trigger="cause_lookup" if plan.lookup else "review",
        )

    def _stage(self, final: SnapshotDecision, run: _Run) -> None:
        writer = run.writer
        reason = run.reason
        assert writer is not None
        assert reason is not None
        written = set(writer.written())
        report = final.notices.report
        coordinator = run.coordinator
        log = run.log
        line = build_line(
            snapshot_id=final.snapshot.snapshot_id,
            turno_id=final.shift.turno_id,
            status="committed",
            decision=_kind(reason),
            decision_reason=reason,
            outcome=log.outcome.value if coordinator is not None and log.outcome is not None else "skipped",
            required=writer.required(),
            model_calls=log.model_calls,
            tool_calls=log.tool_calls,
            thinking=log.thinking,
            notices_agent=writer.written(),
            notices_template=[n.notice_id for n in final.notices.decisions if n.notice_id not in written],
            report_id=None if report is None else f"{report.turno_id}-{REPORT_ID_SUFFIX}",
            card=self._prices,
            agents_run=run.agents_run,
            investigator=self._investigator(run, None),
            proposals_applied=() if coordinator is None else coordinator.applied,
            proposals_declined=() if coordinator is None else coordinator.declined,
        )
        self._trace.stage(line)

    def _aborted(self, snapshot: Snapshot, shift: Shift, error: BaseException, run: _Run) -> TraceLine:
        writer = run.writer
        return build_line(
            snapshot_id=snapshot.snapshot_id,
            turno_id=shift.turno_id,
            status="aborted",
            decision=_kind(run.reason),
            decision_reason=run.reason,
            outcome="skipped" if run.in_investigator else abort_outcome(error),
            required=() if writer is None else writer.required(),
            model_calls=run.log.model_calls,
            tool_calls=run.log.tool_calls,
            thinking=run.log.thinking,
            notices_agent=[],
            notices_template=[],
            report_id=None,
            card=self._prices,
            agents_run=run.agents_run,
            investigator=self._investigator(run, error),
        )


def build_agent_pipeline(
    settings: Settings,
    registry: SqliteRegistry,
    ctx: PlantContext,
    policy: HeldOutPolicy,
    model: ModelPort,
    trace: TraceWriter,
) -> AgentPipeline:
    """Composition root of the agent run: steps, two tool servers, both agents and prices."""
    frames = FrameHolder()
    logbooks = LogbookStore(settings.logbooks_dir, ctx.shifts, policy)
    tool_ctx = ToolContext(
        plant=ctx,
        cases=registry.cases,
        logbooks=logbooks,
        view_max_chars=settings.tool_output_max_chars,
        logbook_max_chars=settings.logbook_max_chars,
    )
    investigator_server = build_server(tool_ctx, frames, tools=INVESTIGATOR_TOOLS)
    coordinator_server = build_server(tool_ctx, frames, tools=COORDINATOR_TOOLS)

    def investigator_tools() -> AbstractAsyncContextManager[ToolPort]:
        return ToolClient(investigator_server)

    def coordinator_tools() -> AbstractAsyncContextManager[ToolPort]:
        return ToolClient(coordinator_server)

    prices = PriceCard(
        input=settings.price_input_per_mtok,
        cache_write_5m=settings.price_cache_write_5m_per_mtok,
        cache_write_1h=settings.price_cache_write_1h_per_mtok,
        cache_read=settings.price_cache_read_per_mtok,
        output=settings.price_output_per_mtok,
        long_context_threshold=settings.long_context_threshold_tokens,
        long_context_multiplier=settings.long_context_multiplier,
    )
    ledger = CauseLedger(registry.causes, registry.cases, ctx.shifts)
    steps = ThresholdPipeline.from_registry(registry, ctx, ledger)
    review = InvestigatorStep(
        build_investigator(settings, model, investigator_tools),
        frames,
        logbooks,
        registry.reviews,
        settings.logbook_review_max_attempts,
        settings.proposal_output_max_chars,
    )
    coordinator = CoordinatorStep(
        build_coordinator(settings, model, coordinator_tools),
        frames,
        partial(_perspectives, registry, ctx),
    )
    return AgentPipeline(
        steps=steps,
        unit=registry,
        frames=frames,
        trace=trace,
        prices=prices,
        judgment=judgment_factory(steps, ledger, settings.notice_text_max_chars),
        review=review,
        coordinator=coordinator,
    )


def _perspectives(
    registry: SqliteRegistry, ctx: PlantContext, decision: SnapshotDecision, required: Sequence[str]
) -> tuple[CasePerspective, ...]:
    return case_perspectives(decision, required, registry.cases, ctx)
