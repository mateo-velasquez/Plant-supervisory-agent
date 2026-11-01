"""002 T8: ProcessedStore unit-of-work contract (E19) and InMemoryProcessedStore specifics."""

from collections.abc import Callable
from datetime import datetime

import pytest

from plant_monitor.domain.enums import AnomalyKind, Market, Model, ShiftPosition
from plant_monitor.domain.models import Anomaly, Combination, Shift, Snapshot, SnapshotCommit
from plant_monitor.runner.memory_store import InMemoryProcessedStore
from plant_monitor.runner.ports import ProcessedStore, SnapshotPipeline

StoreFactory = Callable[[], ProcessedStore]

SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)
HASH_S001 = "ab" * 32
HASH_S002 = "cd" * 32
S001_ANOMALY = Anomaly(
    kind=AnomalyKind.SHIFT_MISMATCH, snapshot_id="S001", detail="turno T02, turnos.csv T01"
)
Q10_ANOMALY = Anomaly(
    kind=AnomalyKind.REPEATED_WITH_DIFFERENT_CONTENT, snapshot_id="S034", detail="hash ef, stored hash 01"
)
COMMIT_S001 = SnapshotCommit(
    snapshot_id="S001", content_hash=HASH_S001, anomalies=(S001_ANOMALY,), new_units={"U1": SEDAN_LOCAL}
)
COMMIT_S002 = SnapshotCommit(
    snapshot_id="S002", content_hash=HASH_S002, anomalies=(), new_units={"U3": SUV_LOCAL}
)


@pytest.fixture(params=[InMemoryProcessedStore], ids=["in_memory"])
def store_factory(request: pytest.FixtureRequest) -> StoreFactory:
    """Every ProcessedStore implementation; spec 003 adds its SQLite store here."""
    factory: StoreFactory = request.param
    return factory


def commit_cleanly(store: ProcessedStore, commit: SnapshotCommit) -> None:
    """Run an empty unit of work that exits cleanly."""
    with store.processing(commit):
        pass


# --- Contract (E19), every implementation ---


def test_e19a_fresh_store_has_no_hash_and_no_known_units(store_factory: StoreFactory) -> None:
    store = store_factory()
    assert store.get_hash("S001") is None
    assert dict(store.known_units()) == {}


def test_e19b_exception_in_processing_propagates_and_records_nothing(store_factory: StoreFactory) -> None:
    store = store_factory()
    with pytest.raises(RuntimeError, match="boom"), store.processing(COMMIT_S001):
        raise RuntimeError("boom")
    assert store.get_hash("S001") is None
    assert dict(store.known_units()) == {}


def test_e10b_keyboard_interrupt_in_processing_propagates_and_records_nothing(
    store_factory: StoreFactory,
) -> None:
    store = store_factory()
    with pytest.raises(KeyboardInterrupt), store.processing(COMMIT_S001):
        raise KeyboardInterrupt
    assert store.get_hash("S001") is None
    assert dict(store.known_units()) == {}


def test_e19c_clean_exit_records_hash_and_new_units(store_factory: StoreFactory) -> None:
    store = store_factory()
    commit_cleanly(store, COMMIT_S001)
    assert store.get_hash("S001") == HASH_S001
    assert dict(store.known_units()) == {"U1": SEDAN_LOCAL}


def test_e19c_clean_exit_marks_only_its_own_snapshot(store_factory: StoreFactory) -> None:
    store = store_factory()
    commit_cleanly(store, COMMIT_S001)
    assert store.get_hash("S002") is None


def test_e19d_reentering_processing_for_marked_snapshot_raises_naming_it(store_factory: StoreFactory) -> None:
    store = store_factory()
    commit_cleanly(store, COMMIT_S001)
    body_ran = False
    with pytest.raises(ValueError, match="S001"), store.processing(COMMIT_S001):
        body_ran = True
    assert not body_ran
    assert store.get_hash("S001") == HASH_S001
    assert dict(store.known_units()) == {"U1": SEDAN_LOCAL}


def test_e19d_reentering_with_a_different_hash_also_raises(store_factory: StoreFactory) -> None:
    store = store_factory()
    commit_cleanly(store, COMMIT_S001)
    other = SnapshotCommit(snapshot_id="S001", content_hash=HASH_S002, anomalies=(), new_units={})
    with pytest.raises(ValueError, match="S001"), store.processing(other):
        pass
    assert store.get_hash("S001") == HASH_S001


def test_failed_unit_of_work_can_be_retried_and_then_records(store_factory: StoreFactory) -> None:
    store = store_factory()
    with pytest.raises(RuntimeError), store.processing(COMMIT_S001):
        raise RuntimeError("boom")
    commit_cleanly(store, COMMIT_S001)
    assert store.get_hash("S001") == HASH_S001
    assert dict(store.known_units()) == {"U1": SEDAN_LOCAL}


