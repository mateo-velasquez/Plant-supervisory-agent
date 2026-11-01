"""002 T4: run types ShiftPosition, AnomalyKind, Anomaly and SnapshotCommit."""

import dataclasses

import pytest
from pydantic import ValidationError

from plant_monitor.domain.enums import AnomalyKind, Market, Model, ShiftPosition
from plant_monitor.domain.models import Anomaly, Combination, SnapshotCommit

SEDAN_LOCAL = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)


def test_shift_position_values() -> None:
    assert [p.value for p in ShiftPosition] == ["mid", "closing"]
    assert ShiftPosition.MID.value == "mid"
    assert ShiftPosition.CLOSING.value == "closing"
    assert isinstance(ShiftPosition.MID, str)


def test_anomaly_kind_has_exactly_the_four_spec_values() -> None:
    assert [k.value for k in AnomalyKind] == [
        "repeated_with_different_content",
        "shift_mismatch",
        "stage_entry_after_snapshot",
        "unit_combination_changed",
    ]


def test_anomaly_kind_members_by_name() -> None:
    assert AnomalyKind.REPEATED_WITH_DIFFERENT_CONTENT.value == "repeated_with_different_content"
    assert AnomalyKind.SHIFT_MISMATCH.value == "shift_mismatch"
    assert AnomalyKind.STAGE_ENTRY_AFTER_SNAPSHOT.value == "stage_entry_after_snapshot"
    assert AnomalyKind.UNIT_COMBINATION_CHANGED.value == "unit_combination_changed"
    assert isinstance(AnomalyKind.SHIFT_MISMATCH, str)


def test_anomaly_kind_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        AnomalyKind("missing_snapshot")


def test_anomaly_parses_kind_from_its_value() -> None:
    anomaly = Anomaly.model_validate(
        {"kind": "shift_mismatch", "snapshot_id": "S003", "detail": "T01 vs T02"}
    )
    assert anomaly.kind is AnomalyKind.SHIFT_MISMATCH
    assert anomaly.snapshot_id == "S003"
    assert anomaly.detail == "T01 vs T02"


def test_anomaly_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        Anomaly.model_validate({"kind": "missing_snapshot", "snapshot_id": "S003", "detail": "x"})


def test_anomaly_is_frozen() -> None:
    anomaly = Anomaly(kind=AnomalyKind.SHIFT_MISMATCH, snapshot_id="S003", detail="T01 vs T02")
    with pytest.raises(ValidationError):
        setattr(anomaly, "detail", "changed")  # noqa: B010


def test_anomaly_equal_values_are_equal_and_hash_alike() -> None:
    first = Anomaly(kind=AnomalyKind.UNIT_COMBINATION_CHANGED, snapshot_id="S002", detail="U2")
    second = Anomaly(kind=AnomalyKind.UNIT_COMBINATION_CHANGED, snapshot_id="S002", detail="U2")
    assert first == second
    assert hash(first) == hash(second)


def test_snapshot_commit_is_a_dataclass_with_the_plan_fields_in_order() -> None:
    assert dataclasses.is_dataclass(SnapshotCommit)
    names = [field.name for field in dataclasses.fields(SnapshotCommit)]
    assert names == ["snapshot_id", "content_hash", "anomalies", "new_units"]


def test_snapshot_commit_holds_hash_anomalies_and_new_units() -> None:
    anomaly = Anomaly(kind=AnomalyKind.SHIFT_MISMATCH, snapshot_id="S001", detail="T02 vs T01")
    commit = SnapshotCommit("S001", "ab" * 32, (anomaly,), {"U1": SEDAN_LOCAL})
    assert commit.snapshot_id == "S001"
    assert commit.content_hash == "ab" * 32
    assert commit.anomalies == (anomaly,)
    assert dict(commit.new_units) == {"U1": SEDAN_LOCAL}


def test_snapshot_commit_accepts_no_anomalies_and_no_new_units() -> None:
    commit = SnapshotCommit(snapshot_id="S002", content_hash="cd" * 32, anomalies=(), new_units={})
    assert commit.anomalies == ()
    assert dict(commit.new_units) == {}


def test_snapshot_commit_is_frozen() -> None:
    commit = SnapshotCommit(snapshot_id="S001", content_hash="ab" * 32, anomalies=(), new_units={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(commit, "content_hash", "ef" * 32)  # noqa: B010
