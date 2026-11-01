"""Series runner: orders, deduplicates, checks and delegates each snapshot to the pipeline."""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import NamedTuple

from plant_monitor.domain.calendar import snapshot_position
from plant_monitor.domain.enums import AnomalyKind, ShiftPosition
from plant_monitor.domain.models import Anomaly, Combination, Shift, SnapshotCommit
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import Arrival
from plant_monitor.ingestion.hashing import content_hash
from plant_monitor.ingestion.snapshot import parse_snapshot
from plant_monitor.runner.checks import check_shift, check_stage_entries, check_unit_identity
from plant_monitor.runner.ports import ProcessedStore, SnapshotPipeline

logger = logging.getLogger(__name__)


class Resolved(NamedTuple):
    """An arrival matched to its calendar shift and position."""

    arrival: Arrival
    shift: Shift
    position: ShiftPosition


@dataclass(frozen=True)
class RunSummary:
    """Outcome of a run: snapshot ids processed and skipped, and the anomalies found."""

    processed: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    anomalies: tuple[Anomaly, ...] = ()


class RunAborted(Exception):
    """Run stopped at `snapshot_id`; earlier snapshots stay processed, this one does not."""

    def __init__(self, snapshot_id: str, cause: Exception, summary: RunSummary) -> None:
        super().__init__(snapshot_id, cause, summary)
        self.snapshot_id = snapshot_id
        self.cause = cause
        self.summary = summary

    def __str__(self) -> str:
        return f"run aborted at {self.snapshot_id}: {self.cause}"


@dataclass
class _Progress:
    """Mutable accumulator behind the frozen `RunSummary`."""

    processed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)

    def summary(self) -> RunSummary:
        return RunSummary(tuple(self.processed), tuple(self.skipped), tuple(self.anomalies))


def _resolve_upfront(arrivals: Sequence[Arrival], shifts: Sequence[Shift]) -> list[Resolved]:
    """Check files and calendar for every arrival; one DataLoadError lists all problems."""
    resolved: list[Resolved] = []
    problems: list[str] = []
    for arrival in arrivals:
        if not arrival.archivo.is_file():
            problems.append(f"missing file {arrival.archivo}")
        try:
            shift, position = snapshot_position(shifts, arrival.snapshot_id)
        except ValueError as exc:
            problems.append(str(exc))
        else:
            resolved.append(Resolved(arrival, shift, position))
    if problems:
        raise DataLoadError("; ".join(problems))
    return resolved


def _warn_anomaly(anomaly: Anomaly) -> None:
    logger.warning("%s %s: %s", anomaly.snapshot_id, anomaly.kind, anomaly.detail)


def _skip_repeat(
    arrival: Arrival, new_hash: str, stored_hash: str, store: ProcessedStore, progress: _Progress
) -> None:
    """Q-10: a repeat with other bytes is an anomaly; the first version is kept."""
    anomaly = Anomaly(
        kind=AnomalyKind.REPEATED_WITH_DIFFERENT_CONTENT,
        snapshot_id=arrival.snapshot_id,
        detail=f"hash {new_hash} differs from first processed version (hash {stored_hash}), which is kept",
    )
    store.record_anomaly(anomaly)
    progress.anomalies.append(anomaly)
    logger.warning(
        "%s repeated with different content (hash %s); first processed version (hash %s) kept",
        arrival.snapshot_id,
        new_hash,
        stored_hash,
    )
    progress.skipped.append(arrival.snapshot_id)


def _handle_arrival(
    resolved: Resolved,
    store: ProcessedStore,
    pipeline: SnapshotPipeline,
    first_seen: dict[str, Combination],
    progress: _Progress,
) -> None:
    """Process or skip one arrival; any Exception is wrapped by the caller."""
    arrival, shift, position = resolved
    data = arrival.archivo.read_bytes()
    digest = content_hash(data)
    stored = store.get_hash(arrival.snapshot_id)
    if stored == digest:
        logger.info("%s skipped: already processed", arrival.snapshot_id)
        progress.skipped.append(arrival.snapshot_id)
        return
    if stored is not None:
        _skip_repeat(arrival, digest, stored, store, progress)
        return

    snapshot = parse_snapshot(data, arrival.archivo)
    if snapshot.snapshot_id != arrival.snapshot_id:
        raise DataLoadError(
            f"{arrival.archivo}: field 'snapshot_id': file holds {snapshot.snapshot_id}, "
            f"llegadas.csv says {arrival.snapshot_id}"
        )

    identity_anomalies, new_units = check_unit_identity(snapshot, first_seen)
    anomalies = (
        *filter(None, [check_shift(snapshot, shift)]),
        *check_stage_entries(snapshot),
        *identity_anomalies,
    )
    for anomaly in anomalies:
        _warn_anomaly(anomaly)
    progress.anomalies.extend(anomalies)

    commit = SnapshotCommit(arrival.snapshot_id, digest, anomalies, MappingProxyType(new_units))
    with store.processing(commit):
        pipeline.process(snapshot, shift, position)

    first_seen.update(new_units)
    progress.processed.append(arrival.snapshot_id)
    logger.info("%s processed: %s %s", arrival.snapshot_id, shift.turno_id, position)


def run_series(
    arrivals: Sequence[Arrival],
    shifts: Sequence[Shift],
    store: ProcessedStore,
    pipeline: SnapshotPipeline,
) -> RunSummary:
    """Process the arrivals in `orden`; RunAborted on a per-snapshot failure, DataLoadError upfront."""
    resolved = _resolve_upfront(sorted(arrivals, key=lambda a: a.orden), shifts)
    first_seen = dict(store.known_units())
    progress = _Progress()
    for item in resolved:
        try:
            _handle_arrival(item, store, pipeline, first_seen, progress)
        except Exception as exc:
            raise RunAborted(item.arrival.snapshot_id, exc, progress.summary()) from exc
    return progress.summary()
