"""002 T10-T14: run_series orders, deduplicates, checks and delegates snapshots (E1-E22 runner parts)."""

import logging
from collections.abc import Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.domain.enums import AnomalyKind, Market, Model, ShiftPosition
from plant_monitor.domain.models import Anomaly, Combination, Shift, Snapshot, SnapshotCommit
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.hashing import content_hash
from plant_monitor.ingestion.plant import load_shifts
from plant_monitor.ingestion.snapshot import load_snapshot
from plant_monitor.runner.memory_store import InMemoryProcessedStore
from plant_monitor.runner.series import RunAborted, RunSummary, run_series

from builders import released_payload, snapshot_payload, unit_payload, write_snapshot

LOGGER = "plant_monitor.runner.series"
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)
MID = ShiftPosition.MID
CLOSING = ShiftPosition.CLOSING
T17 = Shift(
    turno_id="T17",
    inicio=datetime(2026, 3, 7, 14),
    fin=datetime(2026, 3, 7, 22),
    snapshot_medio="S033",
    snapshot_cierre="S034",
)
# Snapshot timestamp and calendar shift per id, so default payloads raise no shift_mismatch.
HEADERS: dict[str, tuple[str, str]] = {
    "S001": ("2026-03-02T10:00", "T01"),
    "S002": ("2026-03-02T14:00", "T01"),
    "S003": ("2026-03-02T18:00", "T02"),
    "S004": ("2026-03-02T22:00", "T02"),
    "S005": ("2026-03-03T02:00", "T03"),
    "S006": ("2026-03-03T06:00", "T03"),
    "S034": ("2026-03-07T22:00", "T17"),
    "S999": ("2026-03-09T10:00", "T99"),
}

type Call = tuple[str, str, ShiftPosition]


# --- Builders and fakes ---


def shifts() -> list[Shift]:
    """Fixture turnos.csv plus the synthetic T17 row (S033 mid, S034 closing)."""
    return [*load_shifts(FIXTURES / "turnos.csv"), T17]


def payload(
    snapshot_id: str,
    units: list[dict[str, object]] | None = None,
    released: list[dict[str, object]] | None = None,
    **overrides: object,
) -> dict[str, object]:
    """Valid payload for `snapshot_id` whose timestamp and turno agree with the calendar."""
    timestamp, turno = HEADERS[snapshot_id]
    data = snapshot_payload(units, released, snapshot_id=snapshot_id, timestamp=timestamp, turno=turno)
    data.update(overrides)
    return data


def arrival(orden: int, snapshot_id: str, archivo: Path, recibido: str = "2026-03-02T10:05") -> Arrival:
    """Row of llegadas.csv with `archivo` already resolved."""
    return Arrival(
        orden=orden, snapshot_id=snapshot_id, archivo=archivo, recibido=datetime.fromisoformat(recibido)
    )


def arrivals_for(directory: Path, *snapshot_ids: str) -> list[Arrival]:
    """Arrivals in orden 1..n pointing at `<id>.json`; no file is written."""
    return [arrival(i, sid, directory / f"{sid}.json") for i, sid in enumerate(snapshot_ids, start=1)]


def write_series(directory: Path, *snapshot_ids: str) -> list[Arrival]:
    """Write a valid default file per id and return the arrivals in orden 1..n."""
    for sid in snapshot_ids:
        write_snapshot(directory, payload(sid), f"{sid}.json")
    return arrivals_for(directory, *snapshot_ids)


class FakePipeline:
    """Records `(snapshot_id, turno_id, position)` per call and raises `error` on `fail_on`."""

    def __init__(self, fail_on: str | None = None, error: BaseException | None = None) -> None:
        self.fail_on = fail_on
        self.error = error
        self.calls: list[Call] = []
        self.snapshots: list[Snapshot] = []

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        self.calls.append((snapshot.snapshot_id, shift.turno_id, position))
        self.snapshots.append(snapshot)
        if snapshot.snapshot_id == self.fail_on and self.error is not None:
            raise self.error


