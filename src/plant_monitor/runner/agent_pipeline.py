"""Agent snapshot pipeline: the coordinator writes the notice texts inside the unit of work (R1, R10-R12)."""

from contextlib import AbstractAsyncContextManager
from typing import Literal, Protocol

import anyio

from plant_monitor.agents.brief import render_brief
from plant_monitor.agents.factory import COORDINATOR_TOOLS, build_coordinator
from plant_monitor.agents.loop import Coordinator, LoopLog, LoopOutcome, ToolPort
from plant_monitor.agents.model import ModelPort
from plant_monitor.cases.ledger import CauseLedger
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import Settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.models import Shift, Snapshot
from plant_monitor.domain.notices import NoticeType
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.context import FrameHolder, SnapshotFrame, ToolContext
from plant_monitor.mcp_server.server import build_server
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.runner.judgment import JudgmentFactory, SnapshotWriter, judgment_factory
from plant_monitor.runner.pipeline import SnapshotDecision, ThresholdPipeline
from plant_monitor.telemetry.trace import DecisionReason, TraceLine, TraceWriter, abort_outcome, build_line
from plant_monitor.telemetry.usage import PriceCard

REPORT_ID_SUFFIX = "informe"
NO_TEXT_REASON: DecisionReason = "no_text_needed"


class OpenUnit(Protocol):
    """The id of the snapshot whose unit of work is open, or None."""

    def current_snapshot(self) -> str | None: ...


