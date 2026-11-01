"""002 T9: pure anomaly checks for shift mismatch, future stage entry and unit identity (E15-E18, E21)."""

from collections.abc import Mapping
from datetime import datetime
from types import MappingProxyType

from plant_monitor.domain.enums import AnomalyKind, Market, Model, Stage
from plant_monitor.domain.models import Anomaly, Combination, ReleasedUnit, Shift, Snapshot, Unit
from plant_monitor.runner.checks import check_shift, check_stage_entries, check_unit_identity

SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
SUV_LOCAL = Combination(modelo=Model.SUV, mercado=Market.LOCAL)
PICKUP_EUROPE = Combination(modelo=Model.PICKUP, mercado=Market.EUROPE)
S005_AT = "2026-03-03T02:00"


def dt(text: str) -> datetime:
    """Naive plant-local datetime from ISO text."""
    return datetime.fromisoformat(text)


def unit(
    unit_id: str,
    combo: Combination = SEDAN_LOCAL,
    *,
    stage: Stage = Stage.QUALITY,
    since: str = "2026-03-02T09:00",
    rework: int = 0,
    shipment: str = "LOC-0302",
) -> Unit:
    """Unit in process varying only the fields the checks read."""
    return Unit(
        unidad_id=unit_id,
        modelo=combo.modelo,
        mercado=combo.mercado,
        color="Gris Plata",
        etapa=stage,
        ingreso_etapa=dt(since),
        retrabajos=rework,
        embarque_asignado=shipment,
    )


def released(unit_id: str, combo: Combination = SEDAN_LOCAL, hour: str = "2026-03-02T09:00") -> ReleasedUnit:
    """Released unit as listed in a snapshot's liberadas."""
    return ReleasedUnit(unidad_id=unit_id, modelo=combo.modelo, mercado=combo.mercado, hora=dt(hour))


def snapshot(
    snapshot_id: str,
    timestamp: str = "2026-03-02T10:00",
    turno: str = "T01",
    units: tuple[Unit, ...] = (),
    releases: tuple[ReleasedUnit, ...] = (),
) -> Snapshot:
    """Snapshot built in Python instead of a JSON file."""
    return Snapshot(
        snapshot_id=snapshot_id, timestamp=dt(timestamp), turno=turno, unidades=units, liberadas=releases
    )


def shift(turno_id: str, start: str, end: str, mid: str, closing: str) -> Shift:
    """Row of turnos.csv."""
    return Shift(
        turno_id=turno_id, inicio=dt(start), fin=dt(end), snapshot_medio=mid, snapshot_cierre=closing
    )


def names_time(detail: str, value: datetime) -> bool:
    """True if `detail` contains `value` in ISO (T) or space-separated form, at least to the minute."""
    return value.isoformat(timespec="minutes") in detail or value.strftime("%Y-%m-%d %H:%M") in detail


T02 = shift("T02", "2026-03-02T14:00", "2026-03-02T22:00", "S003", "S004")


# --- check_shift (Q-18) ---


def test_e15_snapshot_turno_differs_from_calendar_gives_shift_mismatch() -> None:
    s003 = snapshot("S003", "2026-03-02T18:00", turno="T01")
    anomaly = check_shift(s003, T02)
    assert anomaly is not None
    assert anomaly.kind is AnomalyKind.SHIFT_MISMATCH
    assert anomaly.snapshot_id == "S003"
    assert "T01" in anomaly.detail
    assert "T02" in anomaly.detail


def test_check_shift_matching_turno_gives_none() -> None:
    assert check_shift(snapshot("S003", "2026-03-02T18:00", turno="T02"), T02) is None


# --- check_stage_entries (Q-19) ---


def test_e16_future_stage_entry_gives_one_anomaly_naming_unit_entry_and_timestamp() -> None:
    u = unit("U00051", Combination(modelo=Model.SUV, mercado=Market.BRAZIL), since="2026-03-03T03:00")
    s005 = snapshot("S005", S005_AT, "T03", (u,))
    anomalies = check_stage_entries(s005)
    assert len(anomalies) == 1
    anomaly = anomalies[0]
    assert anomaly.kind is AnomalyKind.STAGE_ENTRY_AFTER_SNAPSHOT
    assert anomaly.snapshot_id == "S005"
    assert "U00051" in anomaly.detail
    assert names_time(anomaly.detail, dt("2026-03-03T03:00"))
    assert names_time(anomaly.detail, dt(S005_AT))