class SpyStore:
    """Wraps an InMemoryProcessedStore and records every port call."""

    def __init__(self, inner: InMemoryProcessedStore | None = None) -> None:
        self.inner = inner if inner is not None else InMemoryProcessedStore()
        self.port_calls: list[str] = []
        self.commits: list[SnapshotCommit] = []
        self.recorded: list[Anomaly] = []

    def get_hash(self, snapshot_id: str) -> str | None:
        self.port_calls.append("get_hash")
        return self.inner.get_hash(snapshot_id)

    def known_units(self) -> Mapping[str, Combination]:
        self.port_calls.append("known_units")
        return self.inner.known_units()

    def record_anomaly(self, anomaly: Anomaly) -> None:
        self.port_calls.append("record_anomaly")
        self.recorded.append(anomaly)
        self.inner.record_anomaly(anomaly)

    def processing(self, commit: SnapshotCommit) -> AbstractContextManager[None]:
        self.port_calls.append("processing")
        self.commits.append(commit)
        return self.inner.processing(commit)


class CommitFailingStore(SpyStore):
    """Spy store whose unit of work fails on exit for `fail_on`, like a lost database write."""

    def __init__(self, fail_on: str) -> None:
        super().__init__()
        self.fail_on = fail_on

    def processing(self, commit: SnapshotCommit) -> AbstractContextManager[None]:
        if commit.snapshot_id != self.fail_on:
            return super().processing(commit)
        self.commits.append(commit)
        return self._failing_commit()

    @contextmanager
    def _failing_commit(self) -> Iterator[None]:
        yield
        raise OSError("disk full")


def log_lines(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    """Messages the runner logged at exactly `level`."""
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == level]


def of_kind(anomalies: tuple[Anomaly, ...], kind: AnomalyKind) -> list[Anomaly]:
    """Anomalies of one kind, in order."""
    return [a for a in anomalies if a.kind is kind]


def assert_complete(summary: RunSummary, arrivals: list[Arrival]) -> None:
    """A completed run accounts for every arrival as processed or skipped."""
    assert len(summary.processed) + len(summary.skipped) == len(arrivals)


# --- T10 · Happy path (E1, E2) ---


