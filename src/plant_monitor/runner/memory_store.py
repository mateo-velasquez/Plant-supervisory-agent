"""In-memory `ProcessedStore` for tests and for runs without persistence."""

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from types import MappingProxyType

from plant_monitor.domain.models import Anomaly, Combination, SnapshotCommit


class InMemoryProcessedStore:
    """Dict-backed store; the commit is applied only after the block exits cleanly."""

    def __init__(self, hashes: Mapping[str, str] | None = None) -> None:
        self._hashes: dict[str, str] = dict(hashes or {})
        self._units: dict[str, Combination] = {}
        self._anomalies: list[Anomaly] = []

    def get_hash(self, snapshot_id: str) -> str | None:
        return self._hashes.get(snapshot_id)

    def known_units(self) -> Mapping[str, Combination]:
        return MappingProxyType(dict(self._units))

    def record_anomaly(self, anomaly: Anomaly) -> None:
        self._add_anomalies((anomaly,))

    def _add_anomalies(self, anomalies: Iterable[Anomaly]) -> None:
        """Append anomalies not yet recorded, keyed on (kind, snapshot_id, detail)."""
        seen = {(a.kind, a.snapshot_id, a.detail) for a in self._anomalies}
        for anomaly in anomalies:
            key = (anomaly.kind, anomaly.snapshot_id, anomaly.detail)
            if key not in seen:
                seen.add(key)
                self._anomalies.append(anomaly)

    @contextmanager
    def processing(self, commit: SnapshotCommit) -> Iterator[None]:
        if commit.snapshot_id in self._hashes:
            raise ValueError(f"snapshot {commit.snapshot_id} is already marked as processed")
        yield
        self._hashes[commit.snapshot_id] = commit.content_hash
        self._add_anomalies(commit.anomalies)
        for unit_id, combination in commit.new_units.items():
            self._units.setdefault(unit_id, combination)

    def recorded_anomalies(self) -> tuple[Anomaly, ...]:
        """Test accessor: every anomaly recorded so far, in order."""
        return tuple(self._anomalies)
