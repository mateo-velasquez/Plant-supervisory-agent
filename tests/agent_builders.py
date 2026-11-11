"""Minimal doubles and reply builders for 007 loop tests (fake tool port, progress, scripted replies)."""

import json
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from incident_runs import F2, F5
from pydantic import TypeAdapter

from plant_monitor.agents.fake_model import FakeModel
from plant_monitor.agents.loop import Coordinator, LoopConfig, ToolPort
from plant_monitor.agents.model import ModelReply, TextBlock, ToolUseBlock
from plant_monitor.domain.proposals import Proposal, ValidatedProposal
from plant_monitor.mcp_server.server import READ_TOOLS
from plant_monitor.mcp_server.types import ToolOutcome, ToolSpec
from plant_monitor.telemetry.usage import Usage

JUDGMENT_NAMES = ("set_cause", "raise_severity", "lift_severity_raise")
EMIT_NAMES = ("emit_alert", "emit_shift_report")
WRITE_NAMES = (*JUDGMENT_NAMES, *EMIT_NAMES)
OFFERED = (*READ_TOOLS, *WRITE_NAMES, "apply_proposal")
ALERT_ID = "S003-alerta_inmediata-S001-Sedán-Local"
USAGE = Usage(input_tokens=100, output_tokens=20)


class FakeProgress:
    """Required and missing notice ids; an emit tool empties 'missing', a judgment tool adds 'creates'."""

    def __init__(self, *pending: str, creates: Sequence[str] = ()) -> None:
        self.pending = list(pending)
        self.ids = list(pending)
        self.creates = tuple(creates)

    def required(self) -> tuple[str, ...]:
        return tuple(self.ids)

    def missing(self) -> tuple[str, ...]:
        return tuple(self.pending)

    def judged(self) -> None:
        """A judgment write put new texts back in play."""
        self.ids.extend(self.creates)
        self.pending.extend(self.creates)


class FakeTools:
    """A tool port that records calls and answers from a table ('ok' by default)."""

    def __init__(
        self,
        progress: FakeProgress,
        answers: Mapping[str, ToolOutcome] | None = None,
        offered: Sequence[str] = OFFERED,
    ) -> None:
        self.progress = progress
        self.answers = dict(answers or {})
        self.offered = tuple(offered)
        self.calls: list[tuple[str, Mapping[str, object]]] = []

    async def list_tools(self) -> tuple[ToolSpec, ...]:
        return tuple(ToolSpec(name, f"{name} tool", {"type": "object"}) for name in self.offered)

    async def call(self, name: str, arguments: Mapping[str, object]) -> ToolOutcome:
        self.calls.append((name, arguments))
        outcome = self.answers.get(name, ToolOutcome("ok", False))
        if not outcome.is_error:
            if name in JUDGMENT_NAMES:
                self.progress.judged()
            elif name in EMIT_NAMES:
                self.progress.pending.clear()
        return outcome

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.calls]

    def opener(self) -> Callable[[], AbstractAsyncContextManager[ToolPort]]:
        @asynccontextmanager
        async def open_tools() -> AsyncIterator[ToolPort]:
            yield self

        return open_tools


def tool(name: str, arguments: Mapping[str, object], tool_use_id: str = "tu-1") -> ModelReply:
    """A reply that calls one tool."""
    return ModelReply((ToolUseBlock(tool_use_id, name, arguments),), "tool_use", USAGE)


def tools_reply(
    *calls: tuple[str, Mapping[str, object]], prefix: str = "tu", usage: Usage = USAGE
) -> ModelReply:
    """A reply that calls several tools at once, with ids '<prefix>-1', '<prefix>-2', ..."""
    blocks = tuple(ToolUseBlock(f"{prefix}-{i}", name, args) for i, (name, args) in enumerate(calls, 1))
    return ModelReply(blocks, "tool_use", usage)


def end(text: str, usage: Usage = USAGE) -> ModelReply:
    """A reply that ends the turn with text."""
    return ModelReply((TextBlock(text),), "end_turn", usage)


RAISE2: dict[str, object] = {
    "tipo": "raise",
    "categoria": "retencion_de_calidad",
    "etapa": "calidad",
    "modelo": "SUV",
    "mercado": "Europa",
    "bitacora": "T02",
    "fragmento": F2,
    "estado_causa": "activa_sin_fecha",
}
RAISE5: dict[str, object] = {
    "tipo": "raise",
    "categoria": "parada_de_linea",
    "etapa": "montaje",
    "modelo": "Pickup",
    "mercado": None,
    "bitacora": "T05",
    "fragmento": F5,
    "estado_causa": "activa_sin_fecha",
}


def set_cause_proposal(
    case_id: str,
    categoria: str,
    bitacora: str,
    fragmento: str,
    estado_causa: str,
    etapa: str = "montaje",
) -> dict[str, object]:
    """A 'set_cause' proposal payload."""
    return {
        "tipo": "set_cause",
        "case_id": case_id,
        "categoria": categoria,
        "etapa": etapa,
        "bitacora": bitacora,
        "fragmento": fragmento,
        "estado_causa": estado_causa,
    }


def lift_proposal(causa_activa: str, bitacora: str, fragmento: str, estado_causa: str) -> dict[str, object]:
    """A 'lift' proposal payload."""
    return {
        "tipo": "lift",
        "causa_activa": causa_activa,
        "bitacora": bitacora,
        "fragmento": fragmento,
        "estado_causa": estado_causa,
    }


def output_text(*proposals: Mapping[str, object]) -> str:
    """The investigator's final text for 'proposals'."""
    return json.dumps({"propuestas": list(proposals)}, ensure_ascii=False)


def out(*proposals: Mapping[str, object], usage: Usage = USAGE) -> ModelReply:
    """A reply that ends the turn with the investigator's JSON output."""
    return end(output_text(*proposals), usage)


def validated(proposal_id: str, payload: Mapping[str, object]) -> ValidatedProposal:
    """A 'ValidatedProposal' parsed from a payload."""
    return ValidatedProposal(id=proposal_id, proposal=TypeAdapter(Proposal).validate_python(payload))


def stopped(reason: str) -> ModelReply:
    """A text reply with the given stop reason."""
    return ModelReply((TextBlock("..."),), reason, USAGE)


def make_coordinator(
    model: FakeModel,
    tools: FakeTools,
    *,
    max_turns: int = 8,
    limit: int = 95_000,
    allowed: tuple[str, ...] = OFFERED,
    system: str = "SYSTEM",
) -> Coordinator:
    config = LoopConfig(max_turns=max_turns, prompt_token_limit=limit, max_tokens=16_000, effort="medium")
    return Coordinator(model, tools.opener(), system, allowed, config)
