"""004 T9: file, console and composite notifiers (E30-E33)."""

import io
import json
import os
from pathlib import Path

import pytest

from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.notify.composite import CompositeNotifier
from plant_monitor.notify.console import ConsoleNotifier
from plant_monitor.notify.file import FileNotifier
from plant_monitor.notify.port import Notifier

from notice_builders import (
    PICKUP_BRAZIL_CASE,
    PICKUP_LOCAL_CASE,
    SEDAN_LOCAL_CASE,
    SUV_LOCAL_CASE,
    alert_notice,
    shift_report,
)

MINUS = chr(0x2212)
TIMES = chr(0xD7)
E22A_TEXT = (
    f"Pickup {TIMES} Brasil escaló a crítica en S020 por gap: gap {MINUS}12 u ({MINUS}40 %), retraso 1 día. "
    "Causa no declarada, etapa montaje."
)
E23_ALERT = alert_notice("S020", "S015-Pickup-Brasil", texto=E22A_TEXT)
ALERT_A = alert_notice("S003", SEDAN_LOCAL_CASE)
ALERT_B = alert_notice("S004", PICKUP_BRAZIL_CASE)
T01_REPORT = shift_report(
    "T01", "S002", news=(SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE), active=(SEDAN_LOCAL_CASE,)
)
T02_REPORT = shift_report(
    "T02",
    "S004",
    news=(SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE),
    active=(SEDAN_LOCAL_CASE, SUV_LOCAL_CASE, PICKUP_LOCAL_CASE),
)


class RecordingNotifier:
    """Appends '(name, channel, id)' to a shared log and raises 'error' on 'fail_on' ('alert' or 'report')."""

    def __init__(self, name: str, log: list[tuple[str, str, str]], fail_on: str | None = None) -> None:
        self.name = name
        self.log = log
        self.fail_on = fail_on

    def alert(self, notice: Notice) -> None:
        self.log.append((self.name, "alert", notice.notice_id))
        if self.fail_on == "alert":
            raise OSError("alert channel down")

    def report(self, report: ShiftReport) -> None:
        self.log.append((self.name, "report", report.turno_id))
        if self.fail_on == "report":
            raise OSError("report channel down")


def temp_files(directory: Path) -> list[Path]:
    """Leftover '.tmp' files in 'directory'."""
    return sorted(directory.glob("*.tmp"))


# --- E30 · File adapter, report ---


def test_e30a_report_is_written_as_contract_json_with_lf_and_one_trailing_newline(tmp_path: Path) -> None:
    out = tmp_path / "out"
    FileNotifier(out).report(T01_REPORT)
    data = (out / "informe_T01.json").read_bytes()
    assert json.loads(data) == T01_REPORT.model_dump(mode="json")
    assert "Sedán".encode() in data
    assert b"\r" not in data
    assert data.endswith(b"\n")
    assert not data.endswith(b"\n\n")


def test_e30a_delivering_the_same_report_again_is_byte_identical_and_leaves_no_temp_file(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    notifier = FileNotifier(out)
    notifier.report(T01_REPORT)
    first = (out / "informe_T01.json").read_bytes()
    notifier.report(T01_REPORT)
    assert (out / "informe_T01.json").read_bytes() == first
    assert temp_files(out) == []


def test_e30b_a_failed_replace_propagates_keeps_the_target_and_leaves_no_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    notifier = FileNotifier(out)
    notifier.report(T01_REPORT)
    first = (out / "informe_T01.json").read_bytes()

    def failing_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)
    changed = shift_report("T01", "S002", news=(SEDAN_LOCAL_CASE,))
    with pytest.raises(OSError, match="disk full"):
        notifier.report(changed)
    assert (out / "informe_T01.json").read_bytes() == first
    assert temp_files(out) == []


# --- E31 · File adapter, alerts ---


def test_e31_alerts_are_json_lines_in_delivery_order_without_duplicates_across_instances(
    tmp_path: Path,
) -> None:
    out = tmp_path / "out"
    notifier = FileNotifier(out)
    for alert in (ALERT_A, ALERT_A, ALERT_B):
        notifier.alert(alert)
    target = out / "alertas.jsonl"
    data = target.read_bytes()
    assert b"\r" not in data
    assert data.endswith(b"\n")
    assert not data.endswith(b"\n\n")
    lines = data.decode("utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [
        ALERT_A.model_dump(mode="json"),
        ALERT_B.model_dump(mode="json"),
    ]
    FileNotifier(out).alert(ALERT_B)
    assert target.read_bytes() == data
    assert temp_files(out) == []


# --- E32 · Console adapter ---


def test_e32a_console_writes_the_alert_line_and_the_report_with_news_and_active_cases() -> None:
    stream = io.StringIO()
    console = ConsoleNotifier(stream)
    console.alert(E23_ALERT)
    console.report(T02_REPORT)
    text = stream.getvalue()
    assert "S020-alerta_inmediata-S015-Pickup-Brasil" in text
    assert E22A_TEXT in text
    assert "T02" in text
    assert all(news.texto in text for news in T02_REPORT.novedades)
    assert all(row.case_id in text for row in T02_REPORT.casos_activos)


def test_e32b_console_on_a_cp1252_stream_escapes_what_it_cannot_encode_instead_of_raising() -> None:
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    ConsoleNotifier(stream).alert(E23_ALERT)
    stream.flush()
    data = raw.getvalue()
    assert rb"\u2212" in data
    assert b"\xd7" in data


# --- E33 · Composite ---


def test_e33a_composite_calls_each_notifier_in_order() -> None:
    log: list[tuple[str, str, str]] = []
    composite = CompositeNotifier((RecordingNotifier("first", log), RecordingNotifier("second", log)))
    composite.alert(ALERT_A)
    assert log == [("first", "alert", ALERT_A.notice_id), ("second", "alert", ALERT_A.notice_id)]


def test_e33b_composite_propagates_the_first_failure_and_skips_the_later_notifiers() -> None:
    log: list[tuple[str, str, str]] = []
    first: Notifier = RecordingNotifier("first", log, fail_on="report")
    composite = CompositeNotifier((first, RecordingNotifier("second", log)))
    with pytest.raises(OSError, match="report channel down"):
        composite.report(T01_REPORT)
    assert log == [("first", "report", "T01")]
