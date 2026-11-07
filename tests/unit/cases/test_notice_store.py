"""004 T8: the notice store on the registry's session, its outbox reads and delivery marks (E25-E28)."""

import sqlite3
from collections.abc import Iterator
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.models import SnapshotCommit
from plant_monitor.domain.notices import Notice, PendingDelivery, ShiftReport

from notice_builders import (
    PICKUP_LOCAL_CASE,
    SEDAN_LOCAL_CASE,
    SUV_LOCAL_CASE,
    alert_notice,
    news_notice,
    shift_report,
    silent_notice,
)

ALERT_ID = f"S003-alerta_inmediata-{SEDAN_LOCAL_CASE}"
AWARE = datetime(2026, 3, 2, 18, 0, 5, tzinfo=UTC)
LATER = datetime(2026, 3, 2, 19, 0, tzinfo=UTC)

S003_ALERT = alert_notice("S003", SEDAN_LOCAL_CASE)
S003_SILENT = silent_notice("S003", SUV_LOCAL_CASE)
S003_NEWS = news_notice("S003", PICKUP_LOCAL_CASE)
S004_NEWS = news_notice("S004", SEDAN_LOCAL_CASE)
S004_SILENT = silent_notice("S004", SUV_LOCAL_CASE)
T02_REPORT = shift_report("T02", "S004", news=(SEDAN_LOCAL_CASE,), active=(SEDAN_LOCAL_CASE, SUV_LOCAL_CASE))


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


def commit_e25(registry: SqliteRegistry) -> None:
    """E25: S003 saved with three decisions and no report, then S004 with two decisions and report T02."""
    with registry.processing(commit("S003")):
        registry.notices.save("S003", (S003_ALERT, S003_SILENT, S003_NEWS), None)
    with registry.processing(commit("S004")):
        registry.notices.save("S004", (S004_NEWS, S004_SILENT), T02_REPORT)


def rows_of(path: Path) -> list[tuple[str, str, str, str | None]]:
    """'(notice_id, kind, tipo, case_id)' of every stored row in processing order."""
    with closing(sqlite3.connect(path)) as conn:
        found = conn.execute(
            "SELECT notice_id, kind, tipo, case_id FROM notices ORDER BY seq, idx"
        ).fetchall()
    return [(r[0], r[1], r[2], r[3]) for r in found]


def delivered_text(path: Path, notice_id: str) -> str | None:
    """Raw 'delivered_at' column of one row, read with a fresh connection."""
    with closing(sqlite3.connect(path)) as conn:
        row = conn.execute("SELECT delivered_at FROM notices WHERE notice_id = ?", (notice_id,)).fetchone()
    return None if row is None or row[0] is None else str(row[0])


def names_all(message: str, *names: str) -> bool:
    """True when the message names every given id."""
    return all(name in message for name in names)


# --- E25 · Save and pending ---


def test_e25_for_snapshot_returns_what_was_saved_in_save_order(registry: SqliteRegistry) -> None:
    commit_e25(registry)
    s003: tuple[Notice | ShiftReport, ...] = (S003_ALERT, S003_SILENT, S003_NEWS)
    assert registry.notices.for_snapshot("S003") == s003
    assert registry.notices.for_snapshot("S004") == (S004_NEWS, S004_SILENT, T02_REPORT)
    assert registry.notices.for_snapshot("S999") == ()


def test_e25_rows_carry_kind_tipo_and_a_null_case_for_the_report(tmp_path: Path) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as registry:
        commit_e25(registry)
    assert rows_of(path) == [
        (ALERT_ID, "notice", "alerta_inmediata", SEDAN_LOCAL_CASE),
        (S003_SILENT.notice_id, "notice", "sin_aviso", SUV_LOCAL_CASE),
        (S003_NEWS.notice_id, "notice", "informe_de_turno", PICKUP_LOCAL_CASE),
        (S004_NEWS.notice_id, "notice", "informe_de_turno", SEDAN_LOCAL_CASE),
        (S004_SILENT.notice_id, "notice", "sin_aviso", SUV_LOCAL_CASE),
        ("T02-informe", "report", "informe_de_turno", None),
    ]


def test_e25_pending_is_the_alert_and_the_report_only(registry: SqliteRegistry) -> None:
    commit_e25(registry)
    assert registry.notices.pending() == (
        PendingDelivery(ALERT_ID, S003_ALERT),
        PendingDelivery("T02-informe", T02_REPORT),
    )


# --- E26 · Guards ---


def test_e26a_save_outside_processing_raises_and_writes_nothing(registry: SqliteRegistry) -> None:
    with pytest.raises(RuntimeError):
        registry.notices.save("S003", (S003_ALERT,), None)
    assert registry.notices.for_snapshot("S003") == ()
    assert registry.notices.pending() == ()


def test_e26b_save_with_a_notice_of_another_snapshot_raises_naming_both_and_writes_nothing(
    registry: SqliteRegistry,
) -> None:
    stray = alert_notice("S002", SEDAN_LOCAL_CASE)
    with registry.processing(commit("S003")):
        with pytest.raises(ValueError) as error:
            registry.notices.save("S003", (stray,), None)
        assert names_all(str(error.value), "S003", "S002"), str(error.value)
    assert registry.notices.for_snapshot("S003") == ()
    assert registry.notices.pending() == ()