def test_e1_pipeline_gets_each_snapshot_with_shift_and_position_from_calendar(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    run_series(write_series(tmp_path, "S001", "S002", "S003"), shifts(), InMemoryProcessedStore(), pipeline)
    assert pipeline.calls == [("S001", "T01", MID), ("S002", "T01", CLOSING), ("S003", "T02", MID)]


def test_e1_pipeline_gets_the_snapshot_parsed_from_each_file(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    pipeline = FakePipeline()
    run_series(arrivals, shifts(), InMemoryProcessedStore(), pipeline)
    assert pipeline.snapshots == [load_snapshot(a.archivo) for a in arrivals]


def test_e1_summary_lists_processed_snapshots_and_nothing_else(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    summary = run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline())
    assert summary == RunSummary(processed=("S001", "S002", "S003"), skipped=(), anomalies=())
    assert_complete(summary, arrivals)


def test_e1_store_holds_the_content_hash_of_each_file(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    store = InMemoryProcessedStore()
    run_series(arrivals, shifts(), store, FakePipeline())
    for a in arrivals:
        assert store.get_hash(a.snapshot_id) == content_hash(a.archivo.read_bytes())


def test_e1_known_units_include_first_sighting_after_the_run(tmp_path: Path) -> None:
    write_snapshot(tmp_path, payload("S001", units=[unit_payload(unidad_id="U1")]), "S001.json")
    write_series(tmp_path, "S002", "S003")
    store = InMemoryProcessedStore()
    run_series(arrivals_for(tmp_path, "S001", "S002", "S003"), shifts(), store, FakePipeline())
    assert dict(store.known_units())["U1"] == SEDAN_LOCAL


def test_e1_logs_one_info_line_per_processed_snapshot(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    run_series(
        write_series(tmp_path, "S001", "S002", "S003"), shifts(), InMemoryProcessedStore(), FakePipeline()
    )
    assert log_lines(caplog, logging.INFO) == [
        "S001 processed: T01 mid",
        "S002 processed: T01 closing",
        "S003 processed: T02 mid",
    ]
    assert log_lines(caplog, logging.WARNING) == []


def test_e2_run_series_sorts_arrivals_by_orden(tmp_path: Path) -> None:
    s001, s002, s003 = write_series(tmp_path, "S001", "S002", "S003")
    pipeline = FakePipeline()
    summary = run_series([s002, s003, s001], shifts(), InMemoryProcessedStore(), pipeline)
    assert [call[0] for call in pipeline.calls] == ["S001", "S002", "S003"]
    assert summary.processed == ("S001", "S002", "S003")


def test_recibido_never_affects_order(tmp_path: Path) -> None:
    write_series(tmp_path, "S001", "S002")
    late_first = arrival(1, "S001", tmp_path / "S001.json", recibido="2026-03-02T23:00")
    early_second = arrival(2, "S002", tmp_path / "S002.json", recibido="2026-03-02T09:00")
    pipeline = FakePipeline()
    run_series([early_second, late_first], shifts(), InMemoryProcessedStore(), pipeline)
    assert [call[0] for call in pipeline.calls] == ["S001", "S002"]


def test_empty_series_returns_empty_summary() -> None:
    pipeline = FakePipeline()
    assert run_series([], shifts(), InMemoryProcessedStore(), pipeline) == RunSummary()
    assert pipeline.calls == []


# --- T11 · Idempotency (E7, E8, E9) ---


def s034_twice(tmp_path: Path, second_name: str = "S034.json") -> list[Arrival]:
    """S034 arriving twice: orden 1 from `S034.json`, orden 2 from `second_name`."""
    write_snapshot(tmp_path, payload("S034"), "S034.json")
    return [arrival(1, "S034", tmp_path / "S034.json"), arrival(2, "S034", tmp_path / second_name)]


def test_e7_identical_repeat_calls_pipeline_once(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    run_series(s034_twice(tmp_path), shifts(), InMemoryProcessedStore(), pipeline)
    assert pipeline.calls == [("S034", "T17", CLOSING)]


def test_e7_identical_repeat_is_skipped_in_summary(tmp_path: Path) -> None:
    arrivals = s034_twice(tmp_path)
    summary = run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline())
    assert summary == RunSummary(processed=("S034",), skipped=("S034",), anomalies=())
    assert_complete(summary, arrivals)


def test_e7_identical_repeat_logs_skip_at_info(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    run_series(s034_twice(tmp_path), shifts(), InMemoryProcessedStore(), FakePipeline())
    assert log_lines(caplog, logging.INFO) == [
        "S034 processed: T17 closing",
        "S034 skipped: already processed",
    ]
    assert log_lines(caplog, logging.WARNING) == []


def test_e7_processing_entered_once_and_record_anomaly_never_called(tmp_path: Path) -> None:
    store = SpyStore()
    run_series(s034_twice(tmp_path), shifts(), store, FakePipeline())
    assert [c.snapshot_id for c in store.commits] == ["S034"]
    assert store.port_calls.count("processing") == 1
    assert store.recorded == []


def write_s034_bis(tmp_path: Path) -> tuple[list[Arrival], str, str]:
    """E8 arrivals: S034.json then S034_bis.json with one unit more; returns both hashes too."""
    base_units = [unit_payload(), unit_payload(unidad_id="U00002")]
    first = write_snapshot(tmp_path, payload("S034", units=base_units), "S034.json")
    bis = write_snapshot(
        tmp_path, payload("S034", units=[*base_units, unit_payload(unidad_id="U00003")]), "S034_bis.json"
    )
    arrivals = [arrival(1, "S034", first), arrival(2, "S034", bis)]
    return arrivals, content_hash(first.read_bytes()), content_hash(bis.read_bytes())


def test_e8_pipeline_called_once_with_the_first_version(tmp_path: Path) -> None:
    arrivals, _, _ = write_s034_bis(tmp_path)
    pipeline = FakePipeline()
    run_series(arrivals, shifts(), InMemoryProcessedStore(), pipeline)
    assert pipeline.calls == [("S034", "T17", CLOSING)]
    assert len(pipeline.snapshots[0].unidades) == 2


def test_e8_store_keeps_the_first_hash(tmp_path: Path) -> None:
    arrivals, first_hash, _ = write_s034_bis(tmp_path)
    store = InMemoryProcessedStore()
    run_series(arrivals, shifts(), store, FakePipeline())
    assert store.get_hash("S034") == first_hash


def test_e8_summary_skips_and_reports_anomaly_with_both_hashes(tmp_path: Path) -> None:
    arrivals, first_hash, bis_hash = write_s034_bis(tmp_path)
    summary = run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline())
    assert summary.processed == ("S034",)
    assert summary.skipped == ("S034",)
    assert len(summary.anomalies) == 1
    anomaly = summary.anomalies[0]
    assert anomaly.kind is AnomalyKind.REPEATED_WITH_DIFFERENT_CONTENT
    assert anomaly.snapshot_id == "S034"
    assert first_hash in anomaly.detail
    assert bis_hash in anomaly.detail
    assert_complete(summary, arrivals)


def test_e8_record_anomaly_called_once_with_that_anomaly(tmp_path: Path) -> None:
    arrivals, _, _ = write_s034_bis(tmp_path)
    store = SpyStore()
    summary = run_series(arrivals, shifts(), store, FakePipeline())
    assert store.recorded == list(summary.anomalies)
    assert store.port_calls.count("record_anomaly") == 1
    assert store.port_calls.count("processing") == 1
    assert store.commits[0].anomalies == ()


def test_e8_warning_starts_with_prefix_and_names_both_hashes(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    arrivals, first_hash, bis_hash = write_s034_bis(tmp_path)
    run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline())
    warnings = log_lines(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert warnings[0].startswith("S034 repeated with different content (hash ")
    assert first_hash in warnings[0]
    assert bis_hash in warnings[0]


def write_raw(tmp_path: Path, name: str, data: bytes) -> Path:
    """Write raw bytes, valid JSON or not."""
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_e9a_seeded_identical_bytes_skipped_without_parsing(tmp_path: Path) -> None:
    arrivals = [arrival(1, "S034", write_raw(tmp_path, "S034.json", b"not json"))]
    store = InMemoryProcessedStore(hashes={"S034": content_hash(b"not json")})
    pipeline = FakePipeline()
    summary = run_series(arrivals, shifts(), store, pipeline)
    assert summary == RunSummary(processed=(), skipped=("S034",), anomalies=())
    assert pipeline.calls == []


def test_e9b_seeded_corrupt_repeat_gives_anomaly_without_parsing(tmp_path: Path) -> None:
    arrivals = [arrival(1, "S034", write_raw(tmp_path, "S034.json", b"{broken"))]
    store = InMemoryProcessedStore(hashes={"S034": content_hash(b"not json")})
    pipeline = FakePipeline()
    summary = run_series(arrivals, shifts(), store, pipeline)
    assert summary.processed == ()
    assert summary.skipped == ("S034",)
    assert [a.kind for a in summary.anomalies] == [AnomalyKind.REPEATED_WITH_DIFFERENT_CONTENT]
    assert pipeline.calls == []
    assert store.get_hash("S034") == content_hash(b"not json")


def test_rerun_with_different_hash_repeat_records_the_anomaly_again(tmp_path: Path) -> None:
    arrivals = [arrival(1, "S034", write_raw(tmp_path, "S034.json", b"{broken"))]
    store = SpyStore(InMemoryProcessedStore(hashes={"S034": content_hash(b"not json")}))
    run_series(arrivals, shifts(), store, FakePipeline())
    run_series(arrivals, shifts(), store, FakePipeline())
    assert len(store.recorded) == 2


# --- T12 · Failure and resume (E10, E10b, E13, E14) ---


def test_e10_pipeline_failure_raises_run_aborted_at_failed_snapshot(tmp_path: Path) -> None:
    error = RuntimeError("boom")
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline("S003", error))
    aborted = info.value
    assert aborted.snapshot_id == "S003"
    assert aborted.cause is error
    assert aborted.__cause__ is error
    assert "S003" in str(aborted)
    assert "boom" in str(aborted)


def test_e10_partial_summary_holds_snapshots_before_the_failure(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline("S003", RuntimeError("boom")))
    summary = info.value.summary
    assert summary.processed == ("S001", "S002")
    assert summary.skipped == ()
    assert len(summary.processed) + len(summary.skipped) == 2


def test_e10_store_marks_only_snapshots_before_the_failure(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    store = InMemoryProcessedStore()
    with pytest.raises(RunAborted):
        run_series(arrivals, shifts(), store, FakePipeline("S003", RuntimeError("boom")))
    assert store.get_hash("S001") is not None
    assert store.get_hash("S002") is not None
    assert store.get_hash("S003") is None


def test_e10_second_run_resumes_at_the_failed_snapshot(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    store = InMemoryProcessedStore()
    with pytest.raises(RunAborted):
        run_series(arrivals, shifts(), store, FakePipeline("S003", RuntimeError("boom")))
    healthy = FakePipeline()
    summary = run_series(arrivals, shifts(), store, healthy)
    assert healthy.calls == [("S003", "T02", MID)]
    assert summary.skipped == ("S001", "S002")
    assert summary.processed == ("S003",)
    assert_complete(summary, arrivals)


def test_e10_abort_logs_nothing_beyond_the_processed_lines(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger=LOGGER)
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    with pytest.raises(RunAborted):
        run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline("S003", RuntimeError("boom")))
    assert [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno >= logging.INFO] == [
        "S001 processed: T01 mid",
        "S002 processed: T01 closing",
    ]


def test_abort_index_counts_skipped_arrivals(tmp_path: Path) -> None:
    write_series(tmp_path, "S001", "S002")
    arrivals = [
        arrival(1, "S001", tmp_path / "S001.json"),
        arrival(2, "S001", tmp_path / "S001.json"),
        arrival(3, "S002", tmp_path / "S002.json"),
    ]
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), InMemoryProcessedStore(), FakePipeline("S002", RuntimeError("boom")))
    summary = info.value.summary
    assert summary.processed == ("S001",)
    assert summary.skipped == ("S001",)
    assert len(summary.processed) + len(summary.skipped) == 2


def test_unit_of_work_failure_raises_run_aborted_and_marks_nothing(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    store = CommitFailingStore(fail_on="S002")
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), store, FakePipeline())
    assert info.value.snapshot_id == "S002"
    assert isinstance(info.value.cause, OSError)
    assert info.value.summary.processed == ("S001",)
    assert store.get_hash("S002") is None
    assert store.get_hash("S003") is None


def test_e10b_keyboard_interrupt_propagates_unwrapped(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S002", "S003")
    store = InMemoryProcessedStore()
    pipeline = FakePipeline("S002", KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run_series(arrivals, shifts(), store, pipeline)
    assert store.get_hash("S002") is None
    assert store.get_hash("S001") is not None
    assert [call[0] for call in pipeline.calls] == ["S001", "S002"]


S002_TRUNCATED = b'{"snapshot_id": "S002", "unidades": ['


def test_e13_invalid_json_mid_series_aborts_with_data_load_error_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_series(tmp_path, "S001", "S003")
    write_raw(tmp_path, "S002.json", S002_TRUNCATED)
    arrivals = arrivals_for(tmp_path, "S001", "S002", "S003")
    read: list[str] = []
    original_read_bytes = Path.read_bytes

    def spy_read_bytes(self: Path) -> bytes:
        read.append(self.name)
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", spy_read_bytes)
    store = InMemoryProcessedStore()
    pipeline = FakePipeline()
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), store, pipeline)
    aborted = info.value
    assert aborted.snapshot_id == "S002"
    assert isinstance(aborted.cause, DataLoadError)
    assert aborted.__cause__ is aborted.cause
    assert "S002.json" in str(aborted.cause)
    assert len(aborted.summary.processed) + len(aborted.summary.skipped) == 1
    assert store.get_hash("S001") is not None
    assert store.get_hash("S002") is None
    assert pipeline.calls == [("S001", "T01", MID)]
    assert "S003.json" not in read


def test_e13_rerun_after_fixing_the_file_resumes_at_it(tmp_path: Path) -> None:
    write_series(tmp_path, "S001", "S003")
    write_raw(tmp_path, "S002.json", S002_TRUNCATED)
    arrivals = arrivals_for(tmp_path, "S001", "S002", "S003")
    store = InMemoryProcessedStore()
    with pytest.raises(RunAborted):
        run_series(arrivals, shifts(), store, FakePipeline())
    write_snapshot(tmp_path, payload("S002"), "S002.json")
    healthy = FakePipeline()
    summary = run_series(arrivals, shifts(), store, healthy)
    assert summary.skipped == ("S001",)
    assert summary.processed == ("S002", "S003")
    assert [call[0] for call in healthy.calls] == ["S002", "S003"]


def test_e14_json_id_mismatch_aborts_naming_file_field_and_both_ids(tmp_path: Path) -> None:
    mismatched = payload("S002")
    mismatched["snapshot_id"] = "S003"
    write_snapshot(tmp_path, mismatched, "S002.json")
    arrivals = arrivals_for(tmp_path, "S002")
    store = InMemoryProcessedStore()
    pipeline = FakePipeline()
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), store, pipeline)
    aborted = info.value
    assert aborted.snapshot_id == "S002"
    assert isinstance(aborted.cause, DataLoadError)
    message = str(aborted.cause).replace(str(tmp_path), "<dir>")
    assert "S002.json" in message
    assert "S002" in message.replace("S002.json", "")
    assert "S003" in message
    assert "snapshot_id" in message
    assert aborted.summary == RunSummary()
    assert store.get_hash("S002") is None
    assert pipeline.calls == []