class NoticeSteps(Protocol):
    """The deterministic steps around the texts; 'ThresholdPipeline' satisfies it."""

    def decide(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> SnapshotDecision: ...

    def redecide(self, decision: SnapshotDecision) -> SnapshotDecision: ...

    def finish(self, decision: SnapshotDecision) -> None: ...


def _kind(reason: DecisionReason | None) -> Literal["call", "skip"]:
    """The trace's 'decision' for a reason: only 'text_needed' and 'closing_review' call the model."""
    return "skip" if reason is None or reason == NO_TEXT_REASON else "call"


def _single_leaf(error: BaseExceptionGroup[BaseException]) -> BaseException:
    """Descend through groups holding exactly one exception; other groups stay as they are."""
    current: BaseException = error
    while isinstance(current, BaseExceptionGroup) and len(current.exceptions) == 1:
        current = current.exceptions[0]
    return current


def _reason(writer: SnapshotWriter, decision: SnapshotDecision) -> DecisionReason:
    """Why the model is called, or 'no_text_needed' when it is not (R14)."""
    if writer.required():
        return "text_needed"
    if decision.position is ShiftPosition.CLOSING:
        return "closing_review"
    return "no_text_needed"


class AgentPipeline:
    """SnapshotPipeline that has the coordinator judge causes and write the texts code decided."""

    def __init__(
        self,
        steps: NoticeSteps,
        unit: OpenUnit,
        frames: FrameHolder,
        coordinator: Coordinator,
        trace: TraceWriter,
        prices: PriceCard,
        judgment: JudgmentFactory,
    ) -> None:
        self._steps = steps
        self._unit = unit
        self._frames = frames
        self._coordinator = coordinator
        self._trace = trace
        self._prices = prices
        self._judgment = judgment

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        """Database writes only; the trace line is staged for the post-commit step (X2)."""
        log = LoopLog()
        writer: SnapshotWriter | None = None
        reason: DecisionReason | None = None
        try:
            decision = self._steps.decide(snapshot, shift, position)
            writer = self._judgment(decision)
            reason = _reason(writer, decision)
            if reason == NO_TEXT_REASON:
                final = writer.final()
                self._steps.finish(final)
                log.outcome = LoopOutcome.SKIPPED
                self._stage(final, writer, log, reason)
                return
            self._check_unit(snapshot.snapshot_id)
            self._converse(decision, writer, log)
            failure = writer.failure()
            if failure is not None:
                raise failure
            final = writer.final()
            self._steps.finish(final)
            self._stage(final, writer, log, reason)
        except Exception as error:
            self._trace.write_now(self._aborted(snapshot, shift, error, log, writer, reason))
            raise

    def _check_unit(self, snapshot_id: str) -> None:
        current = self._unit.current_snapshot()
        if current is None:
            raise ValueError(f"no unit of work is open for snapshot {snapshot_id}")
        if current != snapshot_id:
            raise ValueError(f"snapshot {snapshot_id} is processed but the open unit is {current}")

    def _converse(self, decision: SnapshotDecision, writer: SnapshotWriter, log: LoopLog) -> None:
        """Run the loop in the frame; single-exception groups unwrap to the leaf or inner group (X5)."""
        snapshot = decision.snapshot
        notices = decision.notices
        alerts = [n for n in notices.decisions if n.tipo is NoticeType.ALERT]
        news = notices.report.novedades if notices.report is not None else ()
        brief = render_brief(
            snapshot.snapshot_id, decision.shift.turno_id, decision.position, alerts, news, decision.in_force
        )
        frame = SnapshotFrame.with_writer(
            snapshot.snapshot_id, snapshot.timestamp, decision.metrics, snapshot.unidades, writer
        )
        try:
            with self._frames.entered(frame):
                anyio.run(self._coordinator.run, snapshot.snapshot_id, brief, writer, log)
        except BaseExceptionGroup as group:
            leaf = _single_leaf(group)
            if leaf is group:
                raise
            raise leaf from None

    def _stage(
        self, final: SnapshotDecision, writer: SnapshotWriter, log: LoopLog, reason: DecisionReason
    ) -> None:
        written = set(writer.written())
        report = final.notices.report
        line = build_line(
            snapshot_id=final.snapshot.snapshot_id,
            turno_id=final.shift.turno_id,
            status="committed",
            decision=_kind(reason),
            decision_reason=reason,
            outcome=log.outcome.value if log.outcome is not None else LoopOutcome.SKIPPED.value,
            required=writer.required(),
            model_calls=log.model_calls,
            tool_calls=log.tool_calls,
            thinking=log.thinking,
            notices_agent=writer.written(),
            notices_template=[n.notice_id for n in final.notices.decisions if n.notice_id not in written],
            report_id=None if report is None else f"{report.turno_id}-{REPORT_ID_SUFFIX}",
            card=self._prices,
        )
        self._trace.stage(line)

    def _aborted(
        self,
        snapshot: Snapshot,
        shift: Shift,
        error: BaseException,
        log: LoopLog,
        writer: SnapshotWriter | None,
        reason: DecisionReason | None,
    ) -> TraceLine:
        return build_line(
            snapshot_id=snapshot.snapshot_id,
            turno_id=shift.turno_id,
            status="aborted",
            decision=_kind(reason),
            decision_reason=reason,
            outcome=abort_outcome(error),
            required=() if writer is None else writer.required(),
            model_calls=log.model_calls,
            tool_calls=log.tool_calls,
            thinking=log.thinking,
            notices_agent=[],
            notices_template=[],
            report_id=None,
            card=self._prices,
        )


def build_agent_pipeline(
    settings: Settings,
    registry: SqliteRegistry,
    ctx: PlantContext,
    policy: HeldOutPolicy,
    model: ModelPort,
    trace: TraceWriter,
) -> AgentPipeline:
    """Composition root of the agent run: steps, tool server, coordinator and prices."""
    frames = FrameHolder()
    tool_ctx = ToolContext(
        plant=ctx,
        cases=registry.cases,
        logbooks=LogbookStore(settings.logbooks_dir, ctx.shifts, policy),
        view_max_chars=settings.tool_output_max_chars,
        logbook_max_chars=settings.logbook_max_chars,
    )
    server = build_server(tool_ctx, frames, tools=COORDINATOR_TOOLS)

    def tools() -> AbstractAsyncContextManager[ToolPort]:
        return ToolClient(server)

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
    return AgentPipeline(
        steps=steps,
        unit=registry,
        frames=frames,
        coordinator=build_coordinator(settings, model, tools),
        trace=trace,
        prices=prices,
        judgment=judgment_factory(steps, ledger, settings.notice_text_max_chars),
    )