def test_known_units_accumulate_across_commits(store_factory: StoreFactory) -> None:
    store = store_factory()
    commit_cleanly(store, COMMIT_S001)
    commit_cleanly(store, COMMIT_S002)
    assert store.get_hash("S002") == HASH_S002
    assert dict(store.known_units()) == {"U1": SEDAN_LOCAL, "U3": SUV_LOCAL}


def test_q20_first_sighting_in_known_units_is_never_overwritten(store_factory: StoreFactory) -> None:
    store = store_factory()
    commit_cleanly(store, COMMIT_S001)
    resighted = SnapshotCommit(
        snapshot_id="S002", content_hash=HASH_S002, anomalies=(), new_units={"U1": SUV_LOCAL}
    )
    commit_cleanly(store, resighted)
    assert store.get_hash("S002") == HASH_S002
    assert dict(store.known_units()) == {"U1": SEDAN_LOCAL}


def test_record_anomaly_does_not_mark_any_snapshot(store_factory: StoreFactory) -> None:
    store = store_factory()
    store.record_anomaly(Q10_ANOMALY)
    assert store.get_hash("S034") is None
    assert dict(store.known_units()) == {}


# --- InMemoryProcessedStore specifics ---


def test_in_memory_fresh_store_has_no_recorded_anomalies() -> None:
    assert InMemoryProcessedStore().recorded_anomalies() == ()


def test_in_memory_records_commit_anomaly_only_after_clean_exit() -> None:
    store = InMemoryProcessedStore()
    with store.processing(COMMIT_S001):
        assert store.recorded_anomalies() == ()
        assert store.get_hash("S001") is None
    assert store.recorded_anomalies() == (S001_ANOMALY,)


def test_in_memory_records_no_anomaly_after_exception() -> None:
    store = InMemoryProcessedStore()
    with pytest.raises(RuntimeError), store.processing(COMMIT_S001):
        raise RuntimeError("boom")
    assert store.recorded_anomalies() == ()


def test_in_memory_records_no_anomaly_after_keyboard_interrupt() -> None:
    store = InMemoryProcessedStore()
    with pytest.raises(KeyboardInterrupt), store.processing(COMMIT_S001):
        raise KeyboardInterrupt
    assert store.recorded_anomalies() == ()


def test_in_memory_record_anomaly_is_recorded() -> None:
    store = InMemoryProcessedStore()
    store.record_anomaly(Q10_ANOMALY)
    assert store.recorded_anomalies() == (Q10_ANOMALY,)


def test_in_memory_holds_commit_anomaly_plus_record_anomaly_calls() -> None:
    store = InMemoryProcessedStore()
    store.record_anomaly(Q10_ANOMALY)
    commit_cleanly(store, COMMIT_S001)
    recorded = store.recorded_anomalies()
    assert len(recorded) == 2
    assert set(recorded) == {Q10_ANOMALY, S001_ANOMALY}


def test_in_memory_rejected_reentry_records_no_extra_anomaly() -> None:
    store = InMemoryProcessedStore()
    commit_cleanly(store, COMMIT_S001)
    with pytest.raises(ValueError), store.processing(COMMIT_S001):
        pass
    assert store.recorded_anomalies() == (S001_ANOMALY,)


def test_in_memory_hashes_seed_marks_snapshot() -> None:
    store = InMemoryProcessedStore(hashes={"S034": "x"})
    assert store.get_hash("S034") == "x"
    assert store.get_hash("S001") is None
    assert dict(store.known_units()) == {}
    assert store.recorded_anomalies() == ()


def test_in_memory_seeded_snapshot_cannot_be_processed_again() -> None:
    store = InMemoryProcessedStore(hashes={"S034": "x"})
    commit = SnapshotCommit(snapshot_id="S034", content_hash="y", anomalies=(), new_units={})
    with pytest.raises(ValueError, match="S034"), store.processing(commit):
        pass
    assert store.get_hash("S034") == "x"


# --- Structural typing (checked by mypy --strict) ---


class NoopPipeline:
    """Pipeline that does nothing; satisfies SnapshotPipeline structurally."""

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        return None


def test_in_memory_store_is_assignable_to_processed_store_port() -> None:
    store: ProcessedStore = InMemoryProcessedStore()
    assert store.get_hash("S001") is None


def test_class_with_process_is_assignable_to_snapshot_pipeline_port() -> None:
    pipeline: SnapshotPipeline = NoopPipeline()
    shift = Shift(
        turno_id="T01",
        inicio=datetime(2026, 3, 2, 6),
        fin=datetime(2026, 3, 2, 14),
        snapshot_medio="S001",
        snapshot_cierre="S002",
    )
    snapshot = Snapshot(
        snapshot_id="S001", timestamp=datetime(2026, 3, 2, 10), turno="T01", unidades=(), liberadas=()
    )
    pipeline.process(snapshot, shift, ShiftPosition.MID)
