"""The Agentes view: snapshot list, KPIs and one snapshot's conversation (014 R8-R13); computes no metrics."""

import json
import re
from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Final

from pydantic import JsonValue

from plant_monitor.dashboard.heldout import SHIFT_ID
from plant_monitor.dashboard.payloads import (
    AgentCostEvent,
    AgentsKpis,
    AgentsPayload,
    AlertCallEvent,
    ApplyCallEvent,
    ControlErrorEvent,
    DecisionEvent,
    Event,
    HookBlockEvent,
    LogbookReadEvent,
    LogbookText,
    NoProposalsEvent,
    OtherCallEvent,
    ProposalEvent,
    RegistrationEvent,
    ReportCallEvent,
    ReportText,
    Segment,
    Selected,
    SnapshotEntry,
    ThinkingEvent,
    ValidationEvent,
)
from plant_monitor.dashboard.source import RunView, cost_as_of, format_usd, heldout_of
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.verbatim import verbatim_spans
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.telemetry.trace import (
    AgentName,
    TraceHook,
    TraceLine,
    TraceToolCall,
    run_totals,
)

_SHIFT_RE: Final = re.compile(SHIFT_ID)
_NOT_AVAILABLE: Final = "no disponible"
_LOGBOOK_TOOL: Final = "get_logbook"
_ROLE_ES: Final = {"coordinator": "coordinador", "investigator": "investigador"}
_ALLOWLIST: Final = re.compile(
    r"tool (?P<tool>\S+) is not allowed for the (?P<agent>investigator|coordinator)"
)
_NO_NEWS: Final = re.compile(r"(?P<case>\S+): no news since last report")
_CAUSE: Final = re.compile(r"texto for (?P<case>\S+) names cause (?P<named>\S+); its causa is (?P<causa>\S+)")
_FLOOR: Final = re.compile(r"texto for (?P<case>\S+) states .+: below notice severity \(.+\)")


def build_agents(view: RunView, logbooks: LogbookStore, at: int, snapshot: str | None) -> AgentsPayload:
    """The agents payload at position 'at' (already resolved); 'snapshot' picks the conversation."""
    shown = sorted((r for r in view.rows.processed if r.seq <= at), key=lambda r: r.seq, reverse=True)
    entries = [_entry(view, row.snapshot_id, row.seq) for row in shown]
    target = (entries[0]["snapshot_id"] if entries else None) if snapshot is None else snapshot
    chosen = next((e for e in entries if e["snapshot_id"] == target), None)
    return AgentsPayload(
        at=at,
        latest=view.resolve_at(None),
        trace_error=view.trace_error,
        heldout=heldout_of(view),
        kpis=_kpis(view, entries, at),
        snapshots=entries,
        selected=None if chosen is None else _selected(view, logbooks, chosen),
    )


def _entry(view: RunView, snapshot_id: str, seq: int) -> SnapshotEntry:
    line = view.committed.get(snapshot_id)
    attempts = len(view.aborted.get(snapshot_id, ()))
    if line is None:
        return SnapshotEntry(
            snapshot_id=snapshot_id,
            seq=seq,
            turno_id=None,
            agents=[],
            hook_blocks=0,
            model_calls=0,
            usd=format_usd(Decimal(0)),
            previous_attempts=attempts,
            traced=False,
        )
    return SnapshotEntry(
        snapshot_id=snapshot_id,
        seq=seq,
        turno_id=line.turno_id,
        agents=list(line.ran),
        hook_blocks=len(line.hooks),
        model_calls=run_totals([line]).model_calls,
        usd=format_usd(line.totals.usd),
        previous_attempts=attempts,
        traced=True,
    )


def _kpis(view: RunView, entries: Sequence[SnapshotEntry], at: int) -> AgentsKpis:
    return AgentsKpis(
        investigator=sum("investigator" in e["agents"] for e in entries),
        coordinator=sum("coordinator" in e["agents"] for e in entries),
        hook_blocks=sum(e["hook_blocks"] for e in entries),
        cost=cost_as_of(view, at),
    )


