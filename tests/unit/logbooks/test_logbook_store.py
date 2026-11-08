"""006 T4-T5: logbook store refusals, single loader and citation check (R2-R5, E3-E5, E8, E9)."""

import ast
import inspect
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

import pytest

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.ingestion.logbooks import read_logbook_texts
from plant_monitor.ingestion.plant import load_shifts
from plant_monitor.logbooks.errors import (
    EmptyFragment,
    FragmentNotFound,
    LogbookHeldOut,
    LogbookNotAvailable,
    UnknownLogbook,
)
from plant_monitor.logbooks.store import LogbookStore

from builders import FIXTURE_PLANT, held_out_policy

LOGBOOKS = Path(__file__).resolve().parents[2] / "fixtures" / "bitacoras"
SOURCE = Path(__file__).resolve().parents[3] / "src" / "plant_monitor" / "logbooks"
NOT_AVAILABLE = "logbook T02 is not available at S003: it closes at S004"


class SpyLoader:
    """Records calls and serves the fixture texts."""

    def __init__(self) -> None:
        self.calls: list[tuple[Path, list[str], HeldOutPolicy]] = []

    def __call__(self, directory: Path, turno_ids: Iterable[str], policy: HeldOutPolicy) -> dict[str, str]:
        ids = list(turno_ids)
        self.calls.append((directory, ids, policy))
        return {i: (LOGBOOKS / f"{i}.txt").read_text(encoding="utf-8") for i in ids}


def make_store(policy: HeldOutPolicy | None = None) -> tuple[LogbookStore, SpyLoader, HeldOutPolicy]:
    """Store over the fixture calendar and logbooks with a spy loader."""
    spy = SpyLoader()
    chosen = policy if policy is not None else held_out_policy(is_open=True)
    shifts = load_shifts(FIXTURE_PLANT / "turnos.csv")
    return LogbookStore(LOGBOOKS, shifts, chosen, spy), spy, chosen


@pytest.mark.parametrize(
    ("turno_id", "snapshot", "closed_policy", "error", "message"),
    [
        ("T02", "S003", False, LogbookNotAvailable, NOT_AVAILABLE),
        ("T03", "S006", True, LogbookHeldOut, "logbook T03 is held out"),
        ("T03", "S005", True, LogbookHeldOut, "logbook T03 is held out"),
        ("T09", "S004", False, UnknownLogbook, "unknown logbook T09"),
        ("t02", "S004", False, UnknownLogbook, "unknown logbook t02"),
    ],
)
def test_e4_refusals_check_in_order_with_bare_messages(
    turno_id: str, snapshot: str, closed_policy: bool, error: type[RejectedRequest], message: str
) -> None:
    """E4: unknown, held out, then not closed; loader never called."""
    store, spy, _ = make_store(held_out_policy("T03") if closed_policy else None)
    with pytest.raises(error) as raised:
        store.get(turno_id, snapshot)
    assert str(raised.value) == message
    assert isinstance(raised.value, RejectedRequest)
    assert spy.calls == []


def test_r2_available_lists_closed_shifts_without_refused() -> None:
    """Risk: a held-out shift leaks through 'available' (R2, E3 store half)."""
    store, _, _ = make_store()
    assert store.available("S004") == (("T01", "S002"), ("T02", "S004"))
    held, _, _ = make_store(held_out_policy("T03"))
    assert held.available("S006") == (("T01", "S002"), ("T02", "S004"))


def test_e5_loader_called_once_with_store_policy_and_default_is_shared_reader() -> None:
    """E5: one loader call per id, cached; default loader is 'read_logbook_texts'."""
    store, spy, policy = make_store()
    first = store.get("T02", "S004")
    store.get("T02", "S004")
    store.verify_citation("T02", "se paró", "S004")
    assert spy.calls == [(LOGBOOKS, ["T02"], policy)]
    assert (first.turno_id, first.closed_at) == ("T02", "S004")
    assert inspect.signature(LogbookStore.__init__).parameters["loader"].default is read_logbook_texts


def test_risk_policy_and_shifts_must_agree_at_construction() -> None:
    """Risk: a policy from another calendar fails late as KeyError instead of at construction (R4, X3)."""
    shifts = load_shifts(FIXTURE_PLANT / "turnos.csv")
    policy = held_out_policy(is_open=True)
    mismatched = replace(policy, known_shifts=policy.known_shifts | {"T99"})
    with pytest.raises(ValueError):
        LogbookStore(LOGBOOKS, shifts, mismatched, SpyLoader())


@pytest.mark.parametrize("package", ["logbooks", "mcp_server"])
def test_e5_package_has_no_file_io(package: str) -> None:
    """E5/R4: no 'open', 'read_text' or 'read_bytes' call under 'logbooks/' or 'mcp_server/'."""
    files = list((SOURCE.parent / package).glob("*.py"))
    assert files
    banned = {"open", "read_text", "read_bytes"}
    for path in files:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                func = node.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else func.attr
                    if isinstance(func, ast.Attribute)
                    else ""
                )
                assert name not in banned, f"{path.name}: {name}"


@pytest.mark.parametrize(
    "fragment",
    [
        "se paró la línea de montaje de Sedán",
        "falla en la atornilladora de la estación 4",
        "falla  en la\tatornilladora",
    ],
)
def test_e8_verbatim_variants_pass(fragment: str) -> None:
    """E8 (a)-(c): exact, across the line break, and tab or double-space variants pass."""
    store, _, _ = make_store()
    store.verify_citation("T02", fragment, "S004")


def test_e8_paraphrase_is_not_found() -> None:
    """E8 (d): a paraphrase raises 'FragmentNotFound'."""
    store, _, _ = make_store()
    with pytest.raises(FragmentNotFound) as raised:
        store.verify_citation("T02", "se detuvo la línea de montaje de Sedán", "S004")
    assert str(raised.value) == "fragment not found in T02"


@pytest.mark.parametrize("fragment", ["", "  \n"])
def test_e8_empty_fragment(fragment: str) -> None:
    """E8 (e): empty after normalization raises 'EmptyFragment'."""
    store, _, _ = make_store()
    with pytest.raises(EmptyFragment) as raised:
        store.verify_citation("T02", fragment, "S004")
    assert str(raised.value) == "empty fragment for T02"


def test_e8_logbook_not_yet_available() -> None:
    """E8 (f): citing before the shift closes is refused as not available."""
    store, _, _ = make_store()
    with pytest.raises(LogbookNotAvailable) as raised:
        store.verify_citation("T02", "se paró la línea de montaje de Sedán", "S003")
    assert str(raised.value) == NOT_AVAILABLE


@pytest.mark.parametrize("fragment", ["Se paró la línea", "“sin fecha de reparación”"])
def test_e9_case_and_typographic_quotes_are_not_folded(fragment: str) -> None:
    """E9: case and quote variants fail."""
    store, _, _ = make_store()
    with pytest.raises(FragmentNotFound) as raised:
        store.verify_citation("T02", fragment, "S004")
    assert str(raised.value) == "fragment not found in T02"
