"""Pure anomaly checks over one snapshot (Q-18, Q-19, Q-20)."""

from collections.abc import Iterator, Mapping

from plant_monitor.domain.enums import AnomalyKind
from plant_monitor.domain.models import Anomaly, Combination, Shift, Snapshot


def _label(combination: Combination) -> str:
    return f"{combination.modelo}/{combination.mercado}"


def check_shift(snapshot: Snapshot, shift: Shift) -> Anomaly | None:
    """Anomaly when the snapshot's `turno` differs from the calendar's shift."""
    if snapshot.turno == shift.turno_id:
        return None
    return Anomaly(
        kind=AnomalyKind.SHIFT_MISMATCH,
        snapshot_id=snapshot.snapshot_id,
        detail=f"turno {snapshot.turno}, turnos.csv {shift.turno_id}",
    )


def check_stage_entries(snapshot: Snapshot) -> tuple[Anomaly, ...]:
    """One anomaly per unit whose stage entry is after the snapshot timestamp."""
    return tuple(
        Anomaly(
            kind=AnomalyKind.STAGE_ENTRY_AFTER_SNAPSHOT,
            snapshot_id=snapshot.snapshot_id,
            detail=(
                f"unit {unit.unidad_id} entered {unit.etapa} at "
                f"{unit.ingreso_etapa.isoformat(timespec='minutes')}, after snapshot at "
                f"{snapshot.timestamp.isoformat(timespec='minutes')}"
            ),
        )
        for unit in snapshot.unidades
        if unit.ingreso_etapa > snapshot.timestamp
    )


def _sightings(snapshot: Snapshot) -> Iterator[tuple[str, Combination]]:
    """Unit identities in scan order: `unidades` first, then `liberadas`."""
    for unit in snapshot.unidades:
        yield unit.unidad_id, Combination(modelo=unit.modelo, mercado=unit.mercado)
    for released in snapshot.liberadas:
        yield released.unidad_id, Combination(modelo=released.modelo, mercado=released.mercado)


def check_unit_identity(
    snapshot: Snapshot, first_seen: Mapping[str, Combination]
) -> tuple[tuple[Anomaly, ...], dict[str, Combination]]:
    """Anomalies for units whose combination changed, plus this snapshot's new sightings."""
    new_units: dict[str, Combination] = {}
    anomalies: dict[str, Anomaly] = {}
    for unit_id, combination in _sightings(snapshot):
        first = first_seen[unit_id] if unit_id in first_seen else new_units.get(unit_id)
        if first is None:
            new_units[unit_id] = combination
        elif first != combination and unit_id not in anomalies:
            anomalies[unit_id] = Anomaly(
                kind=AnomalyKind.UNIT_COMBINATION_CHANGED,
                snapshot_id=snapshot.snapshot_id,
                detail=f"unit {unit_id} first seen as {_label(first)}, now {_label(combination)}",
            )
    return tuple(anomalies.values()), new_units
