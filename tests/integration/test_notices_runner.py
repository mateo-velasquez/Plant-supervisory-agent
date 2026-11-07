"""004 T12-T13: runner, registry, 'ThresholdPipeline' and outbox over two shifts, with faults (E41-E45)."""

import json
import logging
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import pytest

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, ShiftPosition, Stage
from plant_monitor.domain.models import Shift, Snapshot
from plant_monitor.domain.notices import (
    ActiveCaseRow,
    Notice,
    NoticeType,
    Origin,
    PendingDelivery,
    Reason,
    ShiftReport,
)
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.notify.composite import CompositeNotifier
from plant_monitor.notify.file import FileNotifier
from plant_monitor.notify.port import Notifier
from plant_monitor.runner.outbox import OutboxDispatcher, PendingNotices
from plant_monitor.runner.pipeline import NoticeSink, ThresholdPipeline
from plant_monitor.runner.ports import PostCommit, SnapshotPipeline
from plant_monitor.runner.series import RunAborted, RunSummary, run_series

from notice_builders import plant_context, plant_shifts, write_series

SERIES = ("S001", "S002", "S003", "S004")
LONG_SERIES = (*SERIES, "S005", "S006")
CLOCK_TIME = datetime(2026, 3, 2, 23, 0, tzinfo=UTC)

SEL = "S001-Sedán-Local"
SUV = "S002-SUV-Local"
PL = "S001-Pickup-Local"
PB = "S001-Pickup-Brasil"
PB_SECOND = "S005-Pickup-Brasil"
ALERT_ID = f"S003-alerta_inmediata-{SEL}"

E22D_TEXT = (
    "Sedán × Local escaló a crítica en S003 por gap: gap −18 u (−50 %), sin retraso. "  # noqa: RUF001
    "Causa no declarada: desvío solo por gap, sin etapa cuello identificada."
)
E22E_TEXT = (
    "Pickup × Brasil: caso nuevo. Estado abierto, severidad media, máxima media. "  # noqa: RUF001
    "Causa no declarada, etapa montaje."
)
E22F_TEXT = (
    "Pickup × Brasil: caso nuevo; pico de media. "  # noqa: RUF001
    "Estado en seguimiento, severidad ninguna, máxima media. Causa no declarada, etapa montaje."
)
E22G_TEXT = (
    "Sedán × Local: estado en seguimiento → escalado; severidad alta → crítica. "  # noqa: RUF001
    "Estado escalado, severidad crítica, máxima crítica. "
    "Causa no declarada: desvío solo por gap, sin etapa cuello identificada."
)
E22H_TEXT = (
    "Pickup × Local: pico de alta. Estado en seguimiento, severidad media, máxima alta. "  # noqa: RUF001
    "Causa no declarada: desvío solo por gap, sin etapa cuello identificada."
)
E22I_TEXT = (
    "Pickup × Brasil: resuelto en S003. Estado resuelto, severidad ninguna, máxima ninguna. "  # noqa: RUF001
    "Causa no declarada, etapa montaje."
)

type Call = tuple[str, str]
type ActiveView = tuple[str, float, float | None, Severity, Severity, CaseState, Stage | None]


class Row(NamedTuple):
    """A stored notice row without delivery metadata."""

    notice_id: str
    snapshot_id: str
    kind: str
    tipo: str
    case_id: str | None
    payload: str


class RecordingNotifier:
    """Records '(channel, id)' calls; can raise once on its first call, after recording it."""

    def __init__(
        self, *, first_call_error: BaseException | None = None, events: list[Call] | None = None
    ) -> None:
        self.calls: list[Call] = [] if events is None else events
        self._error = first_call_error

    def alert(self, notice: Notice) -> None:
        self._record(("alert", notice.notice_id))

    def report(self, report: ShiftReport) -> None:
        self._record(("report", report.turno_id))

    def _record(self, call: Call) -> None:
        self.calls.append(call)
        error, self._error = self._error, None
        if error is not None:
            raise error