def _selected(view: RunView, logbooks: LogbookStore, entry: SnapshotEntry) -> Selected:
    line = view.committed.get(entry["snapshot_id"])
    return Selected(
        snapshot_id=entry["snapshot_id"],
        seq=entry["seq"],
        turno_id=entry["turno_id"],
        previous_attempts=entry["previous_attempts"],
        model_calls=entry["model_calls"],
        usd=entry["usd"],
        events=[] if line is None else conversation(line, logbooks),
    )


def conversation(line: TraceLine, logbooks: LogbookStore) -> list[Event]:
    """The events of one committed line in lane order (R9); logbook text is data, never interpreted."""
    events: list[Event] = [
        DecisionEvent(
            lane="code",
            kind="decision",
            decision=line.decision,
            decision_reason=line.decision_reason,
            required=len(line.required),
            agents=list(line.ran),
        )
    ]
    investigator = line.investigator
    if "investigator" in line.ran and investigator is not None:
        events.extend(
            _agent_turns(
                line,
                "investigator",
                investigator.thinking,
                investigator.tool_calls,
                logbooks,
                investigator.proposals,
            )
        )
        events.extend(
            ControlErrorEvent(lane="code", kind="control_error", messages=list(m))
            for m in investigator.control_errors
        )
        if investigator.proposals:
            events.extend(
                ProposalEvent(lane="investigator", kind="proposal", proposal=p)
                for p in investigator.proposals
            )
        else:
            events.append(NoProposalsEvent(lane="investigator", kind="no_proposals"))
        events.append(_cost_event(line, "investigator"))
    if line.proposals_applied or line.proposals_declined:
        events.append(
            ValidationEvent(
                lane="code",
                kind="validation",
                applied=list(line.proposals_applied),
                declined=list(line.proposals_declined),
            )
        )
    if "coordinator" in line.ran:
        events.extend(_agent_turns(line, "coordinator", line.thinking, line.tool_calls, logbooks, []))
        events.append(_cost_event(line, "coordinator"))
    if line.notices_agent or line.notices_template or line.report_id:
        events.append(
            RegistrationEvent(
                lane="code",
                kind="registration",
                agent=len(line.notices_agent),
                template=len(line.notices_template),
                report_id=line.report_id,
            )
        )
    return events


def _cost_event(line: TraceLine, agent: AgentName) -> AgentCostEvent:
    totals = run_totals([line]).by_agent[agent]
    return AgentCostEvent(
        lane=agent, kind="agent_cost", agent=agent, model_calls=totals.model_calls, usd=format_usd(totals.usd)
    )


def _agent_turns(
    line: TraceLine,
    agent: AgentName,
    thinking: Sequence[str],
    calls: Sequence[TraceToolCall],
    logbooks: LogbookStore,
    proposals: Sequence[Mapping[str, JsonValue]],
) -> list[Event]:
    """Thinking, then turn by turn the pre_tool blocks, the calls and the on_stop blocks of one agent."""
    events: list[Event] = []
    texts = [t for t in thinking if t.strip()]
    if texts:
        events.append(ThinkingEvent(lane=agent, kind="thinking", texts=texts))
    hooks = [h for h in line.hooks if h.agent == agent]
    blocked = {(h.turn, h.tool) for h in hooks if h.phase == "pre_tool" and h.tool is not None}
    turns = sorted({c.turn for c in calls} | {h.turn for h in hooks})
    for turn in turns:
        events.extend(_hook_event(h) for h in hooks if h.turn == turn and h.phase == "pre_tool")
        for call in calls:
            if call.turn != turn or (call.is_error and (call.turn, call.name) in blocked):
                continue
            events.append(_call_event(line, agent, call, logbooks, proposals))
        events.extend(_hook_event(h) for h in hooks if h.turn == turn and h.phase == "on_stop")
    return events


def _hook_event(hook: TraceHook) -> HookBlockEvent:
    return HookBlockEvent(
        lane="code",
        kind="hook_block",
        agent=hook.agent,
        phase=hook.phase,
        hook=hook.hook,
        tool=hook.tool,
        turn=hook.turn,
        reason=hook.reason,
        reason_es=explain_hook(hook),
    )


def _text(arguments: Mapping[str, JsonValue], key: str) -> str | None:
    value = arguments.get(key)
    return value if isinstance(value, str) else None