# --- T13 · Upfront errors (E11, E12) ---


def test_e11_missing_file_raises_data_load_error_before_processing(tmp_path: Path) -> None:
    write_series(tmp_path, "S001", "S003")
    store = SpyStore()
    pipeline = FakePipeline()
    with pytest.raises(DataLoadError) as info:
        run_series(arrivals_for(tmp_path, "S001", "S002", "S003"), shifts(), store, pipeline)
    assert not isinstance(info.value, RunAborted)
    assert "S002.json" in str(info.value)
    assert pipeline.calls == []
    assert store.port_calls == []
    assert store.inner.get_hash("S001") is None
    assert dict(store.inner.known_units()) == {}


def test_upfront_error_names_every_missing_file(tmp_path: Path) -> None:
    write_series(tmp_path, "S001")
    with pytest.raises(DataLoadError) as info:
        run_series(
            arrivals_for(tmp_path, "S001", "S002", "S003"), shifts(), InMemoryProcessedStore(), FakePipeline()
        )
    assert "S002.json" in str(info.value)
    assert "S003.json" in str(info.value)


def test_e12_unknown_snapshot_raises_data_load_error_naming_it(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path, "S001", "S999")
    store = SpyStore()
    pipeline = FakePipeline()
    with pytest.raises(DataLoadError) as info:
        run_series(arrivals, shifts(), store, pipeline)
    assert not isinstance(info.value, RunAborted)
    assert "S999" in str(info.value)
    assert pipeline.calls == []
    assert store.port_calls == []


