"""Write tools: the agent's notice texts go to the frame's writer, never anywhere else (R8, R9)."""

import json
from collections.abc import Sequence

from pydantic import BaseModel

from plant_monitor.domain.causes import Cause, CauseCategory, CauseScope, Evidence
from plant_monitor.domain.enums import Market, Model, Stage
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.notices import notice_brief_item
from plant_monitor.mcp_server.context import (
    FrameHolder,
    JudgmentResult,
    NoticeTextWriter,
    SnapshotFrame,
    ToolContext,
)


class NewsText(BaseModel):
    """One item of 'emit_shift_report': the text of a news case."""

    case_id: str
    texto: str


class NoNoticeWriter(RejectedRequest):
    """The frame carries no notice writer, so there is nothing to write."""

    def __init__(self) -> None:
        super().__init__("no notice texts are being written at this snapshot")


class NoJudgmentWriter(RejectedRequest):
    """The frame carries no judgment writer, so there is nothing to record."""

    def __init__(self) -> None:
        super().__init__("no judgment is being recorded at this snapshot")


class CauseIsDefault(RejectedRequest):
    """'no_declarada' is the default, never a cause to set or raise (R3, R5)."""

    @classmethod
    def for_set(cls) -> CauseIsDefault:
        """Refusal for 'set_cause'."""
        return cls("no_declarada cannot be set: it is the default when no logbook names a cause")

    @classmethod
    def for_raise(cls) -> CauseIsDefault:
        """Refusal for 'raise_severity'."""
        return cls("no_declarada cannot be raised: a raise needs a cause a logbook names")


def _json(data: dict[str, object]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _cited(ctx: ToolContext, frame: SnapshotFrame, bitacora: str, fragmento: str) -> Evidence:
    """Verify the citation against the logbooks readable at the frame's snapshot; return it stripped."""
    ctx.logbooks.verify_citation(bitacora, fragmento, frame.snapshot_id)
    return Evidence(bitacora=bitacora, fragmento=fragmento.strip())


def _outcome(result: JudgmentResult) -> dict[str, object]:
    return {"avisos": [notice_brief_item(n) for n in result.changed], "pendientes": list(result.pending)}


def set_cause(
    ctx: ToolContext,
    frames: FrameHolder,
    case_id: str,
    categoria: CauseCategory,
    etapa: Stage,
    bitacora: str,
    fragmento: str,
) -> str:
    """Record the cited cause of 'case_id' from a verified logbook fragment."""
    frame = frames.current()
    if frame.causes is None:
        raise NoJudgmentWriter()
    if categoria is CauseCategory.UNDECLARED:
        raise CauseIsDefault.for_set()
    evidence = _cited(ctx, frame, bitacora, fragmento)
    result = frame.causes.set_cause(case_id, Cause(categoria=categoria, etapa=etapa), evidence)
    cause: dict[str, object] = {"categoria": categoria.value, "etapa": etapa.value}
    return _json({"caso": case_id, "causa": cause, **_outcome(result)})


def raise_severity(
    ctx: ToolContext,
    frames: FrameHolder,
    categoria: CauseCategory,
    etapa: Stage,
    modelo: Model,
    mercado: Market | None,
    bitacora: str,
    fragmento: str,
) -> str:
    """Open an active cause over a model, stage and optional market from a verified fragment."""
    frame = frames.current()
    if frame.raises is None:
        raise NoJudgmentWriter()
    if categoria is CauseCategory.UNDECLARED:
        raise CauseIsDefault.for_raise()
    evidence = _cited(ctx, frame, bitacora, fragmento)
    scope = CauseScope(modelo=modelo, etapa=etapa, mercado=mercado)
    result = frame.raises.raise_severity(categoria, scope, evidence)
    return _json({"causa_activa": result.active_cause_id, "casos": list(result.case_ids), **_outcome(result)})


def lift_severity_raise(
    ctx: ToolContext, frames: FrameHolder, active_cause_id: str, bitacora: str, fragmento: str
) -> str:
    """Lift an active cause from a verified fragment of a later logbook."""
    frame = frames.current()
    if frame.raises is None:
        raise NoJudgmentWriter()
    evidence = _cited(ctx, frame, bitacora, fragmento)
    result = frame.raises.lift(active_cause_id, evidence)
    return _json(
        {"causa_activa": result.active_cause_id, "levantada_en": result.lifted_at, **_outcome(result)}
    )


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
