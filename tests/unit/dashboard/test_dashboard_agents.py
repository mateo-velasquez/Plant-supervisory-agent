"""014 T8-T9: 'build_agents', 'segments', 'explain_hook' and 'conversation' (R8-R13; E7-E12, E15)."""

import json
from pathlib import Path
from typing import Any

import pytest
import trace_builders
from dashboard_builders import RESUMED as _RESUMED
from incident_runs import F5
from trace_builders import apply_call, committed_line, tool_call

from plant_monitor.config import Settings
from plant_monitor.dashboard.agents import build_agents, conversation, explain_hook, segments
from plant_monitor.dashboard.payloads import AgentsPayload
from plant_monitor.dashboard.source import RunView, load_view
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.verbatim import normalize_whitespace
from plant_monitor.ingestion.plant import load_shifts
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.telemetry.trace import TraceHook, TraceLine, run_totals

from builders import isolate_settings_env

agent_dir = trace_builders.agent_dir
thresholds_dir = trace_builders.thresholds_dir
RESUMED = _RESUMED

type Payload = dict[str, Any]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _load(settings: Settings) -> tuple[RunView, LogbookStore]:
    """The view and the logbook store under the policy the settings give."""
    shifts = load_shifts(settings.plant_dir / "turnos.csv")
    policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
    store = LogbookStore(settings.logbooks_dir, shifts, policy)
    return load_view(settings.registry_path, settings.traces_dir, policy), store


def _agents(settings: Settings, snapshot: str | None = None, at: int | None = None) -> Payload:
    """The agents payload as the client parses it."""
    view, store = _load(settings)
    payload: AgentsPayload = build_agents(view, store, view.resolve_at(at), snapshot)
    parsed: Payload = json.loads(json.dumps(payload))
    return parsed


def _events(line: TraceLine, store: LogbookStore) -> list[Payload]:
    parsed: list[Payload] = json.loads(json.dumps(conversation(line, store)))
    return parsed


def _kinds(events: list[Payload]) -> list[tuple[str, str]]:
    return [(e["lane"], e["kind"]) for e in events]


def _with(line: TraceLine, **fields: object) -> TraceLine:
    """A copy of 'line' with top-level 'fields' replaced, revalidated."""
    return TraceLine.model_validate({**line.model_dump(mode="json"), **fields})


def test_e7_agents_list_and_kpis(agent_dir: Settings) -> None:
    """014 E7 (R8): AGENT_DIR at 10, newest first, KPIs and per-snapshot entries."""
    payload = _agents(agent_dir)
    kpis = payload["kpis"]
    assert (kpis["investigator"], kpis["coordinator"], kpis["hook_blocks"]) == (5, 5, 1)
    assert kpis["cost"] == {"usd": "0.00760000", "model_calls": 19, "tokens": 60800}
    entries = payload["snapshots"]
    assert [e["snapshot_id"] for e in entries] == [f"S{n:03d}" for n in range(10, 0, -1)]
    by_id = {e["snapshot_id"]: e for e in entries}
    assert by_id["S010"]["agents"] == ["investigator", "coordinator"]
    assert (by_id["S010"]["hook_blocks"], by_id["S010"]["model_calls"], by_id["S010"]["usd"]) == (
        1,
        5,
        "0.00200000",
    )
    assert all(by_id[s]["agents"] == [] for s in ("S001", "S003", "S007", "S009"))
    assert all(e["previous_attempts"] == 0 and e["traced"] is True for e in entries)
    assert payload["selected"]["snapshot_id"] == "S010"


