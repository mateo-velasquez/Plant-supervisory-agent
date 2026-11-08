"""005 T3: 'check_ids' refuses held-out shifts and snapshots while the policy is closed (E5a, E5f, FR-40)."""

import pytest

from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.held_out import check_ids

from builders import held_out_policy


def test_e5_a_closed_policy_refuses_a_held_out_shift() -> None:
    with pytest.raises(DataLoadError) as info:
        check_ids(held_out_policy("T03"), shifts=["T02", "T03"], snapshots=[], where="x.yaml")
    message = str(info.value)
    assert "x.yaml" in message
    assert "T03" in message
    assert "held out" in message


def test_closed_policy_refuses_a_held_out_snapshot() -> None:
    """Snapshots are checked too, not only shifts (the golden and run source pass both)."""
    with pytest.raises(DataLoadError, match=r"S005.*held out"):
        check_ids(held_out_policy("T03"), shifts=[], snapshots=["S004", "S005"], where="x.yaml")


def test_names_the_first_refused_id_in_sorted_order() -> None:
    with pytest.raises(DataLoadError) as info:
        check_ids(held_out_policy("T02"), shifts=["T03", "T02"], snapshots=[], where="x.yaml")
    assert "T02" in str(info.value)
    assert "T03" not in str(info.value)


def test_e5_f_open_policy_refuses_nothing() -> None:
    policy = held_out_policy("T03", is_open=True)
    check_ids(policy, shifts=["T02", "T03"], snapshots=["S005"], where="x")  # must not raise


def test_allowed_ids_pass_on_a_closed_policy() -> None:
    check_ids(held_out_policy("T03"), shifts=["T01", "T02"], snapshots=["S001", "S004"], where="x")
