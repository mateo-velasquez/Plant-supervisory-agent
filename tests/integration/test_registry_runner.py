"""003 T18: run_series + SqliteRegistry + CaseTracker, uninterrupted vs interrupted and resumed (E30)."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

import pytest

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.tracker import CaseDelta, CaseTracker
from plant_monitor.domain.cases import Case, CaseHistoryRow, CaseState
from plant_monitor.domain.enums import Severity, ShiftPosition
from plant_monitor.domain.models import Shift, Snapshot
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext, compute_metrics
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds
from plant_monitor.runner.series import RunAborted, RunSummary, run_series

from builders import released_payload, snapshot_payload, write_snapshot

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "plant"
SERIES = ("S001", "S002", "S003", "S004", "S005", "S006")
HEADERS: dict[str, tuple[str, str]] = {
    "S001": ("2026-03-02T10:00", "T01"),
    "S002": ("2026-03-02T14:00", "T01"),
    "S003": ("2026-03-02T18:00", "T02"),
    "S004": ("2026-03-02T22:00", "T02"),
    "S005": ("2026-03-03T02:00", "T03"),
    "S006": ("2026-03-03T06:00", "T03"),
}
SEL_FIRST = "S001-Sedán-Local"
SEL_SECOND = "S006-Sedán-Local"
SEE = "S002-Sedán-Europa"

type RowView = tuple[str, CaseState, Severity, float, float | None, int]


class TrackingPipeline:
    """Minimal 003 pipeline: releases → metrics → record releases → track; can fail after track."""

    def __init__(
        self, registry: SqliteRegistry, ctx: PlantContext, fail_after_track_on: str | None = None
    ) -> None:
        self.registry = registry
        self.ctx = ctx
        self.tracker = CaseTracker(registry.cases, ctx.thresholds.resolucion)
        self.fail_after_track_on = fail_after_track_on
        self.deltas: list[CaseDelta] = []

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        metrics = compute_metrics(snapshot, self.registry.releases.released_so_far(), self.ctx)
        self.registry.releases.record_releases(snapshot)
        self.deltas.append(self.tracker.track(snapshot.snapshot_id, metrics, frozenset()))
        if snapshot.snapshot_id == self.fail_after_track_on:
            raise RuntimeError(f"pipeline failed after track on {snapshot.snapshot_id}")


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


@pytest.fixture
def arrivals(tmp_path: Path) -> list[Arrival]:
    """E30 series S001-S006: no units in plant; S004 releases 30 Sedán/Local units L001-L030."""
    directory = tmp_path / "snapshots"
    directory.mkdir()
    s004_released = [
        released_payload(
            unidad_id=f"L{i:03d}", modelo="Sedán", mercado="Local", hora=f"2026-03-02T15:{i:02d}"
        )
        for i in range(1, 31)
    ]
    result: list[Arrival] = []
    for orden, sid in enumerate(SERIES, start=1):
        timestamp, turno = HEADERS[sid]
        released = s004_released if sid == "S004" else []
        payload = snapshot_payload([], released, snapshot_id=sid, timestamp=timestamp, turno=turno)
        path = write_snapshot(directory, payload, f"{sid}.json")
        result.append(
            Arrival(orden=orden, snapshot_id=sid, archivo=path, recibido=datetime.fromisoformat(timestamp))
        )
    return result


def shifts() -> list[Shift]:
    """Fixture turnos.csv: T01-T03 over S001-S006."""
    return load_shifts(FIXTURES / "turnos.csv")


def view(row: CaseHistoryRow) -> RowView:
    """History row as (snapshot, state, effective severity, gap units, gap % to 0.1, streak)."""
    pct = None if row.gap_pct is None else round(row.gap_pct, 1)
    return (row.snapshot_id, row.state, row.effective_severity, row.gap_units, pct, row.clean_streak)


def stored_case_ids(path: Path) -> set[str]:
    """Every case ID in a closed registry file, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return {str(r[0]) for r in conn.execute("SELECT case_id FROM cases")}


def run_uninterrupted(path: Path, arrivals: list[Arrival], ctx: PlantContext) -> RunSummary:
    """Run U on `path` with a healthy pipeline."""
    with SqliteRegistry(path) as registry:
        return run_series(arrivals, shifts(), registry, TrackingPipeline(registry, ctx))


