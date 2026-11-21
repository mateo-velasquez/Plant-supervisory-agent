"""016 T4: the forecast step in the runner, its failure containment and its idempotency (E10-E12)."""

import logging
import re
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from forecast_builders import SYN, P, failing_sink, fc, of, plan_rows, syn_context

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.registry.forecasts import read_forecasts
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.enums import ShiftPosition
from plant_monitor.domain.forecast import ForecastRow
from plant_monitor.domain.models import Shift, Snapshot, SnapshotCommit
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.snapshot import load_snapshot
from plant_monitor.metrics.forecast import ForecastConfig
from plant_monitor.runner import forecast_step
from plant_monitor.runner.forecast_step import ForecastSink, ForecastStep
from plant_monitor.runner.pipeline import ThresholdPipeline
from plant_monitor.runner.ports import SnapshotPipeline
from plant_monitor.runner.series import RunAborted, RunSummary, run_series

from builders import released_payload, snapshot_payload, write_snapshot

PLAN = plan_rows(24)
E1_RELEASES = (13, 13, 13, 13, 10, 10, 10, 10, 10)  # prog(4) = 52, prog(8) = 92
E7A_RELEASES = (13, 13, 12, 12, 9, 9, 9, 9)  # prog(4) = 50, prog(8) = 86
STATE_TABLES = ("cases", "case_history", "notices")
type SinkWrap = Callable[[ForecastSink], ForecastSink]
type PipelineWrap = Callable[[ThresholdPipeline], SnapshotPipeline]


class RaisedAtEight:
    """Runs decide, sets P's case 'raised' in the S008 delta, then finishes (E10)."""

    def __init__(self, inner: ThresholdPipeline) -> None:
        self._inner = inner

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        decision = self._inner.decide(snapshot, shift, position)
        if snapshot.snapshot_id == "S008" and decision.delta is not None:
            cases = tuple(
                case.model_copy(update={"raised": True}) if case.combination == P else case
                for case in decision.delta.cases
            )
            decision = replace(decision, delta=replace(decision.delta, cases=cases))
        self._inner.finish(decision)


class RaiseAfter:
    """Delegates 'process' and then raises at one snapshot, after its forecast was saved (E12)."""

    def __init__(self, inner: SnapshotPipeline, fail_at: str) -> None:
        self._inner = inner
        self._fail_at = fail_at

    def process(self, snapshot: Snapshot, shift: Shift, position: ShiftPosition) -> None:
        self._inner.process(snapshot, shift, position)
        if snapshot.snapshot_id == self._fail_at:
            raise RuntimeError("boom")


def write_series(directory: Path, releases: Sequence[int], *, name: str = "") -> list[Arrival]:
    """One snapshot file per entry of 'releases' (P units released at each), on SYN's calendar."""
    directory.mkdir(parents=True, exist_ok=True)
    arrivals: list[Arrival] = []
    for seq, count in enumerate(releases, start=1):
        snapshot_id = f"S{seq:03d}"
        stamp = datetime(2026, 3, 2, 6, 0) + timedelta(hours=4 * seq)
        released = [
            released_payload(
                unidad_id=f"{name}{snapshot_id}-{i:02d}",
                modelo="Pickup",
                mercado="Local",
                hora=(stamp - timedelta(hours=1)).isoformat(timespec="minutes"),
            )
            for i in range(count)
        ]
        payload = snapshot_payload(
            [],
            released,
            snapshot_id=snapshot_id,
            timestamp=stamp.isoformat(timespec="minutes"),
            turno=f"T{(seq + 1) // 2:02d}",
        )
        path = write_snapshot(directory, payload, f"{snapshot_id}.json")
        arrivals.append(Arrival(orden=seq, snapshot_id=snapshot_id, archivo=path, recibido=stamp))
    return arrivals


def make_pipeline(
    registry: SqliteRegistry,
    *,
    with_step: bool = True,
    sink_wrap: SinkWrap | None = None,
    pipeline_wrap: PipelineWrap | None = None,
) -> SnapshotPipeline:
    """Production-style wiring over SYN with W = 4, H = 3 and the guard open."""
    ctx = syn_context(PLAN)
    step: ForecastStep | None = None
    if with_step:
        sink: ForecastSink = registry.forecasts
        if sink_wrap is not None:
            sink = sink_wrap(sink)
        policy = HeldOutPolicy.from_calendar(SYN, "T12", is_open=True)
        step = ForecastStep.build(ForecastConfig(window=4, horizon=3), registry.forecasts, sink, ctx, policy)
    pipeline = ThresholdPipeline.from_registry(registry, ctx, forecast=step)
    return pipeline if pipeline_wrap is None else pipeline_wrap(pipeline)


