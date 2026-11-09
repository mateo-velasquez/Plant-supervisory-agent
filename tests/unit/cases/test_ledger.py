"""008 T4: 'CauseLedger' set_cause, raise_severity and lift refusals and effects (E6, E8-E10)."""

from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from plant_monitor.cases.causes import Candidate
from plant_monitor.cases.ledger import (
    CaseNotEvaluated,
    CaseNotFound,
    CauseAlreadySet,
    CauseFromRaise,
    CauseLedger,
    CauseLinkedToRaise,
    DuplicateRaise,
    LiftNotLater,
    RaiseAlreadyLifted,
    UnknownActiveCause,
)
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import (
    ActiveCause,
    Cause,
    CauseCategory,
    CauseScope,
    CitedCause,
    Evidence,
)
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.errors import RejectedRequest
from plant_monitor.domain.models import Combination, SnapshotCommit
from plant_monitor.ingestion.plant import load_shifts

from builders import FIXTURE_PLANT, case_with, history_row

SHIFTS = load_shifts(FIXTURE_PLANT / "turnos.csv")
SEL = "S001-Sedán-Local"
SE = "S005-SUV-Europa"
SB = "S007-SUV-Brasil"
PL = "S010-Pickup-Local"
PB = "S010-Pickup-Brasil"
PE = "S007-Pickup-Europa"
SEL8 = "S008-Sedán-Local"
AC1_ID = "S004-causa-1"
AC2_ID = "S010-causa-1"
F2 = "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
F3 = "El auditor vuelve mañana a primera hora"
F4 = "La auditoría de homologación terminó a las 8:30"
F5 = "se paró la línea de montaje de Pickup por la rotura del transportador aéreo de la estación 3"
F6 = "la línea de montaje de Pickup volvió a las 4:00"
EV_T02 = Evidence(bitacora="T02", fragmento=F2)
EV_T03 = Evidence(bitacora="T03", fragmento=F3)
EV_T04 = Evidence(bitacora="T04", fragmento=F4)
EV_T05 = Evidence(bitacora="T05", fragmento=F5)
EV_T06 = Evidence(bitacora="T06", fragmento=F6)
PICKUP_ANY = CauseScope(modelo=Model.PICKUP, etapa=Stage.ASSEMBLY, mercado=None)
SUV_EUROPE = CauseScope(modelo=Model.SUV, etapa=Stage.QUALITY, mercado=Market.EUROPE)
AC1 = ActiveCause(
    active_cause_id=AC1_ID,
    categoria=CauseCategory.QUALITY_HOLD,
    scope=SUV_EUROPE,
    opened_at="S004",
    opened_by=EV_T02,
)
AC2 = ActiveCause(
    active_cause_id=AC2_ID,
    categoria=CauseCategory.LINE_STOP,
    scope=PICKUP_ANY,
    opened_at="S010",
    opened_by=EV_T05,
)


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def cand(case_id: str, stage: Stage | None) -> Candidate:
    """Candidate for an open case with the given Q-32 stage."""
    return Candidate(case=case_with(case_id, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM), stage=stage)


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


@contextmanager
def at(registry: SqliteRegistry, snapshot: str, *new_ids: str) -> Iterator[CauseLedger]:
    """One 'processing' unit that first saves the cases opened at 'snapshot'; yields a ledger."""
    with registry.processing(commit(snapshot)):
        for case_id in new_ids:
            state = CaseState.RESOLVED if case_id == SEL else CaseState.OPEN
            case = case_with(case_id, state, Severity.MEDIUM, Severity.MEDIUM)
            registry.cases.save_case(case, history_row(case_id, snapshot, None))
        yield CauseLedger(registry.causes, registry.cases, SHIFTS)


def seed_ac2(registry: SqliteRegistry, lifted_at: str | None = None) -> None:
    """AC2 opened at S010 and, if 'lifted_at', lifted then by (T06, F6)."""
    with at(registry, "S010"):
        registry.causes.open(AC2)
    if lifted_at is not None:
        with at(registry, lifted_at):
            registry.causes.lift(AC2_ID, lifted_at, EV_T06)


