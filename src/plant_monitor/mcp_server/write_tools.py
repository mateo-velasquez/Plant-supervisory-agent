"""Write tools: the agent's notice texts go to the frame's writer, never anywhere else (R8, R9)."""

import json
from collections.abc import Sequence

from pydantic import BaseModel

from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.mcp_server.context import FrameHolder, NoticeTextWriter, ToolContext


class NewsText(BaseModel):
    """One item of 'emit_shift_report': the text of a news case."""

    case_id: str
    texto: str


class NoNoticeWriter(RejectedRequest):
    """The frame carries no notice writer, so there is nothing to write."""

    def __init__(self) -> None:
        super().__init__("no notice texts are being written at this snapshot")


def _writer(frames: FrameHolder) -> NoticeTextWriter:
    writer = frames.current().notices
    if writer is None:
        raise NoNoticeWriter()
    return writer


def _result(written: Sequence[str], writer: NoticeTextWriter) -> str:
    return json.dumps(
        {"escritos": list(written), "pendientes": list(writer.missing())},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def emit_alert(ctx: ToolContext, frames: FrameHolder, case_id: str, texto: str) -> str:
    """Write the text of this snapshot's alert for 'case_id'."""
    writer = _writer(frames)
    return _result([writer.write_alert(case_id, texto)], writer)


def emit_shift_report(ctx: ToolContext, frames: FrameHolder, textos: Sequence[NewsText]) -> str:
    """Write the texts of the whole shift report at once."""
    writer = _writer(frames)
    return _result(writer.write_news([(item.case_id, item.texto) for item in textos]), writer)