def test_e12_unknown_snapshot_and_missing_file_reported_in_one_error(tmp_path: Path) -> None:
    write_series(tmp_path, "S001", "S999")
    arrivals = arrivals_for(tmp_path, "S001", "S002", "S999")
    pipeline = FakePipeline()
    with pytest.raises(DataLoadError) as info:
        run_series(arrivals, shifts(), InMemoryProcessedStore(), pipeline)
    assert "S999" in str(info.value)
    assert "S002.json" in str(info.value)
    assert pipeline.calls == []


# --- T14 · Anomalies in the run (E15, E16, E17, E21, E22) ---


def run_s003_with_turno_t01(
    tmp_path: Path, store: SpyStore, pipeline: FakePipeline
) -> tuple[RunSummary, list[Arrival]]:
    """E15 setup: S003.json says `turno` T01 while turnos.csv maps S003 to T02 mid."""
    write_snapshot(tmp_path, payload("S003", turno="T01"), "S003.json")
    arrivals = arrivals_for(tmp_path, "S003")
    return run_series(arrivals, shifts(), store, pipeline), arrivals


def test_e15_pipeline_gets_shift_from_calendar_not_snapshot(tmp_path: Path) -> None:
    pipeline = FakePipeline()
    summary, _ = run_s003_with_turno_t01(tmp_path, SpyStore(), pipeline)
    assert pipeline.calls == [("S003", "T02", MID)]
    assert summary.processed == ("S003",)