class FailingSink:
    """'NoticeSink' that saves through the real store and then raises at one snapshot (E43)."""

    def __init__(self, inner: NoticeSink, fail_at: str) -> None:
        self._inner = inner
        self._fail_at = fail_at

    def save(self, snapshot_id: str, decisions: Sequence[Notice], report: ShiftReport | None) -> None:
        self._inner.save(snapshot_id, decisions, report)
        if snapshot_id == self._fail_at:
            raise RuntimeError("boom")


class MarkFailingStore:
    """'PendingNotices' whose 'mark_delivered' raises for one notice, after its send (E45)."""

    def __init__(self, inner: PendingNotices, fail_for: str, error: BaseException) -> None:
        self._inner = inner
        self._fail_for = fail_for
        self._error = error

    def pending(self) -> tuple[PendingDelivery, ...]:
        return self._inner.pending()

    def mark_delivered(self, notice_id: str, at: datetime) -> None:
        if notice_id == self._fail_for:
            raise self._error
        self._inner.mark_delivered(notice_id, at)


class TracingPipeline:
    """Appends '(process, snapshot_id)' to a shared event log, then delegates."""

    def __init__(self, inner: SnapshotPipeline, events: list[Call]) -> None:
        self._inner = inner
        self._events = events

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        self._events.append(("process", snapshot.snapshot_id))
        self._inner.process(snapshot, shift, position)


class CountingPostCommit:
    """Counts 'after_commit' calls, then delegates."""

    def __init__(self, inner: PostCommit) -> None:
        self._inner = inner
        self.count = 0

    def after_commit(self) -> None:
        self.count += 1
        self._inner.after_commit()


def run(
    path: Path,
    arrivals: Sequence[Arrival],
    notifier: Notifier,
    *,
    fail_save_at: str | None = None,
    mark_failure: BaseException | None = None,
    events: list[Call] | None = None,
    counter: list[CountingPostCommit] | None = None,
) -> RunSummary:
    """Run the series on 'path' with the production wiring and optional fault injection."""
    ctx = plant_context()
    with SqliteRegistry(path) as registry:
        if fail_save_at is None:
            pipeline: SnapshotPipeline = ThresholdPipeline.from_registry(registry, ctx)
        else:
            sink = FailingSink(registry.notices, fail_save_at)
            pipeline = ThresholdPipeline(ctx, registry.releases, registry.cases, registry.cases, sink)
        if events is not None:
            pipeline = TracingPipeline(pipeline, events)
        store: PendingNotices = registry.notices
        if mark_failure is not None:
            store = MarkFailingStore(registry.notices, "T01-informe", mark_failure)
        post_commit: PostCommit = OutboxDispatcher(store, notifier, lambda: CLOCK_TIME)
        if counter is not None:
            counting = CountingPostCommit(post_commit)
            counter.append(counting)
            post_commit = counting
        return run_series(arrivals, plant_shifts(), registry, pipeline, post_commit=post_commit)


def stored_rows(path: Path) -> list[Row]:
    """Every stored notice row of a closed registry file, in processing order."""
    query = "SELECT notice_id, snapshot_id, kind, tipo, case_id, payload FROM notices ORDER BY seq, idx"
    with closing(sqlite3.connect(path)) as conn:
        return [Row(*row) for row in conn.execute(query)]


def out_files(out: Path) -> dict[str, bytes]:
    """File name to bytes for everything in the output directory; empty when it does not exist."""
    return {p.name: p.read_bytes() for p in sorted(out.iterdir())} if out.exists() else {}


def snapshot_items(
    registry: SqliteRegistry, snapshot_id: str
) -> tuple[tuple[Notice, ...], ShiftReport | None]:
    """The stored per-case decisions of a snapshot and its report, if any."""
    items = registry.notices.for_snapshot(snapshot_id)
    reports = [item for item in items if isinstance(item, ShiftReport)]
    return tuple(item for item in items if isinstance(item, Notice)), (reports[0] if reports else None)