@contextmanager
def e6_ledger(
    registry: SqliteRegistry, *, prior_cause: bool = False, attached: bool = False
) -> Iterator[CauseLedger]:
    """E6's world at S010: SEL resolved at S004, SE and SB active, PL opened here."""
    with at(registry, "S001", SEL):
        pass
    with at(registry, "S005", SE):
        if prior_cause:
            registry.causes.set_cited(
                SE,
                CitedCause(
                    categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY, evidence=EV_T02, set_at="S005"
                ),
            )
    with at(registry, "S007", SB):
        pass
    with at(registry, "S010", PL) as ledger:
        if attached:
            registry.causes.open(AC2)
            registry.causes.link(AC2_ID, PL, "S010")
            registry.causes.set_cited(
                PL,
                CitedCause(
                    categoria=CauseCategory.LINE_STOP,
                    etapa=Stage.ASSEMBLY,
                    evidence=EV_T05,
                    set_at="S010",
                    active_cause_id=AC2_ID,
                ),
            )
        yield ledger


E6_CANDIDATES = [cand(SE, Stage.QUALITY), cand(SB, None), cand(PL, Stage.ASSEMBLY)]
REWORK = CauseCategory.REWORK
QUALITY_HOLD = CauseCategory.QUALITY_HOLD


@pytest.mark.parametrize(
    ("case_id", "prior_cause", "attached", "error", "message"),
    [
        ("S999-SUV-Local", False, False, CaseNotFound, "unknown case S999-SUV-Local"),
        (SEL, False, False, CaseNotEvaluated, "S001-Sedán-Local is not evaluated at S010"),
        (
            SE,
            True,
            False,
            CauseAlreadySet,
            "cause of S005-SUV-Europa was set at S005; it stays until the case resolves",
        ),
        (PL, False, True, CauseFromRaise, "cause of S010-Pickup-Local comes from active cause S010-causa-1"),
    ],
    ids=["a_unknown", "b_not_evaluated", "d_already_set", "e_from_raise"],
)
def test_e6_set_cause_refusals(
    registry: SqliteRegistry,
    case_id: str,
    prior_cause: bool,
    attached: bool,
    error: type[RejectedRequest],
    message: str,
) -> None:
    ledger_cm = e6_ledger(registry, prior_cause=prior_cause, attached=attached)
    with ledger_cm as ledger, pytest.raises(error) as refusal:
        ledger.set_cause("S010", case_id, Cause(categoria=REWORK, etapa=Stage.QUALITY), EV_T02, E6_CANDIDATES)
    assert str(refusal.value) == message


@pytest.mark.parametrize(
    ("case_id", "calls", "expected"),
    [
        (SE, [(QUALITY_HOLD, Stage.QUALITY), (REWORK, Stage.QUALITY)], (REWORK, Stage.QUALITY)),
        (SB, [(REWORK, Stage.PAINT)], (REWORK, Stage.PAINT)),
    ],
    ids=["c_second_replaces_first", "f_stage_not_compared_with_null_bottleneck"],
)
def test_e6_set_cause_stores_and_replaces_within_the_snapshot(
    registry: SqliteRegistry,
    case_id: str,
    calls: list[tuple[CauseCategory, Stage]],
    expected: tuple[CauseCategory, Stage],
) -> None:
    with e6_ledger(registry) as ledger:
        for categoria, etapa in calls:
            ledger.set_cause("S010", case_id, Cause(categoria=categoria, etapa=etapa), EV_T02, E6_CANDIDATES)
        stored = ledger.cited([case_id])[case_id]
    assert (stored.categoria, stored.etapa) == expected
    assert (stored.evidence, stored.set_at, stored.active_cause_id) == (EV_T02, "S010", None)


def test_r3_q48_set_cause_refuses_a_different_pair_on_a_case_linked_to_a_cause_in_force(
    registry: SqliteRegistry,
) -> None:
    paint_scope = CauseScope(modelo=Model.PICKUP, etapa=Stage.PAINT, mercado=None)
    candidates = [cand(PL, Stage.PAINT)]
    with at(registry, "S010", PL) as ledger:
        ledger.set_cause("S010", PL, Cause(categoria=REWORK, etapa=Stage.PAINT), EV_T02, candidates)
        outcome = ledger.raise_severity("S010", REWORK, paint_scope, EV_T05, candidates)
        before = ledger.cited([PL])[PL]
        assert outcome.linked == (PL,)
        assert before.active_cause_id is None
        with pytest.raises(CauseLinkedToRaise) as refusal:
            ledger.set_cause(
                "S010", PL, Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY), EV_T05, candidates
            )
        assert ledger.cited([PL])[PL] == before
        ledger.set_cause("S010", PL, Cause(categoria=REWORK, etapa=Stage.PAINT), EV_T03, candidates)
        corrected = ledger.cited([PL])[PL]
    assert str(refusal.value) == (
        f"{PL} is linked to active cause {outcome.active_cause_id} (retrabajo in pintura); "
        "its cause cannot change while the raise is in force"
    )
    assert (corrected.evidence, corrected.active_cause_id) == (EV_T03, None)


