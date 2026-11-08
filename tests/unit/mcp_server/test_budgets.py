"""006 T12: size budgets and the threading guard through the in-process client (E15a-b, E17)."""

import json
import logging
from dataclasses import replace
from pathlib import Path

import pytest
from mcp_builders import StaticCases, frame_at, frame_with, tool_context

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, SnapshotCommit, all_combinations
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import build_server

from builders import case_with, history_row, measured

pytestmark = pytest.mark.anyio

CASE_ID = "S001-Sedán-Local"


async def test_e15a_history_over_budget_keeps_the_newest_rows_in_order() -> None:
    """E15a: view budget 1000 and 40 history rows; the newest rows stay, newest first."""
    case = case_with(CASE_ID, CaseState.FOLLOW_UP, Severity.HIGH, Severity.HIGH, at="S040")
    rows = tuple(history_row(CASE_ID, f"S{n:03d}", Stage.ASSEMBLY) for n in range(1, 41))
    ctx, frames = tool_context(cases=StaticCases([case], {CASE_ID: rows}))
    small = replace(ctx, view_max_chars=1000)
    with frames.entered(frame_at("S040")):
        async with ToolClient(build_server(small, frames)) as client:
            outcome = await client.call("get_case", {"case_id": CASE_ID})
    assert not outcome.is_error
    assert len(outcome.text) <= 1000
    data = json.loads(outcome.text)
    kept = [row["snapshot_id"] for row in data["historial"]]
    assert 0 < len(kept) < 40
    assert kept == [f"S{n:03d}" for n in range(40, 40 - len(kept), -1)]
    assert data["historial_omitido"] == 40 - len(kept)


async def test_e15b_logbook_over_its_own_limit_is_refused_whole_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """E15b: logbook budget 100 refuses 'get_logbook' with the full text and one WARNING."""
    ctx, frames = tool_context()
    with frames.entered(frame_at("S004")):
        async with ToolClient(build_server(ctx, frames)) as client:
            whole = await client.call("get_logbook", {"turno_id": "T02"})
    small, small_frames = tool_context(logbook_max_chars=100)
    with caplog.at_level(logging.WARNING), small_frames.entered(frame_at("S004")):
        async with ToolClient(build_server(small, small_frames)) as client:
            outcome = await client.call("get_logbook", {"turno_id": "T02"})
    assert outcome.is_error
    assert outcome.text == (
        "Error executing tool get_logbook: "
        f"get_logbook output is {len(whole.text)} characters, over the budget of 100"
    )
    assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


def _commit(snapshot_id: str) -> SnapshotCommit:
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


async def test_e17_file_backed_registry_serves_every_tool_on_the_loop_thread(tmp_path: Path) -> None:
    """E17: a real 'SqliteRegistry' inside 'processing' answers all six tools and is not written to."""
    sedan_local = Combination(modelo=Model.SEDAN, mercado=Market.LOCAL)
    metrics: dict[Combination, CombinationMetrics] = {
        combo: measured(combo, 0.0, 0.0, 0.0, None, Severity.NONE, Severity.NONE)
        for combo in all_combinations()
    }
    case_id = "S002-Sedán-Local"
    first = case_with(case_id, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM)
    second = case_with(
        case_id,
        CaseState.FOLLOW_UP,
        Severity.HIGH,
        Severity.HIGH,
        at="S003",
        reported=(CaseState.OPEN, Severity.MEDIUM, "S002"),
    )
    calls: list[tuple[str, dict[str, object]]] = [
        ("list_available_logbooks", {}),
        ("get_logbook", {"turno_id": "T01"}),
        ("get_deviations", {}),
        ("get_active_cases", {}),
        ("get_case", {"case_id": case_id}),
        ("get_delayed_units", {"modelo": sedan_local.modelo.value, "mercado": sedan_local.mercado.value}),
    ]
    with SqliteRegistry(tmp_path / "registry.db") as registry:
        with registry.processing(_commit("S002")):
            registry.cases.save_case(
                first, history_row(case_id, "S002", Stage.ASSEMBLY, minimum=Severity.MEDIUM)
            )
        with registry.processing(_commit("S003")):
            registry.cases.save_case(second, history_row(case_id, "S003", Stage.ASSEMBLY))
            conn = registry._session.conn
            before = conn.total_changes
            ctx, frames = tool_context(cases=registry.cases)
            with frames.entered(frame_with("S003", metrics)):
                async with ToolClient(build_server(ctx, frames)) as client:
                    outcomes = [await client.call(name, arguments) for name, arguments in calls]
            assert conn.total_changes == before
    assert [(name, o.is_error) for (name, _), o in zip(calls, outcomes, strict=True)] == [
        (name, False) for name, _ in calls
    ]