def active_view(row: ActiveCaseRow) -> ActiveView:
    """'casos_activos' row as a tuple, with the gap percentage rounded to one decimal."""
    pct = None if row.gap_pct is None else round(row.gap_pct, 1)
    return (
        row.case_id,
        row.gap_unidades,
        pct,
        row.severidad,
        row.severidad_maxima,
        row.estado,
        row.etapa_cuello,
    )


def pending_ids(path: Path) -> list[str]:
    """'notice_id' of every undelivered deliverable notice, read through a fresh registry."""
    with SqliteRegistry(path) as registry:
        return [item.notice_id for item in registry.notices.pending()]


@dataclass(frozen=True)
class Outcome:
    """Result of an uninterrupted run: its files, the notifier calls and the summary."""

    path: Path
    out: Path
    recorder: RecordingNotifier
    summary: RunSummary


@dataclass(frozen=True)
class Baseline:
    """Notice rows and output files of an uninterrupted run (E41)."""

    rows: list[Row]
    files: dict[str, bytes]


@pytest.fixture
def arrivals(tmp_path: Path) -> list[Arrival]:
    """E41 arrivals S001-S004 written under 'tmp_path'."""
    return write_series(tmp_path / "snapshots", SERIES)


@pytest.fixture
def e41(tmp_path: Path, arrivals: list[Arrival]) -> Outcome:
    """E41: the uninterrupted series with file and recording notifiers."""
    path = tmp_path / "registry.sqlite3"
    out = tmp_path / "out"
    recorder = RecordingNotifier()
    summary = run(path, arrivals, CompositeNotifier((FileNotifier(out), recorder)))
    return Outcome(path, out, recorder, summary)


@pytest.fixture
def baseline(tmp_path: Path, arrivals: list[Arrival]) -> Baseline:
    """An uninterrupted run on its own registry and output directory, for byte comparisons."""
    path = tmp_path / "baseline.sqlite3"
    out = tmp_path / "baseline_out"
    run(path, arrivals, CompositeNotifier((FileNotifier(out), RecordingNotifier())))
    return Baseline(stored_rows(path), out_files(out))


# --- T12 · E41 two shifts through the runner (NFR-04) ---


def test_e41_series_gives_the_spec_metrics_in_the_case_histories(e41: Outcome) -> None:
    assert e41.summary.processed == SERIES
    with SqliteRegistry(e41.path) as registry:
        history = registry.cases.history
        assert [(r.snapshot_id, r.gap_units, r.minimum_severity) for r in history(SEL)] == [
            ("S001", -6.0, Severity.MEDIUM),
            ("S002", -12.0, Severity.HIGH),
            ("S003", -18.0, Severity.CRITICAL),
            ("S004", -24.0, Severity.CRITICAL),
        ]
        assert [(r.snapshot_id, r.gap_units, r.minimum_severity) for r in history(SUV)] == [
            ("S002", -6.0, Severity.HIGH),
            ("S003", -6.0, Severity.HIGH),
            ("S004", -6.0, Severity.HIGH),
        ]
        assert [(r.snapshot_id, r.gap_units, r.minimum_severity) for r in history(PL)] == [
            ("S001", -4.0, Severity.MEDIUM),
            ("S002", -4.0, Severity.MEDIUM),
            ("S003", -7.0, Severity.HIGH),
            ("S004", -4.0, Severity.MEDIUM),
        ]
        pb_rows = history(PB)
        assert [(r.snapshot_id, r.gap_units, r.bottleneck, r.minimum_severity) for r in pb_rows[:2]] == [
            ("S001", -5.0, Stage.ASSEMBLY, Severity.MEDIUM),
            ("S002", 0.0, None, Severity.NONE),
        ]
    with closing(sqlite3.connect(e41.path)) as conn:
        assert {str(r[0]) for r in conn.execute("SELECT case_id FROM cases")} == {SEL, SUV, PL, PB}