def run(
    path: Path,
    arrivals: Sequence[Arrival],
    *,
    with_step: bool = True,
    sink_wrap: SinkWrap | None = None,
    pipeline_wrap: PipelineWrap | None = None,
) -> RunSummary:
    """Run 'arrivals' through the runner on the registry at 'path'."""
    with SqliteRegistry(path) as registry:
        pipeline = make_pipeline(
            registry, with_step=with_step, sink_wrap=sink_wrap, pipeline_wrap=pipeline_wrap
        )
        return run_series(arrivals, SYN, registry, pipeline)


def stored(path: Path) -> tuple[ForecastRow, ...]:
    """The stored forecast rows, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        rows = read_forecasts(conn)
    assert rows is not None
    return rows


def dump(path: Path, table: str) -> list[tuple[object, ...]]:
    """All rows of a table, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def test_e10_the_final_decision_feeds_the_step_and_none_changes_no_other_table(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path / "in", E7A_RELEASES)
    with_step, without = tmp_path / "with.sqlite3", tmp_path / "without.sqlite3"
    run(with_step, arrivals, pipeline_wrap=RaisedAtEight)
    run(without, arrivals, with_step=False, pipeline_wrap=RaisedAtEight)
    rows = stored(with_step)
    assert len(rows) == 72
    last = of([r for r in rows if r.snapshot_id == "S008"])
    assert (last.status, last.effective_severity.value) == ("suppressed", "critica")
    assert stored(without) == ()
    for table in STATE_TABLES:
        assert dump(with_step, table) == dump(without, table)


def test_e10_finish_with_a_step_refuses_a_decision_without_delta(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path / "in", E7A_RELEASES[:1])
    path = tmp_path / "r.sqlite3"
    snapshot = load_snapshot(arrivals[0].archivo)
    with SqliteRegistry(path) as registry:
        pipeline = ThresholdPipeline.from_registry(
            registry,
            syn_context(PLAN),
            forecast=ForecastStep.build(
                ForecastConfig(window=4, horizon=3),
                registry.forecasts,
                registry.forecasts,
                syn_context(PLAN),
                HeldOutPolicy.from_calendar(SYN, "T12", is_open=True),
            ),
        )
        commit = SnapshotCommit(snapshot_id="S001", content_hash="h", anomalies=(), new_units={})
        with registry.processing(commit):
            decision = pipeline.decide(snapshot, SYN[0], ShiftPosition.MID)
            with pytest.raises(ValueError):
                pipeline.finish(replace(decision, delta=None))
    assert stored(path) == ()


