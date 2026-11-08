"""Agent snapshot pipeline: the coordinator writes the notice texts inside the unit of work (R1, R10-R12)."""

from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from typing import Protocol

import anyio

from plant_monitor.agents.brief import render_brief
from plant_monitor.agents.factory import COORDINATOR_TOOLS, build_coordinator
from plant_monitor.agents.loop import Coordinator, LoopLog, LoopOutcome, ToolPort
from plant_monitor.agents.model import ModelPort
from plant_monitor.cases.draft import NoticeDraft
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
from plant_monitor.runner.pipeline import SnapshotDecision, ThresholdPipeline
from plant_monitor.telemetry.trace import TraceLine, TraceWriter, abort_outcome, build_line
from plant_monitor.telemetry.usage import PriceCard

REPORT_ID_SUFFIX = "informe"


class OpenUnit(Protocol):
    """The id of the snapshot whose unit of work is open, or None."""

    def current_snapshot(self) -> str | None: ...


class NoticeSteps(Protocol):
    """The deterministic steps around the texts; 'ThresholdPipeline' satisfies it."""

    def decide(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> SnapshotDecision: ...

    def finish(self, decision: SnapshotDecision) -> None: ...


def _single_leaf(error: BaseExceptionGroup[BaseException]) -> BaseException:
    """Descend through groups holding exactly one exception; other groups stay as they are."""
    current: BaseException = error
    while isinstance(current, BaseExceptionGroup) and len(current.exceptions) == 1:
        current = current.exceptions[0]
    return current


class AgentPipeline:
    """SnapshotPipeline that has the coordinator write the texts of the notices code decided."""

    def __init__(
        self,
        steps: NoticeSteps,
        unit: OpenUnit,
        frames: FrameHolder,
        coordinator: Coordinator,
        trace: TraceWriter,
        prices: PriceCard,
        max_chars: int,
    ) -> None:
        self._steps = steps
        self._unit = unit
        self._frames = frames
        self._coordinator = coordinator
        self._trace = trace
        self._prices = prices
        self._max_chars = max_chars

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        """Database writes only; the trace line is staged for the post-commit step (X2)."""
        log = LoopLog()
        required: tuple[str, ...] = ()
        try:
            decision = self._steps.decide(snapshot, shift, position)
            draft = NoticeDraft(decision.notices, self._max_chars)
            required = draft.required()
            if not required:
                self._steps.finish(replace(decision, notices=draft.build()))
                log.outcome = LoopOutcome.SKIPPED
                self._stage(decision, draft, log, "skip", required)
                return
            self._check_unit(snapshot.snapshot_id)
            self._converse(decision, draft, log)
            self._steps.finish(replace(decision, notices=draft.build()))
            self._stage(decision, draft, log, "call", required)
        except Exception as error:
            self._trace.write_now(self._aborted(snapshot, shift, error, log, required))
            raise

    def _check_unit(self, snapshot_id: str) -> None:
        current = self._unit.current_snapshot()
        if current is None:
            raise ValueError(f"no unit of work is open for snapshot {snapshot_id}")
        if current != snapshot_id:
            raise ValueError(f"snapshot {snapshot_id} is processed but the open unit is {current}")

    def _converse(self, decision: SnapshotDecision, draft: NoticeDraft, log: LoopLog) -> None:
        """Run the loop in the frame; single-exception groups unwrap to the leaf or inner group (X5)."""
        snapshot = decision.snapshot
        notices = decision.notices
        alerts = [n for n in notices.decisions if n.tipo is NoticeType.ALERT]
        news = notices.report.novedades if notices.report is not None else ()
        brief = render_brief(snapshot.snapshot_id, decision.shift.turno_id, decision.position, alerts, news)
        frame = SnapshotFrame(
            snapshot.snapshot_id, snapshot.timestamp, decision.metrics, snapshot.unidades, draft
        )
        try:
            with self._frames.entered(frame):
                anyio.run(self._coordinator.run, snapshot.snapshot_id, brief, draft, log)
        except BaseExceptionGroup as group:
            leaf = _single_leaf(group)
            if leaf is group:
                raise
            raise leaf from None

    def _stage(
        self,
        decision: SnapshotDecision,
        draft: NoticeDraft,
        log: LoopLog,
        kind: str,
        required: tuple[str, ...],
    ) -> None:
        written = set(draft.written())
        report = decision.notices.report
        line = build_line(
            snapshot_id=decision.snapshot.snapshot_id,
            turno_id=decision.shift.turno_id,
            status="committed",
            decision=kind,
            outcome=log.outcome.value if log.outcome is not None else LoopOutcome.SKIPPED.value,
            required=required,
            model_calls=log.model_calls,
            tool_calls=log.tool_calls,
            thinking=log.thinking,
            notices_agent=draft.written(),
            notices_template=[n.notice_id for n in decision.notices.decisions if n.notice_id not in written],
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
        required: tuple[str, ...],
    ) -> TraceLine:
        return build_line(
            snapshot_id=snapshot.snapshot_id,
            turno_id=shift.turno_id,
            status="aborted",
            decision="call" if required else "skip",
            outcome=abort_outcome(error),
            required=required,
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
    return AgentPipeline(
        steps=ThresholdPipeline.from_registry(registry, ctx),
        unit=registry,
        frames=frames,
        coordinator=build_coordinator(settings, model, tools),
        trace=trace,
        prices=prices,
        max_chars=settings.notice_text_max_chars,
    )