def test_e8_conversation_order_pairs_hook_blocks_with_their_tool_calls(agent_dir: Settings) -> None:
    """014 E8 (R9): AGENT_DIR snapshot S010, lane and kind in order."""
    events = _agents(agent_dir, "S010")["selected"]["events"]
    assert _kinds(events) == [
        ("code", "decision"),
        ("investigator", "logbook_read"),
        ("investigator", "proposal"),
        ("investigator", "agent_cost"),
        ("code", "validation"),
        ("coordinator", "tool_call"),
        ("code", "hook_block"),
        ("coordinator", "tool_call"),
        ("coordinator", "tool_call"),
        ("coordinator", "tool_call"),
        ("coordinator", "agent_cost"),
        ("code", "registration"),
    ]
    decision, read, proposal, inv_cost, validation, apply, block, alert_a, alert_b, report, cost, reg = events
    assert (decision["decision"], decision["decision_reason"]) == ("call", "text_needed")
    assert (read["turn"], read["turno_id"]) == (1, "T05")
    assert proposal["proposal"]["id"] == "S010-p1"
    assert (inv_cost["model_calls"], inv_cost["usd"]) == (2, "0.00080000")
    assert "S010-p1" in validation["applied"]
    assert (apply["name"], apply["proposal"], apply["turn"]) == ("apply_proposal", "S010-p1", 1)
    assert (block["agent"], block["hook"], block["tool"], block["turn"]) == (
        "coordinator",
        "allowlist",
        "get_logbook",
        2,
    )
    assert block["reason_es"] == explain_hook(
        TraceHook.model_validate({k: block[k] for k in ("agent", "phase", "hook", "tool", "turn", "reason")})
    )
    assert [(c["name"], c.get("case_id")) for c in (alert_a, alert_b)] == [
        ("emit_alert", "S010-Pickup-Local"),
        ("emit_alert", "S010-Pickup-Brasil"),
    ]
    assert (report["name"], report["turn"], len(report["items"])) == ("emit_shift_report", 3, 2)
    assert (cost["model_calls"], cost["usd"]) == (3, "0.00120000")
    assert (reg["agent"], reg["template"], reg["report_id"]) == (4, 0, "T05-informe")
    assert not any(e["kind"] == "thinking" for e in events)


def test_e9_thinking_keeps_non_empty_texts_before_the_first_turn(agent_dir: Settings) -> None:
    """014 E9 (R9): thinking events per agent, empty texts dropped, none when all empty."""
    _, store = _load(agent_dir)
    base = committed_line("S004", proposals=[], coordinator_calls=[apply_call(1, "S004-p1")])
    investigator = {**base.model_dump(mode="json")["investigator"]}
    investigator["tool_calls"] = [tool_call(1, "get_case", {}).model_dump(mode="json")]
    investigator["thinking"] = ["Busco la causa en T05."]
    line = _with(base, investigator=investigator, thinking=["", "Reviso las propuestas."])
    events = _events(line, store)
    thinking = [(e["lane"], e["texts"]) for e in events if e["kind"] == "thinking"]
    assert thinking == [
        ("investigator", ["Busco la causa en T05."]),
        ("coordinator", ["Reviso las propuestas."]),
    ]
    first = {
        lane: next(i for i, e in enumerate(events) if e["lane"] == lane)
        for lane in ("investigator", "coordinator")
    }
    assert events[first["investigator"]]["kind"] == "thinking"
    assert events[first["coordinator"]]["kind"] == "thinking"

    empty = _with(line, thinking=["", ""], investigator={**investigator, "thinking": [""]})
    assert not any(e["kind"] == "thinking" for e in _events(empty, store))


def test_e10_segments_merge_overlaps_and_ignore_absent_fragments() -> None:
    """014 E10 (R10; Q-36): marked spans are whitespace-tolerant, merged, and cover the whole text."""
    text = "Turno T05.\nse paró la línea\nde montaje.\nFin."
    result = segments(text, ["se paró la línea de montaje", "montaje.", "no está"])
    assert result == [("Turno T05.\n", False), ("se paró la línea\nde montaje.", True), ("\nFin.", False)]
    assert "".join(part for part, _ in result) == text


def test_e10_logbook_read_marks_the_cited_fragment(agent_dir: Settings) -> None:
    """014 E10 (R10): AGENT_DIR S010's logbook_read has the file's text and one segment marked."""
    _, store = _load(agent_dir)
    read = next(e for e in _agents(agent_dir, "S010")["selected"]["events"] if e["kind"] == "logbook_read")
    parts = read["logbook"]["segments"]
    assert "".join(p["text"] for p in parts) == store.get("T05", "S010").text
    marked = [p["text"] for p in parts if p["mark"]]
    assert len(marked) == 1
    assert normalize_whitespace(marked[0]) == normalize_whitespace(F5)


