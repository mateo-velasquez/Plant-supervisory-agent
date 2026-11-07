"""003 T12-T15: the SQLite registry, its unit of work, cases and history, and released units."""

import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.cases.lifecycle import Observation, Step, mark_reported, step
from plant_monitor.cases.registry import SCHEMA_VERSION, CaseRepository, SqliteRegistry
from plant_monitor.domain.cases import Case, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import AnomalyKind, Market, Model, Severity, Stage
from plant_monitor.domain.models import Anomaly, Combination, ReleasedUnit, Snapshot, SnapshotCommit
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext, compute_metrics
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import ResolutionThresholds, load_thresholds

from builders import PICKUP_BRAZIL, case_with, history_row, metrics_with

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
PB_CASE = "S010-Pickup-Brasil"
SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)

ANOMALY_A = Anomaly(kind=AnomalyKind.SHIFT_MISMATCH, snapshot_id="S001", detail="turno T02, turnos.csv T01")
ANOMALY_B = Anomaly(kind=AnomalyKind.SHIFT_MISMATCH, snapshot_id="S002", detail="turno T03, turnos.csv T01")
ANOMALY_Q = Anomaly(
    kind=AnomalyKind.REPEATED_WITH_DIFFERENT_CONTENT, snapshot_id="S034", detail="hash ef, stored hash 01"
)


@pytest.fixture
def resolution() -> ResolutionThresholds:
    return load_thresholds(FIXTURES / "umbrales.yaml").resolucion


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


def commit(
    snapshot_id: str,
    *,
    anomalies: tuple[Anomaly, ...] = (),
    new_units: Mapping[str, Combination] | None = None,
) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id."""
    return SnapshotCommit(
        snapshot_id=snapshot_id,
        content_hash=f"hash-{snapshot_id}",
        anomalies=anomalies,
        new_units=new_units if new_units is not None else {},
    )


def opened(
    snapshot_id: str,
    minimum: Severity,
    resolution: ResolutionThresholds,
    *,
    raised: bool = False,
    combination: Combination = PICKUP_BRAZIL,
) -> Step:
    """A case opened by 'lifecycle.step' at 'snapshot_id'."""
    obs = Observation(snapshot_id, metrics_with(minimum, combination=combination), raised)
    result = step(None, obs, resolution)
    assert result is not None
    return result


def advanced(
    case: Case, snapshot_id: str, minimum: Severity, resolution: ResolutionThresholds, *, raised: bool = False
) -> Step:
    """'case' stepped by 'lifecycle.step' to 'snapshot_id'."""
    obs = Observation(snapshot_id, metrics_with(minimum, combination=case.combination), raised)
    result = step(case, obs, resolution)
    assert result is not None
    return result


def e1_step(resolution: ResolutionThresholds) -> Step:
    """E1/E22 case and row: PB opens at S010 with min media and the E22 metric values."""
    metrics = metrics_with(
        Severity.MEDIUM, gap_units=-4.0, gap_pct=-13.3, delay_days=0.0, bottleneck=Stage.ASSEMBLY
    )
    result = step(None, Observation("S010", metrics, False), resolution)
    assert result is not None
    return result


def save_in_own_unit(
    registry: SqliteRegistry,
    s: Step,
    *,
    anomalies: tuple[Anomaly, ...] = (),
    new_units: Mapping[str, Combination] | None = None,
) -> None:
    """Save one step's case and row in its own committed unit of work."""
    snapshot_id = s.history.snapshot_id
    with registry.processing(commit(snapshot_id, anomalies=anomalies, new_units=new_units)):
        registry.cases.save_case(s.case, s.history)


def names_all(message: str, *names: str) -> bool:
    """True when the message names every given id."""
    return all(name in message for name in names)


