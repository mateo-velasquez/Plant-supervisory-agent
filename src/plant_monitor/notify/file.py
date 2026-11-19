"""File channel: one JSON file per report and a JSON-lines file of alerts, both idempotent."""

import json
from pathlib import Path

from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.notify.atomic import write_atomic

_ALERTS_FILE = "alertas.jsonl"
_NEWLINE = b"\n"


class FileNotifier:
    """Writes 'informe_<turno_id>.json' and 'alertas.jsonl' atomically, with LF bytes."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def report(self, report: ShiftReport) -> None:
        data = report.model_dump_json(indent=2).encode("utf-8") + _NEWLINE
        write_atomic(self._directory / f"informe_{report.turno_id}.json", data)

    def alert(self, notice: Notice) -> None:
        target = self._directory / _ALERTS_FILE
        existing = target.read_bytes() if target.exists() else b""
        lines = existing.splitlines()
        if any(json.loads(line)["notice_id"] == notice.notice_id for line in lines):
            return
        lines.append(notice.model_dump_json().encode("utf-8"))
        write_atomic(target, _NEWLINE.join(lines) + _NEWLINE)
