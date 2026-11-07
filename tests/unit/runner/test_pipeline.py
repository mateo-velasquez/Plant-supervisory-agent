"""004 T11: 'ThresholdPipeline' over one shift without the runner, plus its closing glue (E40)."""

from collections.abc import Iterable, Iterator

import pytest

from plant_monitor.cases.notice_builder import ShiftClose
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.cases import Case, CaseHistoryRow
from plant_monitor.domain.enums import Severity, ShiftPosition, Stage
from plant_monitor.domain.models import Snapshot, SnapshotCommit
from plant_monitor.domain.notices import Notice, NoticeType, ShiftReport
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.runner.pipeline import ThresholdPipeline, deviation_rows, shift_close

from builders import history_row
from notice_builders import plant_context, plant_shifts, series_snapshot

SEL = "S001-Sedán-Local"
SUV = "S002-SUV-Local"
PL = "S001-Pickup-Local"
PB = "S001-Pickup-Brasil"


class FakeReader:
    """'NoticeCaseReader' over fixed deviation rows; nothing is resolved-unreported."""

    def __init__(self, rows: Iterable[CaseHistoryRow]) -> None:
        self.rows = {row.case_id: row for row in rows}

    def resolved_unreported(self) -> tuple[Case, ...]:
        return ()

    def last_deviation_row(self, case_id: str) -> CaseHistoryRow | None:
        return self.rows.get(case_id)


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


@pytest.fixture
def ctx() -> PlantContext:
    """Plant context from the fixture CSVs."""
    return plant_context()


def process(registry: SqliteRegistry, pipeline: ThresholdPipeline, snapshot_id: str) -> None:
    """Run one series snapshot through the pipeline inside the registry's unit of work."""
    shift, position = snapshot_position(plant_shifts(), snapshot_id)
    snapshot = Snapshot.model_validate(series_snapshot(snapshot_id))
    commit = SnapshotCommit(snapshot_id, f"hash-{snapshot_id}", (), {})
    with registry.processing(commit):
        pipeline.process(snapshot, shift, position)


def stored_report(registry: SqliteRegistry, snapshot_id: str) -> ShiftReport:
    """The report saved for 'snapshot_id', the last item of its stored set."""
    report = registry.notices.for_snapshot(snapshot_id)[-1]
    assert isinstance(report, ShiftReport)
    return report


def test_e40_mid_snapshot_stores_three_undeliverable_informes_and_marks_nothing(
    registry: SqliteRegistry, ctx: PlantContext
) -> None:
    pipeline = ThresholdPipeline.from_registry(registry, ctx)
    process(registry, pipeline, "S001")
    stored = [n for n in registry.notices.for_snapshot("S001") if isinstance(n, Notice)]
    assert len(stored) == 3
    assert [(n.notice_id, n.tipo) for n in stored] == [
        (f"S001-informe_de_turno-{case_id}", NoticeType.SHIFT_REPORT) for case_id in (SEL, PL, PB)
    ]
    assert registry.notices.pending() == ()
    cases = registry.cases.active_cases()
    assert len(cases) == 3
    assert all(case.last_reported_at is None for case in cases)


def test_e40_closing_snapshot_stores_the_pending_report_and_marks_the_report_set(
    registry: SqliteRegistry, ctx: PlantContext
) -> None:
    pipeline = ThresholdPipeline.from_registry(registry, ctx)
    process(registry, pipeline, "S001")
    process(registry, pipeline, "S002")
    report = stored_report(registry, "S002")
    assert (report.turno_id, report.snapshot_id) == ("T01", "S002")
    assert [(n.case_id, n.severidad_maxima) for n in report.novedades] == [
        (SEL, Severity.HIGH),
        (SUV, Severity.HIGH),
        (PL, Severity.MEDIUM),
        (PB, Severity.MEDIUM),
    ]
    (delivery,) = registry.notices.pending()
    assert (delivery.notice_id, delivery.item) == ("T01-informe", report)
    for case_id in (SEL, SUV, PL, PB):
        case = registry.cases.get_case(case_id)
        assert case is not None
        assert case.last_reported_at == "S002"
        assert case.max_severity_since_report is None


def test_e40_pipeline_holds_no_notifier(registry: SqliteRegistry, ctx: PlantContext) -> None:
    """Delivery belongs to the post-commit dispatcher; a notifier in the pipeline could send before commit."""
    pipeline = ThresholdPipeline.from_registry(registry, ctx)
    held = vars(pipeline).values()
    assert not any(hasattr(part, "alert") or hasattr(part, "report") for part in held)


def test_e40_shift_close_is_none_at_mid_and_empty_at_closing_after_s001(
    registry: SqliteRegistry, ctx: PlantContext
) -> None:
    process(registry, ThresholdPipeline.from_registry(registry, ctx), "S001")
    t01 = plant_shifts()[0]
    assert shift_close(t01, ShiftPosition.MID, registry.cases) is None
    assert shift_close(t01, ShiftPosition.CLOSING, registry.cases) == ShiftClose("T01", ())


def test_deviation_rows_reads_each_case_once_even_when_ids_repeat() -> None:
    """A case resolved at the closing snapshot is in both the delta and the raw resolved-unreported list."""
    reader = FakeReader([history_row(SEL, "S001", None), history_row(PB, "S001", Stage.ASSEMBLY)])
    rows = deviation_rows([SEL, PB, SEL], reader)
    assert set(rows) == {SEL, PB}
    assert rows[PB].bottleneck is Stage.ASSEMBLY


def test_deviation_rows_raises_naming_a_case_without_a_deviation_row() -> None:
    reader = FakeReader([history_row(SEL, "S001", None)])
    with pytest.raises(ValueError, match=PB):
        deviation_rows([SEL, PB], reader)