def test_e16b_stage_entry_equal_to_timestamp_is_not_an_anomaly() -> None:
    u = unit("U00051", Combination(modelo=Model.SUV, mercado=Market.BRAZIL), since=S005_AT)
    assert check_stage_entries(snapshot("S005", S005_AT, "T03", (u,))) == ()


def test_e16b_repainting_unit_with_future_entry_gives_one_anomaly() -> None:
    u = unit(
        "U00052",
        Combination(modelo=Model.SUV, mercado=Market.BRAZIL),
        stage=Stage.PAINT,
        since="2026-03-03T03:00",
        rework=1,
    )
    anomalies = check_stage_entries(snapshot("S005", S005_AT, "T03", (u,)))
    assert len(anomalies) == 1
    assert anomalies[0].kind is AnomalyKind.STAGE_ENTRY_AFTER_SNAPSHOT
    assert "U00052" in anomalies[0].detail


def test_stage_entry_in_the_past_is_not_an_anomaly() -> None:
    u = unit("U1", since="2026-03-02T21:00")
    assert check_stage_entries(snapshot("S005", S005_AT, "T03", (u,))) == ()


def test_one_stage_entry_anomaly_per_future_unit() -> None:
    units = (
        unit("UF1", since="2026-03-03T02:01"),
        unit("UP", since="2026-03-03T01:00"),
        unit("UF2", since="2026-03-03T05:00"),
    )
    anomalies = check_stage_entries(snapshot("S005", S005_AT, "T03", units))
    assert len(anomalies) == 2
    assert all(a.kind is AnomalyKind.STAGE_ENTRY_AFTER_SNAPSHOT for a in anomalies)
    assert all(a.snapshot_id == "S005" for a in anomalies)
    assert sum("UF1" in a.detail for a in anomalies) == 1
    assert sum("UF2" in a.detail for a in anomalies) == 1
    assert not any("UP" in a.detail for a in anomalies)


def test_stage_entry_check_ignores_liberadas() -> None:
    late_release = released("R1", hour="2026-03-03T05:00")
    assert check_stage_entries(snapshot("S005", S005_AT, "T03", releases=(late_release,))) == ()


# --- check_unit_identity (Q-20) ---


def assert_combination_changed(anomaly: Anomaly, snapshot_id: str, unit_id: str) -> None:
    """Kind, snapshot and unit of a unit_combination_changed anomaly."""
    assert anomaly.kind is AnomalyKind.UNIT_COMBINATION_CHANGED
    assert anomaly.snapshot_id == snapshot_id
    assert unit_id in anomaly.detail


def test_e17_first_snapshot_has_no_anomaly_and_sights_every_unit() -> None:
    s001 = snapshot("S001", releases=(released("U1"), released("U2")))
    anomalies, sightings = check_unit_identity(s001, {})
    assert anomalies == ()
    assert sightings == {"U1": SEDAN_LOCAL, "U2": SEDAN_LOCAL}


def test_e17_unit_released_again_in_new_combination_gives_one_anomaly() -> None:
    s002 = snapshot(
        "S002", "2026-03-02T14:00", releases=(released("U2", SUV_LOCAL), released("U3", SUV_LOCAL))
    )
    anomalies, sightings = check_unit_identity(s002, {"U1": SEDAN_LOCAL, "U2": SEDAN_LOCAL})
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S002", "U2")
    assert "Sedán/Local" in anomalies[0].detail
    assert "SUV/Local" in anomalies[0].detail
    assert sightings == {"U3": SUV_LOCAL}


def test_e18_unit_in_unidades_and_liberadas_with_new_combination_gives_one_anomaly() -> None:
    s002 = snapshot(
        "S002",
        "2026-03-02T14:00",
        units=(unit("U2", SUV_LOCAL, stage=Stage.YARD),),
        releases=(released("U2", SUV_LOCAL),),
    )
    anomalies, sightings = check_unit_identity(s002, {"U2": SEDAN_LOCAL})
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S002", "U2")
    assert "U2" not in sightings
    assert sightings == {}


def test_e18_later_snapshot_with_new_combination_gives_another_anomaly() -> None:
    s003 = snapshot("S003", "2026-03-02T18:00", "T02", units=(unit("U2", SUV_LOCAL, stage=Stage.YARD),))
    anomalies, sightings = check_unit_identity(s003, {"U2": SEDAN_LOCAL})
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S003", "U2")
    assert sightings == {}