def test_e15_shift_mismatch_in_summary_naming_both_shifts(tmp_path: Path) -> None:
    summary, _ = run_s003_with_turno_t01(tmp_path, SpyStore(), FakePipeline())
    assert len(summary.anomalies) == 1
    anomaly = summary.anomalies[0]
    assert anomaly.kind is AnomalyKind.SHIFT_MISMATCH
    assert anomaly.snapshot_id == "S003"
    assert "T01" in anomaly.detail
    assert "T02" in anomaly.detail


def test_e15_shift_mismatch_logged_once_as_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    summary, _ = run_s003_with_turno_t01(tmp_path, SpyStore(), FakePipeline())
    assert log_lines(caplog, logging.WARNING) == [f"S003 shift_mismatch: {summary.anomalies[0].detail}"]


def test_e15_anomaly_stored_through_the_commit_not_record_anomaly(tmp_path: Path) -> None:
    store = SpyStore()
    summary, _ = run_s003_with_turno_t01(tmp_path, store, FakePipeline())
    assert [c.anomalies for c in store.commits] == [summary.anomalies]
    assert store.recorded == []
    assert store.inner.recorded_anomalies() == summary.anomalies


def test_e16_future_stage_entry_is_an_anomaly_and_the_run_continues(tmp_path: Path) -> None:
    u00051 = unit_payload(
        unidad_id="U00051",
        modelo="SUV",
        mercado="Brasil",
        etapa="calidad",
        ingreso_etapa="2026-03-03T03:00",
        retrabajos=0,
        embarque_asignado="BRA-0303",
    )
    write_snapshot(tmp_path, payload("S005", units=[u00051]), "S005.json")
    write_series(tmp_path, "S006")
    arrivals = arrivals_for(tmp_path, "S005", "S006")
    pipeline = FakePipeline()
    summary = run_series(arrivals, shifts(), InMemoryProcessedStore(), pipeline)
    stage = of_kind(summary.anomalies, AnomalyKind.STAGE_ENTRY_AFTER_SNAPSHOT)
    assert len(stage) == 1
    assert stage[0].snapshot_id == "S005"
    assert "U00051" in stage[0].detail
    assert summary.processed == ("S005", "S006")
    assert pipeline.calls == [("S005", "T03", MID), ("S006", "T03", CLOSING)]