def test_e41_s001_decides_three_new_informes_and_no_report(e41: Outcome) -> None:
    with SqliteRegistry(e41.path) as registry:
        notices, report = snapshot_items(registry, "S001")
    assert [n.notice_id for n in notices] == [f"S001-informe_de_turno-{c}" for c in (SEL, PL, PB)]
    assert report is None
    assert all("caso nuevo" in n.texto for n in notices)
    assert notices[2].texto == E22E_TEXT


def test_e41_s002_closes_t01_with_four_new_cases_and_pending_peak_for_pickup_brasil(e41: Outcome) -> None:
    with SqliteRegistry(e41.path) as registry:
        notices, report = snapshot_items(registry, "S002")
    assert [n.notice_id for n in notices] == [f"S002-informe_de_turno-{c}" for c in (SEL, SUV, PL, PB)]
    assert report is not None
    assert (report.turno_id, report.snapshot_id) == ("T01", "S002")
    assert report.novedades == notices
    assert report.novedades[3].texto == E22F_TEXT
    assert report.novedades[3].causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY)
    assert [active_view(row) for row in report.casos_activos] == [
        (SEL, -12.0, -33.3, Severity.HIGH, Severity.HIGH, CaseState.FOLLOW_UP, None),
        (SUV, -6.0, -25.0, Severity.HIGH, Severity.HIGH, CaseState.OPEN, None),
        (PL, -4.0, -13.3, Severity.MEDIUM, Severity.MEDIUM, CaseState.FOLLOW_UP, None),
        (PB, 0.0, 0.0, Severity.NONE, Severity.MEDIUM, CaseState.FOLLOW_UP, None),
    ]


def test_e41_s003_alerts_sedan_local_and_reports_the_resolution_of_pickup_brasil(e41: Outcome) -> None:
    with SqliteRegistry(e41.path) as registry:
        notices, report = snapshot_items(registry, "S003")
    assert [n.notice_id for n in notices] == [
        ALERT_ID,
        f"S003-sin_aviso-{SUV}",
        f"S003-informe_de_turno-{PL}",
        f"S003-informe_de_turno-{PB}",
    ]
    assert report is None
    alert = notices[0]
    assert alert.motivo == (Reason.GAP,)
    assert alert.origen is Origin.THRESHOLD
    assert alert.causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=None)
    assert alert.texto == E22D_TEXT
    assert notices[3].estado is CaseState.RESOLVED
    assert notices[3].causa.etapa is Stage.ASSEMBLY


def test_e41_s004_closes_t02_and_marks_the_whole_report_set(e41: Outcome) -> None:
    with SqliteRegistry(e41.path) as registry:
        notices, report = snapshot_items(registry, "S004")
        marked = {case_id: registry.cases.get_case(case_id) for case_id in (SEL, SUV, PL, PB)}
    assert [n.notice_id for n in notices] == [
        f"S004-informe_de_turno-{SEL}",
        f"S004-sin_aviso-{SUV}",
        f"S004-informe_de_turno-{PL}",
        f"S004-informe_de_turno-{PB}",
    ]
    assert (notices[0].texto, notices[2].texto, notices[3].texto) == (E22G_TEXT, E22H_TEXT, E22I_TEXT)
    assert report is not None
    assert (report.turno_id, report.snapshot_id) == ("T02", "S004")
    assert report.novedades == (notices[0], notices[2], notices[3])
    assert [active_view(row) for row in report.casos_activos] == [
        (SEL, -24.0, -66.7, Severity.CRITICAL, Severity.CRITICAL, CaseState.ESCALATED, None),
        (SUV, -6.0, -25.0, Severity.HIGH, Severity.HIGH, CaseState.FOLLOW_UP, None),
        (PL, -4.0, -13.3, Severity.MEDIUM, Severity.HIGH, CaseState.FOLLOW_UP, None),
    ]
    for case in marked.values():
        assert case is not None
        assert case.last_reported_at == "S004"
        assert case.max_severity_since_report is None
    pb = marked[PB]
    assert pb is not None
    assert (pb.state, pb.last_snapshot_id) == (CaseState.RESOLVED, "S003")