@pytest.mark.parametrize("turno_id", ["T05", "../T05", 5])
def test_logbook_read_not_readable_is_null_with_a_note(agent_dir: Settings, turno_id: object) -> None:
    """Risk: 014 R10: an unclosed logbook or malformed id must not leak text; it shows 'no disponible'."""
    _, store = _load(agent_dir)
    base = committed_line("S004", proposals=[])
    investigator = {**base.model_dump(mode="json")["investigator"]}
    investigator["tool_calls"] = [tool_call(1, "get_logbook", {"turno_id": turno_id}).model_dump(mode="json")]
    read = next(
        e for e in _events(_with(base, investigator=investigator), store) if e["kind"] == "logbook_read"
    )
    assert (read["logbook"], read["note"]) == (None, "no disponible")


CASE = "S010-Pickup-Local"
# Formats of 'CauseHook.check' and 'TextFloorHook.check' with real enum values.
CAUSE_REASON = (
    f"texto for {CASE} names cause {CauseCategory.LINE_STOP}; its causa is {CauseCategory.QUALITY_HOLD}"
)
FLOOR_REASON = (
    f"texto for {CASE} states severidad {Severity.MEDIUM}: below notice severity ({Severity.CRITICAL})"
)


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (
            "tool get_logbook is not allowed for the coordinator",
            "El coordinador no tiene permiso para usar get_logbook: cada agente solo usa sus herramientas.",
        ),
        (
            "S010-Pickup-Local: no news since last report",
            "S010-Pickup-Local no tiene novedades desde el último informe: el aviso no se repite.",
        ),
        (
            CAUSE_REASON,
            "El texto de S010-Pickup-Local nombra la causa parada_de_linea, "
            "pero la causa registrada es retencion_de_calidad.",
        ),
        (
            FLOOR_REASON,
            "El texto de S010-Pickup-Local declara una severidad menor que la del aviso.",
        ),
        ("something else", None),
    ],
)
def test_e11_explain_hook_maps_known_reasons_to_spanish(reason: str, expected: str | None) -> None:
    """014 E11 (R11): full-match patterns give a sentence, anything else gives None."""
    hook = TraceHook.model_validate(
        {
            "agent": "coordinator",
            "phase": "pre_tool",
            "hook": "allowlist",
            "tool": None,
            "turn": 1,
            "reason": reason,
        }
    )
    assert explain_hook(hook) == expected


def test_e12_resumed_run_counts_previous_attempts_and_shows_the_committed_line(RESUMED: Settings) -> None:
    """014 E12 (R8, R12; Q-94): RESUMED, snapshot S005."""
    payload = _agents(RESUMED, "S005")
    by_id = {e["snapshot_id"]: e for e in payload["snapshots"]}
    assert by_id["S005"]["previous_attempts"] == 1
    assert by_id["S004"]["previous_attempts"] == 0
    assert payload["selected"]["previous_attempts"] == 1
    view, _ = _load(RESUMED)
    committed = view.committed["S005"]
    events = payload["selected"]["events"]
    assert events[0]["kind"] == "decision"
    assert events[-1]["kind"] == "registration"
    assert events[-1]["agent"] == len(committed.notices_agent)
    assert payload["selected"]["usd"] == f"{committed.totals.usd:.8f}"
    all_lines = [line for _, line in view.lines]
    assert any(line.status == "aborted" for line in all_lines)
    assert payload["kpis"]["cost"]["model_calls"] == run_totals(all_lines).model_calls


def test_e15_held_out_snapshot_selects_nothing_and_leaks_no_id(thresholds_dir: Settings) -> None:
    """014 E15 (R13, agents part): a refused snapshot gives selected null, same as an unknown one."""
    closed = thresholds_dir.model_copy(update={"heldout_open": False, "heldout_first_shift": "T06"})
    refused = _agents(closed, "S012")
    assert refused["selected"] is None
    assert refused == _agents(closed, "S099")
    assert refused["heldout"]["omitted"]["snapshots"] == 2
    body = json.dumps(_agents(closed))
    assert not any(token in body for token in ("S011", "S012", "T06"))
