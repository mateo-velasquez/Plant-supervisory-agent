"""Pure text of a notice trace; every line is escaped so a logbook cannot drive the terminal (013 R12)."""

import json
from decimal import Decimal
from typing import Final

from plant_monitor.domain.numbers import DECIMALS, round_display
from plant_monitor.domain.text import escape_controls
from plant_monitor.telemetry.trace import USD_DECIMALS, TraceTotals
from plant_monitor.telemetry.trace_query import AbortedAttempt, AgentView, CauseView, LineView, NoticeTrace

_NONE: Final = "none"


def _number(value: float) -> str:
    """A float with 'DECIMALS' places; '-0.0' prints as '0.0'."""
    return f"{round_display(value) + 0.0:.{DECIMALS}f}"


def _usd(value: Decimal) -> str:
    return format(value.quantize(USD_DECIMALS), "f")


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _tokens(totals: TraceTotals) -> str:
    return (
        f"input {totals.input_tokens}, output {totals.output_tokens}, "
        f"cache read {totals.cache_read_tokens}, "
        f"cache write {totals.cache_write_5m_tokens} (5m) {totals.cache_write_1h_tokens} (1h), "
        f"usd {_usd(totals.usd)}"
    )


def _metrics(trace: NoticeTrace) -> list[str]:
    row = trace.history.row
    at = row.snapshot_id
    note = "" if trace.history.at_notice else f" (last history row; no row at {trace.notice.snapshot_id})"
    pct = "no shift plan" if row.gap_pct is None else f"{_number(row.gap_pct)} %"
    delay = (
        "delay beyond the shipment horizon"
        if row.delay_days is None
        else f"delay {_number(row.delay_days)} days"
    )
    stage = _NONE if row.bottleneck is None else str(row.bottleneck)
    previous = trace.history.previous
    before = "—" if previous is None else f"{previous.state} ({previous.snapshot_id})"
    return [
        f"metrics at {at}{note}: gap {_number(row.gap_units)} units ({pct}), {delay}, bottleneck {stage}",
        f"severity at {at}: minimum {row.minimum_severity}, effective {row.effective_severity}, "
        f"raised {'yes' if row.raised else 'no'}",
        f"transition: {before} → {row.state} ({at})",
    ]


def _cause_lines(trace: NoticeTrace) -> list[str]:
    notice = trace.notice
    cause = notice.causa
    text = f"cause: {cause.categoria}, etapa {_NONE if cause.etapa is None else cause.etapa}"
    if trace.cited is not None:
        text += f", recorded at {trace.cited.set_at}"
        if trace.cited.active_cause_id is not None:
            text += f" from {trace.cited.active_cause_id}"
    lines = [text]
    if notice.evidencia:
        lines.append("evidence:")
        lines.extend(f'  {item.bitacora}: "{item.fragmento}"' for item in notice.evidencia)
    else:
        lines.append(f"evidence: {_NONE}")
    return lines


def _active_cause(view: CauseView, snapshot_id: str) -> list[str]:
    cause = view.cause
    state = f"lifted at {cause.lifted_at}" if view.lift_shown else f"in force at {snapshot_id}"
    lines = [
        f"  {cause.active_cause_id}: {cause.categoria}, {cause.scope.describe()}; "
        f"linked at {view.linked_at}; {state}",
        f'    opened at {cause.opened_at} by {cause.opened_by.bitacora}: "{cause.opened_by.fragmento}"',
    ]
    if view.lift_shown and cause.lifted_by is not None:
        lines.append(
            f'    lifted at {cause.lifted_at} by {cause.lifted_by.bitacora}: "{cause.lifted_by.fragmento}"'
        )
    opening = view.opening
    if opening is None:
        return lines
    head = f"    raise opened at {opening.snapshot_id}"
    match opening.status:
        case "no_line":
            lines.append(f"{head}: no committed trace line")
        case "no_proposal":
            lines.append(f"{head}: no matching proposal in the committed line")
        case "found":
            assert opening.proposal is not None and opening.apply is not None
            lines.append(f"{head} ({opening.file}):")
            lines.append(f"      investigator proposal {_json(opening.proposal)}")
            lines.append(
                f"      coordinator turn {opening.apply.turn} {opening.apply.name} "
                f"{_json(opening.apply.arguments)}"
            )
    return lines


def _section(agent: AgentView) -> list[str]:
    if agent.agent == "investigator":
        lines = [f"investigator (outcome {agent.outcome}, trigger {agent.trigger}):"]
    else:
        lines = [f"coordinator (outcome {agent.outcome}):"]
    for view in agent.calls:
        call = view.call
        text = f"  turn {call.turn} {call.name} {_json(call.arguments)}"
        if call.is_error:
            text += f" [error: {call.error}]"
        if view.this_case:
            text += " → this case"
        lines.append(text)
    lines.extend(f"  proposal {_json(proposal)}" for proposal in agent.proposals)
    return lines


def _aborted(attempt: AbortedAttempt) -> str:
    investigator = (
        "" if attempt.investigator_outcome is None else f", investigator {attempt.investigator_outcome}"
    )
    head = f"aborted attempt in {attempt.file}: outcome {attempt.outcome}{investigator}"
    return f"{head}, {_tokens(attempt.totals)}"


def _line_lines(line: LineView, snapshot_id: str) -> list[str]:
    lines: list[str] = []
    if line.no_agent:
        lines.append("agents: none, no agent was involved")
    for agent in line.agents:
        lines.extend(_section(agent))
    if line.hooks:
        lines.append("hooks:")
        for hook in line.hooks:
            where = f"{hook.tool}, turn {hook.turn}" if hook.tool is not None else f"turn {hook.turn}"
            lines.append(f"  {hook.agent} {hook.phase} {hook.hook} ({where}): {hook.reason}")
    else:
        lines.append(f"hooks: {_NONE}")
    lines.append(f"tokens at {snapshot_id}: {_tokens(line.totals)}")
    return lines


def _trace_lines(trace: NoticeTrace) -> list[str]:
    snapshot_id = trace.notice.snapshot_id
    if trace.mode == "thresholds_only":
        return ["trace: threshold-only run: no agent was involved"]
    aborted = [_aborted(attempt) for attempt in trace.aborted]
    if trace.line is None:
        return [f"trace: no committed trace line for {snapshot_id}", *aborted]
    line = trace.line
    reason = _NONE if line.decision_reason is None else line.decision_reason
    head = f"trace: committed line in {line.file} (decision {line.decision}, reason {reason})"
    return [head, *aborted, *_line_lines(line, snapshot_id)]


def render_notice_trace(trace: NoticeTrace) -> str:
    """The R12 layout, each line escaped and joined by newlines, with no final newline."""
    notice = trace.notice
    lines = [
        f"notice {notice.notice_id}",
        f"case {notice.case_id}, snapshot {notice.snapshot_id}",
        f"type {notice.tipo}, estado {notice.estado}, severidad {notice.severidad}, "
        f"severidad_maxima {notice.severidad_maxima}",
        *_metrics(trace),
        f"motivo: {', '.join(notice.motivo) if notice.motivo else _NONE}",
        f"severity set by: {notice.origen}",
        f"text written by: {trace.text_by}",
        f'texto: "{notice.texto}"',
        *_cause_lines(trace),
    ]
    if trace.causes:
        lines.append("active causes:")
        for view in trace.causes:
            lines.extend(_active_cause(view, notice.snapshot_id))
    else:
        lines.append(f"active causes: {_NONE}")
    lines.extend(_trace_lines(trace))
    return "\n".join(escape_controls(line) for line in lines)