def test_e21_unit_first_in_unidades_then_released_in_new_combination() -> None:
    s001 = snapshot("S001", units=(unit("U9", SEDAN_LOCAL, stage=Stage.QUALITY),))
    first_anomalies, first_sightings = check_unit_identity(s001, {})
    assert first_anomalies == ()
    assert first_sightings == {"U9": SEDAN_LOCAL}
    s002 = snapshot("S002", "2026-03-02T14:00", releases=(released("U9", SUV_LOCAL),))
    anomalies, sightings = check_unit_identity(s002, first_sightings)
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S002", "U9")
    assert "Sedán/Local" in anomalies[0].detail
    assert "SUV/Local" in anomalies[0].detail
    assert sightings == {}


def test_same_combination_again_is_neither_anomaly_nor_new_sighting() -> None:
    s002 = snapshot("S002", units=(unit("U1"),), releases=(released("U1"),))
    assert check_unit_identity(s002, {"U1": SEDAN_LOCAL}) == ((), {})


def test_new_sightings_exclude_units_already_known() -> None:
    s002 = snapshot("S002", units=(unit("U1"), unit("U5", SUV_LOCAL)))
    anomalies, sightings = check_unit_identity(s002, {"U1": SEDAN_LOCAL})
    assert anomalies == ()
    assert sightings == {"U5": SUV_LOCAL}


def test_unidades_scanned_before_liberadas_within_a_snapshot() -> None:
    s001 = snapshot("S001", units=(unit("U4", SEDAN_LOCAL),), releases=(released("U4", SUV_LOCAL),))
    anomalies, sightings = check_unit_identity(s001, {})
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S001", "U4")
    assert "Sedán/Local" in anomalies[0].detail
    assert "SUV/Local" in anomalies[0].detail
    assert sightings == {"U4": SEDAN_LOCAL}


def test_first_sighting_within_liberadas_list_order_wins() -> None:
    s001 = snapshot("S001", releases=(released("U6", SUV_LOCAL), released("U6", SEDAN_LOCAL)))
    anomalies, sightings = check_unit_identity(s001, {})
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S001", "U6")
    assert sightings == {"U6": SUV_LOCAL}


def test_at_most_one_anomaly_per_unit_per_snapshot_with_two_new_combinations() -> None:
    s002 = snapshot("S002", units=(unit("U2", SUV_LOCAL),), releases=(released("U2", PICKUP_EUROPE),))
    anomalies, sightings = check_unit_identity(s002, {"U2": SEDAN_LOCAL})
    assert len(anomalies) == 1
    assert_combination_changed(anomalies[0], "S002", "U2")
    assert sightings == {}


def test_one_anomaly_per_changed_unit() -> None:
    s002 = snapshot("S002", units=(unit("U1", SUV_LOCAL),), releases=(released("U2", SUV_LOCAL),))
    anomalies, _ = check_unit_identity(s002, {"U1": SEDAN_LOCAL, "U2": SEDAN_LOCAL})
    assert len(anomalies) == 2
    assert all(a.kind is AnomalyKind.UNIT_COMBINATION_CHANGED for a in anomalies)
    assert sum("U1" in a.detail for a in anomalies) == 1
    assert sum("U2" in a.detail for a in anomalies) == 1


def test_input_mapping_is_never_mutated() -> None:
    first_seen = {"U1": SEDAN_LOCAL}
    s002 = snapshot("S002", units=(unit("U1", SUV_LOCAL), unit("U7", PICKUP_EUROPE)))
    check_unit_identity(s002, first_seen)
    assert first_seen == {"U1": SEDAN_LOCAL}


def test_accepts_a_read_only_mapping() -> None:
    first_seen: Mapping[str, Combination] = MappingProxyType({"U1": SEDAN_LOCAL})
    anomalies, sightings = check_unit_identity(snapshot("S002", units=(unit("U8"),)), first_seen)
    assert anomalies == ()
    assert sightings == {"U8": SEDAN_LOCAL}


def test_identity_check_is_deterministic() -> None:
    s002 = snapshot("S002", units=(unit("U1", SUV_LOCAL),), releases=(released("U3", SUV_LOCAL),))
    first_seen = {"U1": SEDAN_LOCAL}
    assert check_unit_identity(s002, first_seen) == check_unit_identity(s002, first_seen)
