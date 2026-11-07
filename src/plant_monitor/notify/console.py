"""Console channel: readable lines that never raise on encoding."""

import sys
from typing import TextIO

from plant_monitor.domain.notices import Notice, ShiftReport


class ConsoleNotifier:
    """Prints alerts and reports; 'None' stream means 'sys.stdout' at call time."""

    def __init__(self, stream: TextIO | None = None) -> None:
        self._stream = stream

    def alert(self, notice: Notice) -> None:
        self._write(f"ALERTA {notice.notice_id}: {notice.texto}")

    def report(self, report: ShiftReport) -> None:
        lines = [f"INFORME {report.turno_id} ({report.snapshot_id})", "Novedades:"]
        lines += [f"  - {news.case_id}: {news.texto}" for news in report.novedades]
        lines.append("Casos activos:")
        lines += [
            f"  - {row.case_id}: {row.estado} severidad {row.severidad} (máxima {row.severidad_maxima})"
            for row in report.casos_activos
        ]
        self._write("\n".join(lines))

    def _write(self, text: str) -> None:
        stream = self._stream if self._stream is not None else sys.stdout
        encoding = getattr(stream, "encoding", None) or "utf-8"
        safe = text.encode(encoding, "backslashreplace").decode(encoding)
        stream.write(safe + "\n")
        stream.flush()