def sedan_local_release(unit_id: str) -> dict[str, object]:
    """Release of `unit_id` as Sedán/Local."""
    return released_payload(unidad_id=unit_id, modelo="Sedán", mercado="Local")


def suv_local_release(unit_id: str) -> dict[str, object]:
    """Release of `unit_id` as SUV/Local."""
    return released_payload(unidad_id=unit_id, modelo="SUV", mercado="Local")


def assert_one_u_change(anomalies: tuple[Anomaly, ...], snapshot_id: str, unit_id: str) -> None:
    """Exactly one unit_combination_changed anomaly: `unit_id` in `snapshot_id`, Sedán/Local to SUV/Local."""
    changed = of_kind(anomalies, AnomalyKind.UNIT_COMBINATION_CHANGED)
    assert len(changed) == 1
    assert changed[0].snapshot_id == snapshot_id
    assert unit_id in changed[0].detail
    assert "Sedán/Local" in changed[0].detail
    assert "SUV/Local" in changed[0].detail


def write_e17(tmp_path: Path) -> list[Arrival]:
    """E17: S001 releases U1, U2 as Sedán/Local; S002 releases U2, U3 as SUV/Local."""
    s001_released = [sedan_local_release("U1"), sedan_local_release("U2")]
    write_snapshot(tmp_path, payload("S001", units=[], released=s001_released), "S001.json")
    s002_released = [suv_local_release("U2"), suv_local_release("U3")]
    write_snapshot(tmp_path, payload("S002", units=[], released=s002_released), "S002.json")
    return arrivals_for(tmp_path, "S001", "S002")


def test_e17_identity_is_carried_across_snapshots_of_one_run(tmp_path: Path) -> None:
    summary = run_series(write_e17(tmp_path), shifts(), InMemoryProcessedStore(), FakePipeline())
    assert_one_u_change(summary.anomalies, "S002", "U2")
    assert len(summary.anomalies) == 1
    assert summary.processed == ("S001", "S002")


