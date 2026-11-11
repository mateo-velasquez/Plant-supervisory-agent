"""009 T7: a pending shift whose logbook file is absent is 'missing', never a load error (R8, E14, X7)."""

from pathlib import Path

import pytest
from incident_builders import copy_incident_logbooks, incident_shifts
from incident_runs import F5
from judgment_builders import bare_frame, incident_tool_context

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.logbooks import LogbookFileMissing, read_logbook_texts
from plant_monitor.logbooks.errors import LogbookMissing
from plant_monitor.logbooks.store import LogbookStore
from plant_monitor.mcp_server.client import ToolClient
from plant_monitor.mcp_server.server import build_server

from builders import held_out_policy


def incident_store(directory: Path) -> LogbookStore:
    """Store over the IF calendar and the logbooks in 'directory'."""
    shifts = incident_shifts()
    policy = HeldOutPolicy.from_calendar(shifts, "T06", True)
    return LogbookStore(directory, shifts, policy, read_logbook_texts)


def test_e14a_missing_lists_the_ids_whose_file_is_absent(tmp_path: Path) -> None:
    store = incident_store(copy_incident_logbooks(tmp_path, omit=["T05"]))
    assert store.missing(["T04", "T05"], "S010") == ("T05",)


@pytest.mark.parametrize("call", ["get", "verify_citation"])
def test_e14bc_a_missing_logbook_is_refused_not_a_load_error(tmp_path: Path, call: str) -> None:
    store = incident_store(copy_incident_logbooks(tmp_path, omit=["T05"]))
    with pytest.raises(LogbookMissing) as raised:
        if call == "get":
            store.get("T05", "S010")
        else:
            store.verify_citation("T05", F5, "S010")
    assert str(raised.value) == "logbook T05 is missing"
    assert isinstance(raised.value, RejectedRequest)
    assert not isinstance(raised.value, DataLoadError)


@pytest.mark.anyio
async def test_e14d_get_logbook_shows_the_missing_refusal(tmp_path: Path) -> None:
    ctx, frames = incident_tool_context(copy_incident_logbooks(tmp_path, omit=["T05"]))
    with frames.entered(bare_frame("S010")):
        async with ToolClient(build_server(ctx, frames)) as client:
            outcome = await client.call("get_logbook", {"turno_id": "T05"})
    assert outcome.is_error
    assert outcome.text == "Error executing tool get_logbook: logbook T05 is missing"


def test_x7_an_empty_logbook_file_is_present_not_missing(tmp_path: Path) -> None:
    directory = copy_incident_logbooks(tmp_path, omit=["T05"])
    (directory / "T05.txt").write_text("", encoding="utf-8")
    store = incident_store(directory)
    assert store.missing(["T05"], "S010") == ()
    assert store.get("T05", "S010").text == ""


def test_r8_loader_raises_file_missing_only_for_an_absent_file(tmp_path: Path) -> None:
    """Risk: the store maps every load error to 'missing', hiding a held-out refusal as a retry."""
    directory = copy_incident_logbooks(tmp_path, omit=["T05"])
    policy = held_out_policy("T03", is_open=True)
    with pytest.raises(LogbookFileMissing, match=r"T01\.txt: logbook not found"):
        read_logbook_texts(tmp_path / "empty", ["T01"], policy)
    with pytest.raises(DataLoadError) as refused:
        read_logbook_texts(directory, ["T99"], policy)
    assert not isinstance(refused.value, LogbookFileMissing)