def test_e26c_second_alert_for_a_case_raises_naming_the_case_and_writes_nothing(
    registry: SqliteRegistry,
) -> None:
    with registry.processing(commit("S003")):
        registry.notices.save("S003", (S003_ALERT,), None)
    second = alert_notice("S004", SEDAN_LOCAL_CASE)
    with registry.processing(commit("S004")), pytest.raises(ValueError, match=SEDAN_LOCAL_CASE):
        registry.notices.save("S004", (S004_SILENT, second), None)
    assert registry.notices.for_snapshot("S004") == ()
    assert registry.notices.pending() == (PendingDelivery(ALERT_ID, S003_ALERT),)


def test_e26d_a_second_save_for_the_snapshot_replaces_its_set(registry: SqliteRegistry) -> None:
    with registry.processing(commit("S003")):
        registry.notices.save("S003", (S003_ALERT, S003_SILENT), None)
        registry.notices.save("S003", (S003_SILENT,), None)
    assert registry.notices.for_snapshot("S003") == (S003_SILENT,)
    assert registry.notices.pending() == ()


def test_e26e_mark_delivered_inside_processing_raises(registry: SqliteRegistry) -> None:
    commit_e25(registry)
    with registry.processing(commit("S005")), pytest.raises(RuntimeError):
        registry.notices.mark_delivered(ALERT_ID, AWARE)
    assert registry.notices.delivered_at(ALERT_ID) is None


def test_e26f_mark_delivered_of_an_unknown_notice_raises_naming_it(registry: SqliteRegistry) -> None:
    with pytest.raises(ValueError, match="S999-alerta_inmediata-X"):
        registry.notices.mark_delivered("S999-alerta_inmediata-X", AWARE)


def test_e26g_pending_inside_processing_raises(registry: SqliteRegistry) -> None:
    commit_e25(registry)
    with registry.processing(commit("S005")), pytest.raises(RuntimeError):
        registry.notices.pending()


def test_e26h_a_report_id_stored_by_another_snapshot_raises_naming_it_and_writes_nothing(
    registry: SqliteRegistry,
) -> None:
    commit_e25(registry)
    clash = shift_report("T02", "S005")
    with registry.processing(commit("S005")), pytest.raises(ValueError, match="T02-informe"):
        registry.notices.save("S005", (), clash)
    assert registry.notices.for_snapshot("S005") == ()
    assert registry.notices.for_snapshot("S004") == (S004_NEWS, S004_SILENT, T02_REPORT)


# --- E27 · Delivery marks ---


def test_e27a_mark_delivered_removes_it_from_pending_keeps_the_first_time_and_survives_reopen(
    tmp_path: Path,
) -> None:
    path = tmp_path / "r.sqlite3"
    with SqliteRegistry(path) as registry:
        commit_e25(registry)
        registry.notices.mark_delivered(ALERT_ID, AWARE)
        assert registry.notices.pending() == (PendingDelivery("T02-informe", T02_REPORT),)
        stored = registry.notices.delivered_at(ALERT_ID)
        assert stored == AWARE
        assert stored is not None
        assert stored.utcoffset() is not None
        registry.notices.mark_delivered(ALERT_ID, LATER)
        assert registry.notices.delivered_at(ALERT_ID) == AWARE
    assert delivered_text(path, ALERT_ID) == "2026-03-02T18:00:05+00:00"
    with SqliteRegistry(path) as reopened:
        assert reopened.notices.pending() == (PendingDelivery("T02-informe", T02_REPORT),)
        assert reopened.notices.delivered_at(ALERT_ID) == AWARE


def test_e27b_a_naive_time_raises_and_the_notice_stays_pending(registry: SqliteRegistry) -> None:
    commit_e25(registry)
    with pytest.raises(ValueError):
        registry.notices.mark_delivered("T02-informe", datetime(2026, 3, 2, 18, 0))
    assert registry.notices.delivered_at("T02-informe") is None
    assert registry.notices.pending()[-1] == PendingDelivery("T02-informe", T02_REPORT)


# --- E28 · Rollback ---


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(RuntimeError("boom"), id="runtime_error"),
        pytest.param(KeyboardInterrupt(), id="interrupt"),
    ],
)
def test_e28_failure_after_save_leaves_nothing_and_the_snapshot_commits_again(
    registry: SqliteRegistry, failure: BaseException
) -> None:
    with pytest.raises(type(failure)), registry.processing(commit("S003")):
        registry.notices.save("S003", (S003_ALERT,), None)
        raise failure
    assert registry.notices.for_snapshot("S003") == ()
    assert registry.notices.pending() == ()
    with registry.processing(commit("S003")):
        registry.notices.save("S003", (S003_ALERT,), None)
    assert registry.notices.pending() == (PendingDelivery(ALERT_ID, S003_ALERT),)


def test_e26i_two_rows_with_one_notice_id_in_a_save_raise_duplicate_and_write_nothing(
    registry: SqliteRegistry,
) -> None:
    """Review finding: a repeated id in one save is not 'another snapshot'."""
    with registry.processing(commit("S003")):
        with pytest.raises(ValueError) as error:
            registry.notices.save("S003", (S003_SILENT, S003_SILENT), None)
        message = str(error.value)
        assert S003_SILENT.notice_id in message, message
        assert "duplicate" in message.lower(), message
        assert "another snapshot" not in message, message
    assert registry.notices.for_snapshot("S003") == ()