def test_e17_commits_carry_new_units_and_the_anomaly(tmp_path: Path) -> None:
    store = SpyStore()
    summary = run_series(write_e17(tmp_path), shifts(), store, FakePipeline())
    s001, s002 = store.commits
    assert dict(s001.new_units) == {"U1": SEDAN_LOCAL, "U2": SEDAN_LOCAL}
    assert s001.anomalies == ()
    assert dict(s002.new_units) == {"U3": SUV_LOCAL}
    assert s002.anomalies == summary.anomalies
    assert dict(store.inner.known_units()) == {"U1": SEDAN_LOCAL, "U2": SEDAN_LOCAL, "U3": SUV_LOCAL}


def test_e17_combination_change_logged_as_warning(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=LOGGER)
    summary = run_series(write_e17(tmp_path), shifts(), InMemoryProcessedStore(), FakePipeline())
    assert log_lines(caplog, logging.WARNING) == [
        f"S002 unit_combination_changed: {summary.anomalies[0].detail}"
    ]


def test_e21_unit_seen_in_process_then_released_in_new_combination(tmp_path: Path) -> None:
    u9 = unit_payload(unidad_id="U9", etapa="calidad")
    write_snapshot(tmp_path, payload("S001", units=[u9], released=[]), "S001.json")
    write_snapshot(tmp_path, payload("S002", units=[], released=[suv_local_release("U9")]), "S002.json")
    summary = run_series(
        arrivals_for(tmp_path, "S001", "S002"), shifts(), InMemoryProcessedStore(), FakePipeline()
    )
    assert_one_u_change(summary.anomalies, "S002", "U9")
    assert summary.processed == ("S001", "S002")


def write_e22(tmp_path: Path) -> list[Arrival]:
    """E22: S001 releases U2 as Sedán/Local; S002 releases U2 and U3 as SUV/Local."""
    write_snapshot(tmp_path, payload("S001", units=[], released=[sedan_local_release("U2")]), "S001.json")
    s002_released = [suv_local_release("U2"), suv_local_release("U3")]
    write_snapshot(tmp_path, payload("S002", units=[], released=s002_released), "S002.json")
    return arrivals_for(tmp_path, "S001", "S002")


def test_e22_failed_run_reports_anomaly_but_stores_only_committed_units(tmp_path: Path) -> None:
    arrivals = write_e22(tmp_path)
    store = InMemoryProcessedStore()
    with pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), store, FakePipeline("S002", RuntimeError("boom")))
    assert_one_u_change(info.value.summary.anomalies, "S002", "U2")
    assert dict(store.known_units()) == {"U2": SEDAN_LOCAL}
    assert store.recorded_anomalies() == ()


def test_e22_resumed_run_seeds_identity_from_store_and_detects_again(tmp_path: Path) -> None:
    arrivals = write_e22(tmp_path)
    store = InMemoryProcessedStore()
    with pytest.raises(RunAborted):
        run_series(arrivals, shifts(), store, FakePipeline("S002", RuntimeError("boom")))
    summary = run_series(arrivals, shifts(), store, FakePipeline())
    assert summary.skipped == ("S001",)
    assert summary.processed == ("S002",)
    assert_one_u_change(summary.anomalies, "S002", "U2")
    assert dict(store.known_units()) == {"U2": SEDAN_LOCAL, "U3": SUV_LOCAL}
    assert store.recorded_anomalies() == summary.anomalies


def test_identity_seeded_from_store_across_separate_runs(tmp_path: Path) -> None:
    arrivals = write_e22(tmp_path)
    store = InMemoryProcessedStore()
    run_series(arrivals[:1], shifts(), store, FakePipeline())
    summary = run_series(arrivals[1:], shifts(), store, FakePipeline())
    assert_one_u_change(summary.anomalies, "S002", "U2")


def test_anomalies_before_pipeline_failure_in_summary_but_not_stored(tmp_path: Path) -> None:
    store = SpyStore()
    with pytest.raises(RunAborted) as info:
        run_s003_with_turno_t01(tmp_path, store, FakePipeline("S003", RuntimeError("boom")))
    assert [a.kind for a in info.value.summary.anomalies] == [AnomalyKind.SHIFT_MISMATCH]
    assert info.value.summary.processed == ()
    assert store.inner.recorded_anomalies() == ()
    assert store.recorded == []