def run_interrupted(path: Path, arrivals: list[Arrival], ctx: PlantContext) -> RunAborted:
    """Run I1 on `path`: the pipeline raises after `track` on S004."""
    with SqliteRegistry(path) as registry, pytest.raises(RunAborted) as info:
        run_series(arrivals, shifts(), registry, TrackingPipeline(registry, ctx, fail_after_track_on="S004"))
    return info.value


# --- T18 · Runner integration with failure and resume (E30) ---


def test_e30_uninterrupted_run_tracks_sedan_local_and_sedan_europa(
    tmp_path: Path, arrivals: list[Arrival], ctx: PlantContext
) -> None:
    path = tmp_path / "u.sqlite3"
    summary = run_uninterrupted(path, arrivals, ctx)
    assert summary.processed == SERIES
    with SqliteRegistry(path) as u:
        assert [view(r) for r in u.cases.history(SEL_FIRST)] == [
            ("S001", CaseState.OPEN, Severity.MEDIUM, -6.0, -16.7, 0),
            ("S002", CaseState.FOLLOW_UP, Severity.HIGH, -12.0, -33.3, 0),
            ("S003", CaseState.ESCALATED, Severity.CRITICAL, -18.0, -50.0, 0),
            ("S004", CaseState.ESCALATED, Severity.NONE, 6.0, 16.7, 1),
            ("S005", CaseState.RESOLVED, Severity.NONE, 0.0, 0.0, 2),
        ]
        first = u.cases.get_case(SEL_FIRST)
        assert first is not None
        assert (first.state, first.resolved_at) == (CaseState.RESOLVED, "S005")
        assert [view(r) for r in u.cases.history(SEL_SECOND)] == [
            ("S006", CaseState.OPEN, Severity.MEDIUM, -6.0, -16.7, 0)
        ]
        assert u.cases.get_case("S001-Sedán-Europa") is None
        assert [view(r) for r in u.cases.history(SEE)][:2] == [
            ("S002", CaseState.OPEN, Severity.HIGH, -4.0, -33.3, 0),
            ("S003", CaseState.ESCALATED, Severity.CRITICAL, -6.0, -50.0, 0),
        ]


def test_e30_interrupted_run_keeps_only_snapshots_before_the_failure(
    tmp_path: Path, arrivals: list[Arrival], ctx: PlantContext
) -> None:
    path = tmp_path / "i.sqlite3"
    aborted = run_interrupted(path, arrivals, ctx)
    assert aborted.snapshot_id == "S004"
    with SqliteRegistry(path) as i:
        assert [sid for sid in SERIES if i.get_hash(sid) is not None] == ["S001", "S002", "S003"]
        case = i.cases.get_case(SEL_FIRST)
        assert case is not None
        assert case.state is CaseState.ESCALATED
        assert len(i.cases.history(SEL_FIRST)) == 3
        assert i.releases.released_so_far() == ()


def test_e30_resumed_run_matches_the_uninterrupted_run(
    tmp_path: Path, arrivals: list[Arrival], ctx: PlantContext
) -> None:
    u_path = tmp_path / "u.sqlite3"
    i_path = tmp_path / "i.sqlite3"
    run_uninterrupted(u_path, arrivals, ctx)
    run_interrupted(i_path, arrivals, ctx)
    with SqliteRegistry(i_path) as i:
        resumed = run_series(arrivals, shifts(), i, TrackingPipeline(i, ctx))
    assert resumed.processed == ("S004", "S005", "S006")
    assert resumed.skipped == ("S001", "S002", "S003")

    u_ids = stored_case_ids(u_path)
    assert {SEL_FIRST, SEL_SECOND, SEE} <= u_ids
    assert stored_case_ids(i_path) == u_ids
    with SqliteRegistry(u_path) as u, SqliteRegistry(i_path) as i:
        u_cases: dict[str, Case | None] = {cid: u.cases.get_case(cid) for cid in u_ids}
        assert {cid: i.cases.get_case(cid) for cid in u_ids} == u_cases
        assert {cid: i.cases.history(cid) for cid in u_ids} == {cid: u.cases.history(cid) for cid in u_ids}
        assert i.cases.active_cases() == u.cases.active_cases()
        assert len(i.releases.released_so_far()) == 30
        assert i.releases.released_so_far() == u.releases.released_so_far()