def test_e8a_duplicate_raise_names_the_covering_cause(registry: SqliteRegistry) -> None:
    seed_ac2(registry)
    with at(registry, "S011") as ledger, pytest.raises(DuplicateRaise) as refusal:
        ledger.raise_severity("S011", CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05, [])
    assert registry.causes.in_force() == (AC2,)
    assert str(refusal.value) == "active cause S010-causa-1 already covers Pickup in montaje, any market"


@pytest.mark.parametrize(
    ("snapshot", "scope", "ac2", "expected_id"),
    [
        ("S011", PICKUP_ANY.model_copy(update={"mercado": Market.LOCAL}), "in_force", "S011-causa-1"),
        ("S004", SUV_EUROPE, None, "S004-causa-1"),
        ("S013", PICKUP_ANY, "lifted", "S013-causa-1"),
    ],
    ids=["b_other_market", "c_no_case", "d_after_lift"],
)
def test_e8_raise_opens_an_active_cause_with_the_next_id(
    registry: SqliteRegistry, snapshot: str, scope: CauseScope, ac2: str | None, expected_id: str
) -> None:
    if ac2 is not None:
        seed_ac2(registry, "S012" if ac2 == "lifted" else None)
    with at(registry, snapshot) as ledger:
        outcome = ledger.raise_severity(snapshot, CauseCategory.LINE_STOP, scope, EV_T05, [])
        opened = registry.causes.get_active(expected_id)
    assert (outcome.active_cause_id, outcome.linked) == (expected_id, ())
    assert opened is not None
    assert (opened.scope, opened.opened_at, opened.opened_by) == (scope, snapshot, EV_T05)


@pytest.mark.parametrize(
    "pe_cause", [CauseCategory.MISSING_PARTS, CauseCategory.LINE_STOP], ids=["other", "same"]
)
def test_e10_raise_links_matching_cases_and_attaches_its_cause(
    registry: SqliteRegistry, pe_cause: CauseCategory
) -> None:
    with at(registry, "S007", PE):
        pass
    pe_cited = CitedCause(categoria=pe_cause, etapa=Stage.ASSEMBLY, evidence=EV_T04, set_at="S008")
    with at(registry, "S008", SEL8):
        registry.causes.set_cited(PE, pe_cited)
    candidates = [
        cand(PL, Stage.ASSEMBLY),
        cand(PB, None),
        cand(SEL8, Stage.ASSEMBLY),
        cand(PE, Stage.ASSEMBLY),
    ]
    with at(registry, "S010", PL, PB) as ledger:
        outcome = ledger.raise_severity("S010", CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05, candidates)
        cited = ledger.cited([PL, PB, PE, SEL8])
        links = registry.causes.links([AC2_ID])
    linked = (PL, PB, PE) if pe_cause is CauseCategory.LINE_STOP else (PL, PB)
    attached = CitedCause(
        categoria=CauseCategory.LINE_STOP,
        etapa=Stage.ASSEMBLY,
        evidence=EV_T05,
        set_at="S010",
        active_cause_id=AC2_ID,
    )
    assert (outcome.active_cause_id, outcome.linked) == (AC2_ID, linked)
    assert links == {AC2_ID: linked}
    assert cited == {PL: attached, PB: attached, PE: pe_cited}


@pytest.mark.parametrize(
    ("active_id", "bitacora", "lifted_before", "error", "message"),
    [
        ("S099-causa-1", "T03", False, UnknownActiveCause, "unknown active cause S099-causa-1"),
        (AC1_ID, "T03", True, RaiseAlreadyLifted, "active cause S004-causa-1 was lifted at S008"),
        (
            AC1_ID,
            "T02",
            False,
            LiftNotLater,
            "T02 is not later than T02, which opened active cause S004-causa-1",
        ),
        (
            AC1_ID,
            "T01",
            False,
            LiftNotLater,
            "T01 is not later than T02, which opened active cause S004-causa-1",
        ),
    ],
    ids=["a_unknown", "b_already_lifted", "c_same_logbook", "c_earlier_logbook"],
)
def test_e9_lift_refusals(
    registry: SqliteRegistry,
    active_id: str,
    bitacora: str,
    lifted_before: bool,
    error: type[RejectedRequest],
    message: str,
) -> None:
    with at(registry, "S004"):
        registry.causes.open(AC1)
    if lifted_before:
        with at(registry, "S008"):
            registry.causes.lift(AC1_ID, "S008", EV_T04)
    snapshot = "S010" if lifted_before else "S006"
    with at(registry, snapshot) as ledger, pytest.raises(error) as refusal:
        ledger.lift(snapshot, active_id, Evidence(bitacora=bitacora, fragmento=F3))
    assert str(refusal.value) == message