def test_e41_delivers_one_report_per_shift_and_the_single_alert_in_order(e41: Outcome) -> None:
    assert e41.recorder.calls == [("report", "T01"), ("alert", ALERT_ID), ("report", "T02")]
    rows = stored_rows(e41.path)
    assert len(rows) == 17
    assert sum(1 for r in rows if r.kind == "report" or r.tipo == NoticeType.ALERT) == 3
    assert pending_ids(e41.path) == []
    files = out_files(e41.out)
    assert sorted(files) == ["alertas.jsonl", "informe_T01.json", "informe_T02.json"]
    assert files["alertas.jsonl"].count(b"\n") == 1
    with SqliteRegistry(e41.path) as registry:
        _, t01 = snapshot_items(registry, "S002")
        alerts, _ = snapshot_items(registry, "S003")
    assert t01 is not None
    assert json.loads(files["informe_T01.json"].decode("utf-8")) == t01.model_dump(mode="json")
    assert json.loads(files["alertas.jsonl"].decode("utf-8")) == alerts[0].model_dump(mode="json")


def test_e41b_a_repeated_arrival_adds_no_rows_no_delivery_and_no_after_commit(
    tmp_path: Path, arrivals: list[Arrival]
) -> None:
    repeat = arrivals[2].model_copy(update={"orden": 5})
    recorder = RecordingNotifier()
    counter: list[CountingPostCommit] = []
    path = tmp_path / "registry.sqlite3"
    summary = run(path, [*arrivals, repeat], recorder, counter=counter)
    assert (summary.processed, summary.skipped) == (SERIES, ("S003",))
    assert len(stored_rows(path)) == 17
    assert recorder.calls == [("report", "T01"), ("alert", ALERT_ID), ("report", "T02")]
    assert counter[0].count == 5  # one at the start and one per committed snapshot


# --- T12 · E42 marking set across shifts ---


def test_e42_a_case_reported_as_resolved_is_not_marked_or_reported_again_in_the_next_shift(
    tmp_path: Path,
) -> None:
    long_arrivals = write_series(tmp_path / "snapshots", LONG_SERIES)
    path = tmp_path / "registry.sqlite3"
    summary = run(
        path, long_arrivals, CompositeNotifier((FileNotifier(tmp_path / "out"), RecordingNotifier()))
    )
    assert summary.processed == LONG_SERIES
    with SqliteRegistry(path) as registry:
        (opening, *_) = registry.cases.history(PB_SECOND)
        assert (opening.snapshot_id, opening.state, opening.minimum_severity, opening.gap_units) == (
            "S005",
            CaseState.OPEN,
            Severity.MEDIUM,
            -5.0,
        )
        _, report = snapshot_items(registry, "S006")
        old = registry.cases.get_case(PB)
        assert registry.cases.resolved_unreported() == ()
    assert report is not None
    assert report.turno_id == "T03"
    news_ids = {n.case_id for n in report.novedades}
    assert PB_SECOND in news_ids
    assert PB not in news_ids
    assert old is not None
    assert old.last_reported_at == "S004"
    assert (old.last_reported_state, old.last_reported_severity) == (CaseState.RESOLVED, Severity.NONE)
    assert old.max_severity_since_report is None


# --- T13 · E43-E45 interruption and resume (ADR-0010) ---

UNINTERRUPTED_CALLS: list[Call] = [("report", "T01"), ("alert", ALERT_ID), ("report", "T02")]


