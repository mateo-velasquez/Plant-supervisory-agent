"""008 T9: 'SnapshotJudgment' re-decides and rebases after a judgment write (E17, R10 guard, X4)."""

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import cast

import pytest
from draft_builders import MAX_CHARS
from incident_builders import incident_context, incident_scenario
from incident_runs import EV_T05, IncidentRun

from plant_monitor.cases.ledger import CauseLedger, UnknownActiveCause
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Stage
from plant_monitor.domain.notices import Notice, NoticeType, ShiftReport
from plant_monitor.mcp_server.context import JudgmentResult
from plant_monitor.runner.judgment import SnapshotJudgment, WritesClosed, judgment_factory
from plant_monitor.runner.pipeline import NoticeSink, SnapshotDecision, ThresholdPipeline

PL_CASE = "S010-Pickup-Local"
PB_CASE = "S010-Pickup-Brasil"
LINE_STOP = Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY)
PL_NEWS = f"S010-informe_de_turno-{PL_CASE}"
PB_NEWS = f"S010-informe_de_turno-{PB_CASE}"
CLOSED = "writes are closed at S010 after an internal error"


class SpySink:
    """Notice sink that records each 'save' and forwards it."""

    def __init__(self, inner: NoticeSink) -> None:
        self.inner = inner
        self.saved: list[str] = []

    def save(self, snapshot_id: str, decisions: Sequence[Notice], report: ShiftReport | None) -> None:
        """Record the snapshot id and forward."""
        self.saved.append(snapshot_id)
        self.inner.save(snapshot_id, decisions, report)


class CountingSteps:
    """Real steps that count 'redecide' calls."""

    def __init__(self, pipeline: ThresholdPipeline) -> None:
        self.pipeline = pipeline
        self.redecides = 0

    def redecide(self, decision: SnapshotDecision) -> SnapshotDecision:
        """Count, then delegate."""
        self.redecides += 1
        return self.pipeline.redecide(decision)


class FailingLedger:
    """A ledger stub whose 'set_cause' raises the given error."""

    def __init__(self, error: Exception) -> None:
        self.error = error

    def set_cause(self, *args: object) -> None:
        """Raise the configured error."""
        raise self.error


@contextmanager
def at_s010() -> Iterator[tuple[IncidentRun, CountingSteps, SpySink]]:
    """IF run through S009 with a spied notice sink and counted re-decides, ready to step S010."""
    ctx = incident_context()
    with SqliteRegistry(":memory:") as registry:
        ledger = CauseLedger(registry.causes, registry.cases, ctx.shifts)
        sink = SpySink(registry.notices)
        pipeline = ThresholdPipeline(ctx, registry.releases, registry.cases, registry.cases, sink, ledger)
        run = IncidentRun(registry, ledger, pipeline, incident_scenario())
        run.through(9)
        yield run, CountingSteps(pipeline), sink


def news_of(decision: SnapshotDecision, case_id: str) -> Notice:
    """The news notice of 'case_id' in the decision's report."""
    assert decision.notices.report is not None
    (notice,) = [n for n in decision.notices.report.novedades if n.case_id == case_id]
    return notice


def test_e17_a_set_cause_redecides_once_rebuilds_the_news_and_saves_only_at_finish() -> None:
    with at_s010() as (run, steps, sink):
        seen: dict[str, object] = {}

        def act(decision: SnapshotDecision) -> SnapshotDecision:
            writer = judgment_factory(steps, run.ledger, MAX_CHARS)(decision)
            baseline = len(sink.saved)
            seen["result"] = writer.set_cause(PL_CASE, LINE_STOP, EV_T05)
            seen["saves_before_finish"] = len(sink.saved) - baseline
            seen["required"] = writer.required()
            seen["missing"] = writer.missing()
            final = writer.final()
            seen["final"] = final
            return final

        run.step(10, act)

        final = seen["final"]
        assert isinstance(final, SnapshotDecision)
        news = news_of(final, PL_CASE)
        assert news.tipo is NoticeType.SHIFT_REPORT
        assert news.causa == LINE_STOP
        assert news.evidencia == (EV_T05,)
        assert news.texto.endswith("Causa: parada de línea, etapa montaje (bitácora T05).")
        result = seen["result"]
        assert isinstance(result, JudgmentResult)
        assert result.case_ids == (PL_CASE,)
        assert result.changed == (news,)
        assert result.pending == (PL_NEWS, PB_NEWS)
        assert (seen["required"], seen["missing"]) == ((PL_NEWS, PB_NEWS), (PL_NEWS, PB_NEWS))
        assert steps.redecides == 1
        assert len([r for r in run.registry.cases.history(PL_CASE) if r.snapshot_id == "S010"]) == 1
        assert seen["saves_before_finish"] == 0
        assert sink.saved[-1] == "S010"
        assert len(sink.saved) == 10


def test_x4_an_internal_error_is_stored_reraised_and_closes_every_later_write() -> None:
    error = sqlite3.IntegrityError("boom")
    with at_s010() as (run, steps, _sink):

        def act(decision: SnapshotDecision) -> SnapshotDecision:
            writer = SnapshotJudgment(steps, decision, cast(CauseLedger, FailingLedger(error)), MAX_CHARS)
            with pytest.raises(sqlite3.IntegrityError) as raised:
                writer.set_cause(PL_CASE, LINE_STOP, EV_T05)
            assert raised.value is error
            assert writer.failure() is error
            with pytest.raises(WritesClosed, match=CLOSED):
                writer.set_cause(PL_CASE, LINE_STOP, EV_T05)
            with pytest.raises(WritesClosed, match=CLOSED):
                writer.write_alert(PL_CASE, "x")
            with pytest.raises(WritesClosed, match=CLOSED):
                writer.write_news([(PL_CASE, "x"), (PB_CASE, "y")])
            assert writer.failure() is error
            assert steps.redecides == 0
            return decision

        run.step(10, act)


def test_risk_a_refusal_propagates_without_being_stored_as_a_failure() -> None:
    """Risk: storing a refusal as an internal error would abort the run for a model mistake."""
    with at_s010() as (run, steps, _sink):

        def act(decision: SnapshotDecision) -> SnapshotDecision:
            ledger = cast(CauseLedger, FailingLedger(UnknownActiveCause("S099-causa-1")))
            writer = SnapshotJudgment(steps, decision, ledger, MAX_CHARS)
            with pytest.raises(UnknownActiveCause):
                writer.set_cause(PL_CASE, LINE_STOP, EV_T05)
            assert writer.failure() is None
            return decision

        run.step(10, act)
