"""013 E11 (R2, R3, R14): 'read_notice' reads one notice from a registry file, read-only."""

import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from incident_runs import AC1, EV_T02, SUV_EUROPE, incident_run

from plant_monitor.cases.registry.notice_reader import read_notice
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.notices import Reason, ShiftReport
from plant_monitor.domain.stored import StoredNotice

ALERT_ID = "S005-alerta_inmediata-S005-SUV-Europa"
NEWS_ID = "S006-informe_de_turno-S005-SUV-Europa"


def test_e11_reader_gives_a_stored_notice_a_report_none_and_value_errors(tmp_path: Path) -> None:
    """013 E11 (a)-(e): notice facts, report, unknown id, a table missing, a path missing."""
    path = tmp_path / "registry.sqlite3"
    with incident_run(path=path) as run:
        run.through(3)
        run.step(4, lambda d: run.raise_cause(d, CauseCategory.QUALITY_HOLD, SUV_EUROPE, EV_T02))
        run.through(6, first=5)
    before = path.read_bytes()

    stored = read_notice(path, ALERT_ID)
    assert isinstance(stored, StoredNotice)
    assert stored.notice.motivo == (Reason.LOGBOOK,)
    assert [row.snapshot_id for row in stored.history] == ["S005", "S006"]
    assert dict(stored.order) == {f"S00{n}": n for n in range(1, 7)}
    assert [cause.active_cause_id for cause in stored.causes] == [AC1]
    assert dict(stored.links) == {AC1: "S005"}
    assert stored.cited is not None
    assert (stored.cited.set_at, stored.cited.active_cause_id) == ("S005", AC1)

    report = read_notice(path, "T03-informe")
    assert isinstance(report, ShiftReport)
    assert report.turno_id == "T03"
    assert [news.notice_id for news in report.novedades] == [NEWS_ID]

    assert read_notice(path, "S005-sin_aviso-X") is None
    assert path.read_bytes() == before

    broken = tmp_path / "broken.sqlite3"
    shutil.copy(path, broken)
    with closing(sqlite3.connect(broken)) as conn:
        conn.execute("DROP TABLE active_cause_links")
        conn.commit()
    with pytest.raises(ValueError, match="active_cause_links"):
        read_notice(broken, ALERT_ID)

    missing = tmp_path / "absent.sqlite3"
    with pytest.raises(ValueError, match="registry not found"):
        read_notice(missing, ALERT_ID)
    assert not missing.exists()