def test_e43_failure_after_saving_notices_leaves_no_rows_and_no_sends_then_resumes_identically(
    tmp_path: Path, arrivals: list[Arrival], baseline: Baseline
) -> None:
    path = tmp_path / "interrupted.sqlite3"
    out = tmp_path / "out"
    first = RecordingNotifier()
    with pytest.raises(RunAborted) as info:
        run(path, arrivals, CompositeNotifier((FileNotifier(out), first)), fail_save_at="S002")
    assert info.value.snapshot_id == "S002"
    assert info.value.summary.processed == ("S001",)
    rows = stored_rows(path)
    assert len(rows) == 3
    assert {r.snapshot_id for r in rows} == {"S001"}
    assert first.calls == []
    assert out_files(out) == {}
    with SqliteRegistry(path) as registry:
        assert registry.get_hash("S002") is None
        assert all(case.last_reported_at is None for case in registry.cases.active_cases())

    second = RecordingNotifier()
    summary = run(path, arrivals, CompositeNotifier((FileNotifier(out), second)))
    assert summary.processed == ("S002", "S003", "S004")
    assert second.calls == UNINTERRUPTED_CALLS
    assert stored_rows(path) == baseline.rows
    assert out_files(out) == baseline.files


def test_e44_b1_a_notifier_exception_is_logged_and_the_notice_is_retried_after_the_next_commit(
    tmp_path: Path, arrivals: list[Arrival], caplog: pytest.LogCaptureFixture
) -> None:
    path = tmp_path / "registry.sqlite3"
    recorder = RecordingNotifier(first_call_error=RuntimeError("boom"))
    summary = run(path, arrivals, recorder)
    assert summary.processed == SERIES
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "T01-informe" in errors[0].getMessage()
    assert recorder.calls == [("report", "T01"), ("report", "T01"), ("alert", ALERT_ID), ("report", "T02")]
    assert pending_ids(path) == []


def test_e44_b2_an_interrupted_notifier_is_resumed_exactly_once_and_then_nothing_is_resent(
    tmp_path: Path, arrivals: list[Arrival]
) -> None:
    path = tmp_path / "registry.sqlite3"
    with pytest.raises(KeyboardInterrupt):
        run(path, arrivals, RecordingNotifier(first_call_error=KeyboardInterrupt()))
    with SqliteRegistry(path) as registry:
        assert registry.get_hash("S002") is not None
        assert registry.get_hash("S003") is None
    assert pending_ids(path) == ["T01-informe"]

    events: list[Call] = []
    second = run(path, arrivals, RecordingNotifier(events=events), events=events)
    assert (second.processed, second.skipped) == (("S003", "S004"), ("S001", "S002"))
    assert events == [
        ("report", "T01"),
        ("process", "S003"),
        ("alert", ALERT_ID),
        ("process", "S004"),
        ("report", "T02"),
    ]

    third_recorder = RecordingNotifier()
    third = run(path, arrivals, third_recorder)
    assert (third.processed, third.skipped) == ((), SERIES)
    assert third_recorder.calls == []
    assert pending_ids(path) == []


def test_e45_an_interrupt_after_a_send_resends_once_and_leaves_the_files_identical(
    tmp_path: Path, arrivals: list[Arrival], baseline: Baseline
) -> None:
    path = tmp_path / "registry.sqlite3"
    out = tmp_path / "out"
    first = RecordingNotifier()
    with pytest.raises(KeyboardInterrupt):
        run(path, arrivals, CompositeNotifier((FileNotifier(out), first)), mark_failure=KeyboardInterrupt())
    assert first.calls == [("report", "T01")]
    assert "informe_T01.json" in out_files(out)
    assert pending_ids(path) == ["T01-informe"]

    second = RecordingNotifier()
    run(path, arrivals, CompositeNotifier((FileNotifier(out), second)))
    assert second.calls == UNINTERRUPTED_CALLS
    assert [*first.calls, *second.calls].count(("report", "T01")) == 2
    assert out_files(out) == baseline.files