@pytest.mark.parametrize("failure", ["forecast_raises", "save_raises_after_four_rows"])
def test_e11_a_failed_forecast_is_logged_and_skipped_while_the_snapshot_commits(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    arrivals = write_series(tmp_path / "in", E1_RELEASES)
    path = tmp_path / "r.sqlite3"
    clean = tmp_path / "clean.sqlite3"
    run(clean, arrivals)
    sink_wrap: SinkWrap | None = None
    if failure == "forecast_raises":
        real = forecast_step.forecast_snapshot

        def explode(**kwargs: Any) -> tuple[ForecastRow, ...]:
            if kwargs["snapshot_id"] == "S008":
                raise ValueError("boom")
            return real(**kwargs)

        monkeypatch.setattr(forecast_step, "forecast_snapshot", explode)
    else:
        sink_wrap = lambda inner: failing_sink(inner, fail_at="S008")  # noqa: E731
    with caplog.at_level(logging.WARNING):
        summary = run(path, arrivals, sink_wrap=sink_wrap)
    skipped = [r.getMessage() for r in caplog.records if "forecast skipped" in r.getMessage()]
    assert skipped == ["forecast skipped for S008 (ValueError)"]
    assert {"S008", "S009"} <= set(summary.processed)
    assert {r.snapshot_id for r in stored(path)} == {f"S{k:03d}" for k in (1, 2, 3, 4, 5, 6, 7, 9)}
    assert len(stored(path)) == 72
    assert dump(path, "notices") == dump(clean, "notices")


def test_e9_a_closed_guard_stops_the_projection_at_the_last_open_snapshot(tmp_path: Path) -> None:
    """016 E9 (R4; Q-133; FR-40): with T06 refused no row, point or warning names S011 or later."""
    arrivals = write_series(tmp_path / "in", (*E1_RELEASES, 10))
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as registry:
        policy = HeldOutPolicy.from_calendar(SYN, "T06", is_open=False)
        step = ForecastStep.build(
            ForecastConfig(window=4, horizon=3),
            registry.forecasts,
            registry.forecasts,
            syn_context(PLAN),
            policy,
        )
        pipeline = ThresholdPipeline.from_registry(registry, syn_context(PLAN), forecast=step)
        run_series(arrivals, SYN, registry, pipeline)
    rows = stored(path)
    assert {r.snapshot_id for r in rows} == {f"S{k:03d}" for k in range(1, 11)}
    assert not re.search(r"S(?:01[1-9]|0[2-9]\d|[1-9]\d\d)", " ".join(r.model_dump_json() for r in rows))
    assert [p.snapshot_id for p in of([r for r in rows if r.snapshot_id == "S008"]).points] == [
        "S009",
        "S010",
    ]


def test_risk_a_repeated_unit_counts_once_in_the_window_start_of_the_rate(tmp_path: Path) -> None:
    """Risk: raw rows at n - W double-count a repeated unit, skewing 'rate' (R2/I4, Q-20, criterio 1)."""
    ids = ("ab", "cd", "ae", "fg", "hi", "bj", "kl", "mn")  # 'a' repeats at S003 (<= 4), 'b' at S006 (> 4)
    directory = tmp_path / "in"
    directory.mkdir()
    arrivals: list[Arrival] = []
    for seq, letters in enumerate(ids, start=1):
        snapshot_id = f"S{seq:03d}"
        stamp = datetime(2026, 3, 2, 6, 0) + timedelta(hours=4 * seq)
        hora = (stamp - timedelta(hours=1)).isoformat(timespec="minutes")
        released = [
            released_payload(unidad_id=f"U-{letter}", modelo="Pickup", mercado="Local", hora=hora)
            for letter in letters
        ]
        payload = snapshot_payload(
            [],
            released,
            snapshot_id=snapshot_id,
            timestamp=stamp.isoformat(timespec="minutes"),
            turno=f"T{(seq + 1) // 2:02d}",
        )
        path = write_snapshot(directory, payload, f"{snapshot_id}.json")
        arrivals.append(Arrival(orden=seq, snapshot_id=snapshot_id, archivo=path, recibido=stamp))
    db = tmp_path / "r.sqlite3"
    run(db, arrivals)
    last = of([r for r in stored(db) if r.snapshot_id == "S008"])
    distinct_at_4 = len({letter for letters in ids[:4] for letter in letters})
    distinct_at_8 = len({letter for letters in ids for letter in letters})
    assert (distinct_at_4, distinct_at_8) == (7, 14)  # raw rows through S004 would be 8
    assert last.basis is not None
    assert last.basis.rate == (distinct_at_8 - distinct_at_4) / 4


def test_e12_repeats_write_nothing_and_an_aborted_snapshot_leaves_no_rows(tmp_path: Path) -> None:
    arrivals = write_series(tmp_path / "in", E1_RELEASES[:8])
    baseline = tmp_path / "base.sqlite3"
    run(baseline, arrivals)
    rows = stored(baseline)
    assert len(rows) == 72
    assert of([r for r in rows if r.snapshot_id == "S008"]) == of(fc(8, 92, 52, plan=PLAN))
    # the same bytes, then a different S008 under the same id
    run(baseline, arrivals)
    assert stored(baseline) == rows
    changed = write_series(tmp_path / "changed", (13, 13, 13, 13, 10, 10, 10, 11), name="x")
    run(baseline, [arrival for arrival in changed if arrival.snapshot_id == "S008"])
    assert stored(baseline) == rows
    # abort after the S008 forecast was saved, then resume
    aborted = tmp_path / "aborted.sqlite3"
    with pytest.raises(RunAborted):
        run(aborted, arrivals, pipeline_wrap=lambda p: RaiseAfter(p, "S008"))
    assert {r.snapshot_id for r in stored(aborted)} == {f"S{k:03d}" for k in range(1, 8)}
    run(aborted, arrivals)
    assert stored(aborted) == rows