def user_version(path: Path) -> int:
    """PRAGMA user_version of a SQLite file, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


# --- T12 · Schema, session, ProcessedStore, anomalies ---


def test_schema_version_is_two() -> None:
    assert SCHEMA_VERSION == 2


def test_e20a_commit_anomaly_is_recorded(registry: SqliteRegistry) -> None:
    with registry.processing(commit("S001", anomalies=(ANOMALY_A,))):
        pass
    assert registry.recorded_anomalies() == (ANOMALY_A,)


def test_e20b_identical_anomaly_is_stored_once_in_insertion_order(registry: SqliteRegistry) -> None:
    with registry.processing(commit("S001", anomalies=(ANOMALY_A,))):
        pass
    registry.record_anomaly(ANOMALY_Q)
    registry.record_anomaly(ANOMALY_Q)
    assert registry.recorded_anomalies() == (ANOMALY_A, ANOMALY_Q)


def test_e20c_identical_anomaly_after_reopen_is_not_duplicated(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as first:
        with first.processing(commit("S001", anomalies=(ANOMALY_A,))):
            pass
        first.record_anomaly(ANOMALY_Q)
    with SqliteRegistry(path) as second:
        second.record_anomaly(ANOMALY_Q)
        assert second.recorded_anomalies() == (ANOMALY_A, ANOMALY_Q)


def test_e20d_anomaly_of_a_failed_unit_of_work_is_not_stored(registry: SqliteRegistry) -> None:
    with registry.processing(commit("S001", anomalies=(ANOMALY_A,))):
        pass
    with (
        pytest.raises(RuntimeError, match="boom"),
        registry.processing(commit("S002", anomalies=(ANOMALY_B,))),
    ):
        raise RuntimeError("boom")
    assert registry.recorded_anomalies() == (ANOMALY_A,)


def test_e21a_new_file_gets_schema_version_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path):
        pass
    assert user_version(path) == SCHEMA_VERSION
    with SqliteRegistry(path) as again:
        assert again.get_hash("S001") is None


def test_e21b_other_schema_version_raises_naming_file_and_versions_and_leaves_file(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA user_version = 7")
    with pytest.raises(ValueError) as error:
        SqliteRegistry(path)
    message = str(error.value)
    assert path.name in message, message
    versions = message.replace(str(path), "").replace(path.name, "")
    assert re.search(r"\b7\b", versions), message
    assert re.search(rf"\b{SCHEMA_VERSION}\b", versions), message
    assert user_version(path) == 7
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT count(*) FROM sqlite_master").fetchone()[0] == 0


def test_current_snapshot_is_the_open_unit_of_work(registry: SqliteRegistry) -> None:
    assert registry.current_snapshot() is None
    with registry.processing(commit("S010")):
        assert registry.current_snapshot() == "S010"
    assert registry.current_snapshot() is None
    with pytest.raises(RuntimeError), registry.processing(commit("S011")):
        raise RuntimeError("boom")
    assert registry.current_snapshot() is None


def test_e23e_record_anomaly_inside_processing_raises_and_writes_nothing(registry: SqliteRegistry) -> None:
    with pytest.raises(RuntimeError), registry.processing(commit("S010")):
        registry.record_anomaly(ANOMALY_Q)
    assert registry.recorded_anomalies() == ()
    assert registry.get_hash("S010") is None


def test_e23f_nested_processing_raises_naming_the_open_one_and_keeps_it_open(
    registry: SqliteRegistry,
) -> None:
    """A failed nested entry must not clear the outer unit of work, or its writes would go unguarded."""
    with registry.processing(commit("S010")):
        with pytest.raises(RuntimeError, match="S010"), registry.processing(commit("S011")):
            pass
        assert registry.current_snapshot() == "S010"
    assert registry.get_hash("S011") is None
    assert registry.get_hash("S010") == "hash-S010"


# --- T13 · Case repository ---


def test_case_repository_port_is_satisfied_by_registry_cases(registry: SqliteRegistry) -> None:
    repo: CaseRepository = registry.cases
    assert repo.current_snapshot() is None
    with registry.processing(commit("S010")):
        assert repo.current_snapshot() == "S010"
    assert repo.current_snapshot() is None


def test_e22_case_and_history_row_round_trip(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = e1_step(resolution)
    with registry.processing(commit("S010")):
        registry.cases.save_case(s.case, s.history)
        assert registry.cases.get_case(PB_CASE) == s.case
        assert registry.cases.active_cases() == (s.case,)
        assert registry.cases.history(PB_CASE) == (s.history,)
    assert registry.cases.get_case(PB_CASE) == s.case
    assert registry.cases.active_cases() == (s.case,)
    assert registry.cases.history(PB_CASE) == (s.history,)
    assert registry.cases.get_case("S999-Pickup-Brasil") is None


def test_reads_rebuild_effective_severity_from_minimum_and_raise(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    """E22 has raised False, so a raised case (E9) is needed to show severities are rebuilt, not echoed."""
    s = opened("S010", Severity.MEDIUM, resolution, raised=True)
    save_in_own_unit(registry, s)
    case = registry.cases.get_case(PB_CASE)
    assert case == s.case
    assert case is not None
    assert case.raised is True
    assert case.current_severity is Severity.CRITICAL
    (row,) = registry.cases.history(PB_CASE)
    assert row == s.history
    assert row.minimum_severity is Severity.MEDIUM
    assert row.effective_severity is Severity.CRITICAL


def test_active_cases_follow_all_combinations_order(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    """Sedán sorts after Pickup byte-wise, so saving PB first checks the order is all_combinations()'s."""
    pb = opened("S010", Severity.MEDIUM, resolution)
    sel = opened("S010", Severity.HIGH, resolution, combination=SEDAN_LOCAL)
    with registry.processing(commit("S010")):
        registry.cases.save_case(pb.case, pb.history)
        registry.cases.save_case(sel.case, sel.history)
    assert registry.cases.active_cases() == (sel.case, pb.case)