def _call_event(
    line: TraceLine,
    agent: AgentName,
    call: TraceToolCall,
    logbooks: LogbookStore,
    proposals: Sequence[Mapping[str, JsonValue]],
) -> Event:
    args = call.arguments
    if call.name == _LOGBOOK_TOOL and agent == "investigator":
        return _logbook_event(line, call, logbooks, proposals)
    if call.name == "apply_proposal":
        return ApplyCallEvent(
            lane=agent,
            kind="tool_call",
            turn=call.turn,
            name="apply_proposal",
            proposal=_text(args, "propuesta"),
            is_error=call.is_error,
            error=call.error,
        )
    if call.name == "emit_alert":
        return AlertCallEvent(
            lane=agent,
            kind="tool_call",
            turn=call.turn,
            name="emit_alert",
            case_id=_text(args, "case_id"),
            texto=_text(args, "texto"),
            is_error=call.is_error,
            error=call.error,
        )
    if call.name == "emit_shift_report":
        return ReportCallEvent(
            lane=agent,
            kind="tool_call",
            turn=call.turn,
            name="emit_shift_report",
            items=_report_items(args.get("textos")),
            is_error=call.is_error,
            error=call.error,
        )
    return OtherCallEvent(
        lane=agent,
        kind="tool_call",
        turn=call.turn,
        name=call.name,
        arguments_json=json.dumps(args, separators=(",", ":")),
        is_error=call.is_error,
        error=call.error,
    )


def _report_items(value: JsonValue | None) -> list[ReportText]:
    """The stored (case_id, texto) pairs of an 'emit_shift_report' call; other shapes give no items."""
    if not isinstance(value, list):
        return []
    return [
        ReportText(case_id=_text(item, "case_id"), texto=_text(item, "texto"))
        for item in value
        if isinstance(item, dict)
    ]


def _logbook_event(
    line: TraceLine,
    call: TraceToolCall,
    logbooks: LogbookStore,
    proposals: Sequence[Mapping[str, JsonValue]],
) -> LogbookReadEvent:
    turno_id = _text(call.arguments, "turno_id")
    text: LogbookText | None = None
    if turno_id is not None and _SHIFT_RE.fullmatch(turno_id):
        try:
            body = logbooks.get(turno_id, line.snapshot_id).text
        except RejectedRequest:
            body = None
        if body is not None:
            fragments = [
                f
                for p in proposals
                if p.get("bitacora") == turno_id and isinstance(f := p.get("fragmento"), str)
            ]
            text = LogbookText(
                segments=[Segment(text=part, mark=mark) for part, mark in segments(body, fragments)]
            )
    return LogbookReadEvent(
        lane="investigator",
        kind="logbook_read",
        turn=call.turn,
        turno_id=turno_id,
        is_error=call.is_error,
        error=call.error,
        logbook=text,
        note=None if text is not None else _NOT_AVAILABLE,
    )


def segments(text: str, fragments: Sequence[str]) -> list[tuple[str, bool]]:
    """Split 'text' into consecutive parts, marking the merged whitespace-tolerant spans of 'fragments'."""
    spans = sorted(span for fragment in fragments for span in verbatim_spans(text, fragment))
    merged: list[tuple[int, int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    parts: list[tuple[str, bool]] = []
    cursor = 0
    for start, end in merged:
        if start > cursor:
            parts.append((text[cursor:start], False))
        parts.append((text[start:end], True))
        cursor = end
    if cursor < len(text):
        parts.append((text[cursor:], False))
    return parts


def explain_hook(hook: TraceHook) -> str | None:
    """A Spanish sentence for a stored reason that fully matches a known pattern, else 'None'."""
    reason = hook.reason
    if m := _ALLOWLIST.fullmatch(reason):
        return (
            f"El {_ROLE_ES[m['agent']]} no tiene permiso para usar {m['tool']}: "
            "cada agente solo usa sus herramientas."
        )
    if m := _NO_NEWS.fullmatch(reason):
        return f"{m['case']} no tiene novedades desde el último informe: el aviso no se repite."
    if m := _CAUSE.fullmatch(reason):
        return (
            f"El texto de {m['case']} nombra la causa {m['named']}, pero la causa registrada es {m['causa']}."
        )
    if m := _FLOOR.fullmatch(reason):
        return f"El texto de {m['case']} declara una severidad menor que la del aviso."
    return None
