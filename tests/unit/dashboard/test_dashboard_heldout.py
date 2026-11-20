"""014 T4: the dashboard held-out filter (R13, E14, I5)."""

import pytest
from trace_builders import committed_line, history_row

from plant_monitor.cases.registry.run_reader import CaseRow, HistoryAt
from plant_monitor.dashboard.heldout import (
    UnsafeId,
    case_shown,
    history_shown,
    line_shown,
    notice_ids_valid,
    select_shown,
    validate_ids,
)
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.causes import Evidence
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.telemetry.trace import TraceLine

from builders import combination_of
from notice_builders import alert_notice, news_notice, plant_shifts, shift_report, silent_notice


def _items() -> tuple[Notice | ShiftReport, ...]:
    """The six items of E14, in order."""
    cited = news_notice("S004", "S003-Pickup-Local").model_copy(
        update={"evidencia": (Evidence(bitacora="T03", fragmento="x"),)}
    )
    return (
        alert_notice("S004", "S003-Pickup-Local"),
        ShiftReport(turno_id="T02", snapshot_id="S004", novedades=(cited,), casos_activos=()),
        shift_report("T02", "S004", active=("S005-Pickup-Brasil",)),
        alert_notice("S005", "S005-SUV-Local"),
        shift_report("T03", "S006"),
        shift_report("../T03", "S004"),
    )


def _line(snapshot_id: str, logbooks: list[str]) -> TraceLine:
    """A committed investigator line over 'snapshot_id' reading 'logbooks'."""
    data = committed_line("S004", proposals=[]).model_dump(mode="json")
    data["snapshot_id"] = snapshot_id
    data["investigator"]["logbooks"] = logbooks
    return TraceLine.model_validate(data)


def _lines() -> tuple[TraceLine, TraceLine, TraceLine]:
    """Lines (7), (8) and (9) of E14."""
    return _line("S004", ["T03"]), _line("../S004", []), _line("S004", [])


def _policy(is_open: bool) -> HeldOutPolicy:
    """Refuses T03, S005 and S006 while closed."""
    return HeldOutPolicy.from_calendar(plant_shifts(), "T03", is_open)


def test_e14_closed_guard_omits_held_out_and_unverifiable_items_and_lines() -> None:
    """014 E14 (R13): refused or unverifiable items and lines are omitted; the clean ones stay."""
    items = _items()
    policy = _policy(False)
    assert select_shown(items, policy) == ((items[0],), 5)
    held, bad_id, clean = _lines()
    assert [line_shown(held, policy), line_shown(bad_id, policy), line_shown(clean, policy)] == [
        False,
        False,
        True,
    ]


def test_e14_open_guard_keeps_everything_and_validate_ids_still_rejects() -> None:
    """014 E14 (R13, I5): with the guard open nothing is omitted; 'validate_ids' raises 'dashboard:'."""
    items = _items()
    policy = _policy(True)
    assert select_shown(items, policy) == (items, 0)
    held, bad_id, _ = _lines()
    assert line_shown(held, policy)
    assert line_shown(bad_id, policy)
    with pytest.raises(UnsafeId) as error:
        validate_ids(items[5])
    assert str(error.value) == "dashboard: invalid turno_id: ../T03"


def test_e14_case_and_history_rows_are_omitted_by_snapshot_prefix_and_pattern() -> None:
    """Risk: a held-out or malformed-id case or history row leaks into the page (R13)."""
    closed, opened = _policy(False), _policy(True)

    def case(case_id: str, opened_at: str) -> CaseRow:
        return CaseRow(case_id=case_id, combination=combination_of("S001-Pickup-Local"), opened_at=opened_at)

    def hist(case_id: str, snapshot_id: str) -> HistoryAt:
        return HistoryAt(seq=1, row=history_row(case_id, snapshot_id))

    cases = [
        case("S003-Pickup-Local", "S003"),
        case("S005-Pickup-Local", "S005"),
        case("S003-Pickup-Local", "S006"),
        case("S003-Pickup-Local", "../S003"),
    ]
    assert [case_shown(c, closed) for c in cases] == [True, False, False, False]
    assert all(case_shown(c, opened) for c in cases[:3])
    rows = [
        hist("S003-Pickup-Local", "S004"),
        hist("S003-Pickup-Local", "S005"),
        hist("S006-Pickup-Local", "S004"),
        hist("S003-Pickup-Local", "S4"),
    ]
    assert [history_shown(r, closed) for r in rows] == [True, False, False, False]
    assert all(history_shown(r, opened) for r in rows[:3])


@pytest.mark.parametrize("text", ["ver\nT03 luego", "ver\tS005"])
@pytest.mark.parametrize("where", ["coordinator", "investigator"])
def test_e14_line_with_a_refused_id_after_an_escaped_control_char_is_omitted(text: str, where: str) -> None:
    """014 E14 (R13): a refused id after an escaped control char in 'thinking' still hides the line."""
    data = committed_line("S004", proposals=[]).model_dump(mode="json")
    if where == "coordinator":
        data["thinking"] = [text]
    else:
        data["investigator"]["thinking"] = [text]
    assert not line_shown(TraceLine.model_validate(data), _policy(False))


def test_e14_closed_guard_keeps_a_sin_aviso_decision_notice_with_valid_ids() -> None:
    """014 E14 (R6, R13): a per-case 'sin_aviso' notice has a valid id, so its cause reaches the cell."""
    assert notice_ids_valid(silent_notice("S004", "S003-Pickup-Local"))


def test_e14_notice_ids_valid_checks_ids_and_evidence_shifts() -> None:
    """Risk: a per-case notice with a malformed id or evidence shift is shown instead of omitted (R13)."""
    good = alert_notice("S004", "S003-Pickup-Local")
    bad_shift = good.model_copy(update={"evidencia": (Evidence(bitacora="../T03", fragmento="x"),)})
    bad_id = good.model_copy(update={"notice_id": "x"})
    assert notice_ids_valid(good)
    assert not notice_ids_valid(bad_shift)
    assert not notice_ids_valid(bad_id)