def test_e4_second_active_case_for_a_combination_raises_naming_it(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    first = opened("S010", Severity.MEDIUM, resolution)
    save_in_own_unit(registry, first)
    follow_up = advanced(first.case, "S011", Severity.MEDIUM, resolution)
    save_in_own_unit(registry, follow_up)
    assert follow_up.case.state is CaseState.FOLLOW_UP
    second = opened("S012", Severity.HIGH, resolution)
    with registry.processing(commit("S012")):
        with pytest.raises(ValueError, match=r"Pickup.*Brasil"):
            registry.cases.save_case(second.case, second.history)
        assert registry.cases.get_case("S012-Pickup-Brasil") is None
    assert registry.cases.active_cases() == (follow_up.case,)


def test_second_save_for_same_case_and_snapshot_updates_in_place(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    first = opened("S010", Severity.HIGH, resolution)
    save_in_own_unit(registry, first)
    plain = advanced(first.case, "S011", Severity.HIGH, resolution)
    with_raise = advanced(first.case, "S011", Severity.HIGH, resolution, raised=True)
    with registry.processing(commit("S011")):
        registry.cases.save_case(plain.case, plain.history)
        registry.cases.save_case(with_raise.case, with_raise.history)
    assert registry.cases.get_case(PB_CASE) == with_raise.case
    assert registry.cases.active_cases() == (with_raise.case,)
    assert registry.cases.history(PB_CASE) == (first.history, with_raise.history)


def test_e23a_save_case_outside_processing_raises_and_writes_nothing(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = e1_step(resolution)
    with pytest.raises(RuntimeError):
        registry.cases.save_case(s.case, s.history)
    assert registry.cases.get_case(PB_CASE) is None
    assert registry.cases.history(PB_CASE) == ()


def test_e23b_update_case_outside_processing_raises_and_writes_nothing(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = e1_step(resolution)
    save_in_own_unit(registry, s)
    with pytest.raises(RuntimeError):
        registry.cases.update_case(mark_reported(s.case, "S010"))
    assert registry.cases.get_case(PB_CASE) == s.case


def test_e23d_save_case_for_another_snapshot_raises_naming_both(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = opened("S011", Severity.MEDIUM, resolution)
    with registry.processing(commit("S010")):
        with pytest.raises(ValueError) as error:
            registry.cases.save_case(s.case, s.history)
        assert names_all(str(error.value), "S010", "S011"), str(error.value)
        assert registry.cases.get_case("S011-Pickup-Brasil") is None


def test_e23g_update_case_for_unknown_case_raises_naming_it(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    ghost = mark_reported(opened("S999", Severity.MEDIUM, resolution).case, "S010")
    with registry.processing(commit("S010")), pytest.raises(ValueError, match="S999-Pickup-Brasil"):
        registry.cases.update_case(ghost)


def test_e23h_save_case_with_row_at_another_snapshot_raises_naming_both(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    step = opened("S010", Severity.MEDIUM, resolution)
    row = step.history.model_copy(update={"snapshot_id": "S009"})
    with registry.processing(commit("S010")):
        with pytest.raises(ValueError) as error:
            registry.cases.save_case(step.case, row)
        assert names_all(str(error.value), "S010", "S009"), str(error.value)
        assert "belongs to" not in str(error.value)
        assert registry.cases.get_case(PB_CASE) is None


def test_update_case_writes_only_the_report_baseline_and_no_history_row(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = e1_step(resolution)
    save_in_own_unit(registry, s)
    marked = mark_reported(s.case, "S011")
    tampered = marked.model_copy(update={"clean_streak": 7})
    with registry.processing(commit("S011")):
        registry.cases.update_case(tampered)
    assert registry.cases.get_case(PB_CASE) == marked
    assert registry.cases.history(PB_CASE) == (s.history,)


def test_update_case_requires_last_reported_at_to_be_the_open_snapshot(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = e1_step(resolution)
    save_in_own_unit(registry, s)
    with registry.processing(commit("S011")):
        with pytest.raises(ValueError) as error:
            registry.cases.update_case(mark_reported(s.case, "S010"))
        assert names_all(str(error.value), "S010", "S011"), str(error.value)
        with pytest.raises(ValueError):
            registry.cases.update_case(s.case)
    assert registry.cases.get_case(PB_CASE) == s.case


# --- T14 · Atomicity, reopen and resume ---


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(RuntimeError("boom"), id="runtime_error"),
        pytest.param(KeyboardInterrupt(), id="interrupt"),
    ],
)
def test_e25_failure_in_block_leaves_nothing_and_snapshot_commits_again(
    registry: SqliteRegistry, resolution: ResolutionThresholds, failure: BaseException
) -> None:
    s = e1_step(resolution)
    s010 = commit("S010", new_units={"U1": PICKUP_BRAZIL})
    with pytest.raises(type(failure)), registry.processing(s010):
        registry.cases.save_case(s.case, s.history)
        raise failure
    assert registry.cases.get_case(PB_CASE) is None
    assert registry.cases.active_cases() == ()
    assert registry.cases.history(PB_CASE) == ()
    assert registry.get_hash("S010") is None
    assert dict(registry.known_units()) == {}
    with registry.processing(s010):
        registry.cases.save_case(s.case, s.history)
    assert registry.get_hash("S010") == "hash-S010"
    assert registry.cases.get_case(PB_CASE) == s.case
    assert dict(registry.known_units()) == {"U1": PICKUP_BRAZIL}


def test_e26_reopened_registry_sees_everything_and_resumes(
    tmp_path: Path, resolution: ResolutionThresholds
) -> None:
    path = tmp_path / "r.sqlite3"
    s010 = e1_step(resolution)
    s011 = advanced(s010.case, "S011", Severity.NONE, resolution)
    with SqliteRegistry(path) as a:
        save_in_own_unit(a, s010, anomalies=(ANOMALY_A,), new_units={"U1": PICKUP_BRAZIL})
        save_in_own_unit(a, s011)
        hashes = (a.get_hash("S010"), a.get_hash("S011"))
        units = dict(a.known_units())
        active = a.cases.active_cases()
        history = a.cases.history(PB_CASE)
        anomalies = a.recorded_anomalies()
    assert hashes == ("hash-S010", "hash-S011")
    assert history == (s010.history, s011.history)
    with SqliteRegistry(path) as b:
        assert (b.get_hash("S010"), b.get_hash("S011")) == hashes
        assert dict(b.known_units()) == units
        assert b.cases.active_cases() == active == (s011.case,)
        assert b.cases.history(PB_CASE) == history
        assert b.recorded_anomalies() == anomalies == (ANOMALY_A,)
        with pytest.raises(ValueError, match="S011"), b.processing(commit("S011")):
            pass
        stored = b.cases.get_case(PB_CASE)
        assert stored is not None
        s012 = advanced(stored, "S012", Severity.NONE, resolution)
        save_in_own_unit(b, s012)
        resolved = b.cases.get_case(PB_CASE)
        assert resolved is not None
        assert resolved.state is CaseState.RESOLVED
        assert resolved.clean_streak == 2
        assert resolved.resolved_at == "S012"
        assert b.cases.active_cases() == ()
        assert [row.snapshot_id for row in b.cases.history(PB_CASE)] == ["S010", "S011", "S012"]


# --- T15 · Released units ---


def released(unit_id: str, hour: str, combination: Combination) -> ReleasedUnit:
    """Released unit at 'hour' on 2026-03-02."""
    return ReleasedUnit(
        unidad_id=unit_id,
        modelo=combination.modelo,
        mercado=combination.mercado,
        hora=datetime.fromisoformat(f"2026-03-02T{hour}"),
    )


def snapshot(snapshot_id: str, at: str, shift: str, *releases: ReleasedUnit) -> Snapshot:
    """Snapshot on 2026-03-02 with no units in plant."""
    return Snapshot(
        snapshot_id=snapshot_id,
        timestamp=datetime.fromisoformat(f"2026-03-02T{at}"),
        turno=shift,
        unidades=(),
        liberadas=releases,
    )


U1_PB = released("U1", "09:10", PICKUP_BRAZIL)
E27_U1 = released("U1", "09:10", SEDAN_LOCAL)
E27_U2_SEL = released("U2", "09:40", SEDAN_LOCAL)
E27_U2_SL = released("U2", "12:00", SUV_LOCAL)
E27_U3 = released("U3", "13:00", SUV_LOCAL)
E27_S001 = snapshot("S001", "10:00", "T01", E27_U1, E27_U2_SEL)
E27_S002 = snapshot("S002", "14:00", "T01", E27_U2_SL, E27_U3)


@pytest.fixture
def ctx() -> PlantContext:
    """Plant context from the fixture CSVs and umbrales.yaml."""
    shifts = load_shifts(FIXTURES / "turnos.csv")
    return PlantContext(
        plan=load_plan(FIXTURES / "plan_produccion.csv", shifts),
        shifts=shifts,
        standards=StandardsTable.from_rows(load_standards(FIXTURES / "tiempos_estandar.csv")),
        shipments=ShipmentsTable.from_rows(load_shipments(FIXTURES / "embarques.csv")),
        thresholds=load_thresholds(FIXTURES / "umbrales.yaml"),
    )


def record_in_own_unit(registry: SqliteRegistry, snap: Snapshot) -> None:
    """Record one snapshot's releases in its own committed unit of work."""
    with registry.processing(commit(snap.snapshot_id)):
        registry.releases.record_releases(snap)


def test_e23c_record_releases_outside_processing_raises_and_writes_nothing(registry: SqliteRegistry) -> None:
    with pytest.raises(RuntimeError):
        registry.releases.record_releases(snapshot("S010", "10:00", "T01", U1_PB))
    assert registry.releases.released_so_far() == ()


def test_record_releases_for_another_snapshot_raises_naming_both(registry: SqliteRegistry) -> None:
    """The guard must compare ids for releases too, or they would be stamped with the wrong seq."""
    with registry.processing(commit("S010")):
        with pytest.raises(ValueError) as error:
            registry.releases.record_releases(snapshot("S011", "10:00", "T01", U1_PB))
        assert names_all(str(error.value), "S010", "S011"), str(error.value)
        assert registry.releases.released_so_far() == ()


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(RuntimeError("boom"), id="runtime_error"),
        pytest.param(KeyboardInterrupt(), id="interrupt"),
    ],
)
def test_e25_failure_in_block_discards_releases(
    registry: SqliteRegistry, resolution: ResolutionThresholds, failure: BaseException
) -> None:
    s = e1_step(resolution)
    s010 = snapshot("S010", "10:00", "T01", U1_PB)
    with pytest.raises(type(failure)), registry.processing(commit("S010")):
        registry.releases.record_releases(s010)
        registry.cases.save_case(s.case, s.history)
        raise failure
    assert registry.releases.released_so_far() == ()
    with registry.processing(commit("S010")):
        registry.releases.record_releases(s010)
        registry.cases.save_case(s.case, s.history)
    assert registry.releases.released_so_far() == (U1_PB,)


def test_e26_reopened_registry_returns_the_same_releases(
    tmp_path: Path, resolution: ResolutionThresholds
) -> None:
    path = tmp_path / "r.sqlite3"
    s010 = e1_step(resolution)
    s011 = advanced(s010.case, "S011", Severity.NONE, resolution)
    with SqliteRegistry(path) as a:
        with a.processing(commit("S010", new_units={"U1": PICKUP_BRAZIL})):
            a.releases.record_releases(snapshot("S010", "10:00", "T01", U1_PB))
            a.cases.save_case(s010.case, s010.history)
        with a.processing(commit("S011")):
            a.releases.record_releases(snapshot("S011", "14:00", "T01"))
            a.cases.save_case(s011.case, s011.history)
        releases = a.releases.released_so_far()
    assert releases == (U1_PB,)
    with SqliteRegistry(path) as b:
        assert b.releases.released_so_far() == releases


def test_e27_released_so_far_follows_processing_then_list_order(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    expected = (E27_U1, E27_U2_SEL, E27_U2_SL, E27_U3)
    with SqliteRegistry(path) as first:
        record_in_own_unit(first, E27_S001)
        with first.processing(commit("S002")):
            assert first.releases.released_so_far() == (E27_U1, E27_U2_SEL)
            first.releases.record_releases(E27_S002)
        assert first.releases.released_so_far() == expected
    with SqliteRegistry(path) as second:
        assert second.releases.released_so_far() == expected


def test_e27_compute_metrics_on_stored_releases_counts_first_release(
    registry: SqliteRegistry, ctx: PlantContext
) -> None:
    record_in_own_unit(registry, E27_S001)
    record_in_own_unit(registry, E27_S002)
    s003 = snapshot("S003", "18:00", "T02")
    metrics = compute_metrics(s003, registry.releases.released_so_far(), ctx)
    assert metrics[SEDAN_LOCAL].progress == 2
    assert metrics[SUV_LOCAL].progress == 1


# --- Review fixes ---


def test_current_unit_is_none_outside_processing_and_new_on_every_entry(registry: SqliteRegistry) -> None:
    repo: CaseRepository = registry.cases
    assert registry.current_unit() is None
    assert repo.current_unit() is None
    with pytest.raises(RuntimeError, match="boom"), registry.processing(commit("S010")):
        failed = registry.current_unit()
        assert failed is not None
        assert repo.current_unit() == failed
        raise RuntimeError("boom")
    assert registry.current_unit() is None
    with registry.processing(commit("S010")):
        retried = registry.current_unit()
        assert retried is not None
        assert repo.current_unit() == retried
    with registry.processing(commit("S011")):
        following = registry.current_unit()
        assert following is not None
    assert len({failed, retried, following}) == 3
    assert repo.current_unit() is None


def test_save_case_with_row_of_another_case_raises_naming_both_and_writes_nothing(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    case = opened("S010", Severity.MEDIUM, resolution).case
    row = opened("S010", Severity.HIGH, resolution, combination=SEDAN_LOCAL).history
    with registry.processing(commit("S010")):
        with pytest.raises(ValueError) as error:
            registry.cases.save_case(case, row)
        assert names_all(str(error.value), case.case_id, row.case_id), str(error.value)
        assert registry.cases.get_case(case.case_id) is None
        assert registry.cases.history(case.case_id) == ()
        assert registry.cases.history(row.case_id) == ()


def test_save_case_rejects_an_unvalidated_inconsistent_case_before_writing(
    registry: SqliteRegistry, resolution: ResolutionThresholds
) -> None:
    s = e1_step(resolution)
    fields = {name: getattr(s.case, name) for name in Case.model_fields}
    bad = Case.model_construct(**{**fields, "state": CaseState.RESOLVED, "resolved_at": None})
    with registry.processing(commit("S010")):
        with pytest.raises(ValueError):
            registry.cases.save_case(bad, s.history)
        assert registry.cases.get_case(PB_CASE) is None
        assert registry.cases.history(PB_CASE) == ()


# --- 004 T8 · Schema version 2 (E24) and the notice step's case reads (E29) ---


def table_names(path: Path) -> set[str]:
    """Names of the tables of a SQLite file, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def test_e24a_new_file_has_version_two_and_a_notices_table_and_reopens(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path):
        pass
    assert user_version(path) == 2
    assert "notices" in table_names(path)
    with SqliteRegistry(path) as again:
        assert again.get_hash("S001") is None


def test_e24b_other_version_names_file_found_version_and_two(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("PRAGMA user_version = 7")
    with pytest.raises(ValueError) as error:
        SqliteRegistry(path)
    message = str(error.value)
    assert path.name in message, message
    versions = message.replace(str(path), "").replace(path.name, "")
    assert re.search(r"\b7\b", versions), message
    assert re.search(r"\b2\b", versions), message


def test_e24c_version_one_file_is_rejected_and_left_untouched(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with closing(sqlite3.connect(path)) as conn:
        conn.execute("CREATE TABLE processed_snapshots (snapshot_id TEXT PRIMARY KEY)")
        conn.execute("PRAGMA user_version = 1")
    with pytest.raises(ValueError) as error:
        SqliteRegistry(path)
    message = str(error.value)
    assert path.name in message, message
    versions = message.replace(str(path), "").replace(path.name, "")
    assert re.search(r"\b1\b", versions), message
    assert re.search(r"\b2\b", versions), message
    assert user_version(path) == 1
    assert table_names(path) == {"processed_snapshots"}


def seed_e29(registry: SqliteRegistry) -> None:
    """E29 committed cases, one unit of work per snapshot; history of S007-PB follows the spec."""
    pb, suv, sel_e, pl = "S007-Pickup-Brasil", "S001-SUV-Local", "S009-Sedán-Europa", "S010-Pickup-Local"
    reported_follow_up = (CaseState.FOLLOW_UP, Severity.NONE, "S010")
    steps: dict[str, list[tuple[Case, CaseHistoryRow]]] = {
        "S001": [
            (case_with(suv, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM), history_row(suv, "S001", None))
        ],
        "S005": [
            (
                case_with(
                    suv,
                    CaseState.RESOLVED,
                    Severity.NONE,
                    None,
                    at="S005",
                    reported=(CaseState.RESOLVED, Severity.NONE, "S006"),
                ),
                history_row(suv, "S005", None, minimum=Severity.NONE, state=CaseState.RESOLVED),
            )
        ],
        "S007": [
            (
                case_with(pb, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM),
                history_row(pb, "S007", Stage.PAINT, state=CaseState.OPEN),
            )
        ],
        "S008": [
            (
                case_with(pb, CaseState.FOLLOW_UP, Severity.HIGH, Severity.HIGH, at="S008"),
                history_row(pb, "S008", None, minimum=Severity.HIGH),
            )
        ],
        "S009": [
            (
                case_with(pb, CaseState.FOLLOW_UP, Severity.MEDIUM, Severity.HIGH, at="S009"),
                history_row(pb, "S009", Stage.ASSEMBLY),
            ),
            (
                case_with(sel_e, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM),
                history_row(sel_e, "S009", None, state=CaseState.OPEN),
            ),
        ],
        "S010": [
            (
                case_with(pb, CaseState.FOLLOW_UP, Severity.NONE, Severity.HIGH, at="S010"),
                history_row(pb, "S010", Stage.BODY, minimum=Severity.NONE),
            ),
            (
                case_with(pl, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM),
                history_row(pl, "S010", None, state=CaseState.OPEN),
            ),
        ],
        "S011": [
            (
                case_with(
                    pb, CaseState.RESOLVED, Severity.NONE, None, at="S011", reported=reported_follow_up
                ),
                history_row(pb, "S011", None, minimum=Severity.NONE, state=CaseState.RESOLVED),
            ),
            (
                case_with(
                    sel_e, CaseState.RESOLVED, Severity.NONE, None, at="S011", reported=reported_follow_up
                ),
                history_row(sel_e, "S011", None, minimum=Severity.NONE, state=CaseState.RESOLVED),
            ),
        ],
    }
    for snapshot_id in sorted(steps):
        with registry.processing(commit(snapshot_id)):
            for case, row in steps[snapshot_id]:
                registry.cases.save_case(case, row)


def test_e29a_resolved_unreported_is_unreported_resolved_cases_in_case_order(
    registry: SqliteRegistry,
) -> None:
    seed_e29(registry)
    found = registry.cases.resolved_unreported()
    assert tuple(case.case_id for case in found) == ("S009-Sedán-Europa", "S007-Pickup-Brasil")
    assert all(case.state is CaseState.RESOLVED for case in found)


def test_e29b_last_deviation_row_is_the_latest_row_with_minimum_media_or_more(
    registry: SqliteRegistry,
) -> None:
    """Text order is not severity order ('ninguna' sorts above 'media'), so clean rows must be skipped."""
    seed_e29(registry)
    row = registry.cases.last_deviation_row("S007-Pickup-Brasil")
    assert row is not None
    assert row.snapshot_id == "S009"
    assert row.bottleneck is Stage.ASSEMBLY


def test_e29c_last_deviation_row_of_an_unknown_case_is_none(registry: SqliteRegistry) -> None:
    seed_e29(registry)
    assert registry.cases.last_deviation_row("S999-Pickup-Brasil") is None


def test_e29_last_deviation_row_sees_the_open_units_own_row_after_save(registry: SqliteRegistry) -> None:
    """The pipeline reads it inside 'processing' after 'track', so the unit's own row must be visible."""
    seed_e29(registry)
    pl = "S010-Pickup-Local"
    with registry.processing(commit("S012")):
        registry.cases.save_case(
            case_with(pl, CaseState.FOLLOW_UP, Severity.HIGH, Severity.HIGH, at="S012"),
            history_row(pl, "S012", Stage.QUALITY, minimum=Severity.HIGH),
        )
        row = registry.cases.last_deviation_row(pl)
    assert row is not None
    assert (row.snapshot_id, row.bottleneck) == ("S012", Stage.QUALITY)


def test_e29_the_trackers_port_does_not_gain_the_notice_reads() -> None:
    """'CaseRepository' stays the tracker's port; the new reads sit behind 'NoticeCaseReader'."""
    assert not hasattr(CaseRepository, "resolved_unreported")
    assert not hasattr(CaseRepository, "last_deviation_row")