def test_e9d_lift_accepts_a_later_logbook_whatever_it_reports(registry: SqliteRegistry) -> None:
    with at(registry, "S004"):
        registry.causes.open(AC1)
    with at(registry, "S006") as ledger:
        ledger.lift("S006", AC1_ID, EV_T03)
        lifted = registry.causes.get_active(AC1_ID)
    assert lifted is not None
    assert (lifted.in_force, lifted.lifted_at, lifted.lifted_by) == (False, "S006", EV_T03)


def test_recheck_links_a_case_that_enters_the_scope_while_the_cause_is_in_force(
    registry: SqliteRegistry,
) -> None:
    """Risk: a case entering the scope after the raise is never raised (sticky re-check, Q-49)."""
    with at(registry, "S010") as ledger:
        ledger.raise_severity("S010", CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05, [])
    pe = "S011-Pickup-Europa"
    with at(registry, "S011", pe) as ledger:
        added = ledger.recheck("S011", [cand(pe, Stage.ASSEMBLY)])
        again = ledger.recheck("S011", [cand(pe, Stage.ASSEMBLY)])
        raised = ledger.raised([case_with(pe, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM)])
        cited = ledger.cited([pe])[pe]
        view = ledger.in_force_view()
    assert (added, again) == (True, False)
    assert raised == {Combination(modelo=Model.PICKUP, mercado=Market.EUROPE)}
    assert (cited.categoria, cited.set_at, cited.active_cause_id) == (CauseCategory.LINE_STOP, "S011", AC2_ID)
    assert [(cause.active_cause_id, linked) for cause, linked in view] == [(AC2_ID, (pe,))]


def test_r7_with_two_causes_in_force_the_oldest_attaches_and_a_later_other_pair_does_not_link(
    registry: SqliteRegistry,
) -> None:
    pickup_local = PICKUP_ANY.model_copy(update={"mercado": Market.LOCAL})
    with at(registry, "S010", PL) as ledger:
        first = ledger.raise_severity("S010", CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05, [])
        second = ledger.raise_severity("S010", CauseCategory.MISSING_PARTS, pickup_local, EV_T03, [])
        added = ledger.recheck("S010", [cand(PL, Stage.ASSEMBLY)])
        links = registry.causes.links([first.active_cause_id, second.active_cause_id])
        cited = ledger.cited([PL])[PL]
    assert added is True
    assert links == {first.active_cause_id: (PL,)}
    assert cited == CitedCause(
        categoria=CauseCategory.LINE_STOP,
        etapa=Stage.ASSEMBLY,
        evidence=EV_T05,
        set_at="S010",
        active_cause_id=first.active_cause_id,
    )


def test_lifting_one_of_two_causes_keeps_the_case_raised_until_both_are_lifted(
    registry: SqliteRegistry,
) -> None:
    """Risk: a lift of one cause drops the raise that another cause still holds (Q-25)."""
    se = case_with(SE, CaseState.OPEN, Severity.MEDIUM, Severity.MEDIUM)
    combination = Combination(modelo=Model.SUV, mercado=Market.EUROPE)
    with at(registry, "S005", SE) as ledger:
        candidates = [cand(SE, Stage.QUALITY)]
        first = ledger.raise_severity("S005", QUALITY_HOLD, SUV_EUROPE, EV_T02, candidates)
        wide = SUV_EUROPE.model_copy(update={"mercado": None})
        second = ledger.raise_severity("S005", QUALITY_HOLD, wide, EV_T02, candidates)
    with at(registry, "S006") as ledger:
        ledger.lift("S006", first.active_cause_id, EV_T03)
        after_one = ledger.raised([se])
        ledger.lift("S006", second.active_cause_id, EV_T03)
        after_both = ledger.raised([se])
    assert (after_one, after_both) == (frozenset({combination}), frozenset())
