"""008 T6: 'ThresholdPipeline' with a cause ledger over the incident fixture (E11-E14, E34, X1, X2)."""

import pytest
from incident_builders import (
    PB,
    PL,
    SE,
    SEL,
    SL,
    IncidentScenario,
    delayed_unit,
    incident_scenario,
)
from incident_runs import (
    AC1,
    AC2,
    EV_T02,
    EV_T03,
    EV_T04,
    EV_T05,
    PICKUP_ANY,
    SUV_EUROPE,
    SUV_PAINT_ANY,
    SUV_QUALITY_ANY,
    IncidentRun,
    incident_run,
)

from plant_monitor.cases.ledger import DuplicateRaise
from plant_monitor.cases.tracker import CaseDelta
from plant_monitor.domain.cases import Case, CaseEvent, CaseState
from plant_monitor.domain.causes import ActiveCause, Cause, CauseCategory, CitedCause, Evidence
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.notices import Notice, NoticeType, Origin, Reason
from plant_monitor.runner.pipeline import SnapshotDecision

PL_CASE = "S010-Pickup-Local"
PB_CASE = "S010-Pickup-Brasil"
PE_CASE = "S011-Pickup-Europa"
SEL_CASE = "S011-Sedán-Local"
SE_CASE = "S005-SUV-Europa"
SL_CASE = "S009-SUV-Local"
PB_E12 = "S006-Pickup-Brasil"
T03_REPAINT = Evidence(
    bitacora="T03", fragmento="Se separaron las SUV en Gris Grafito. Vuelven a la cabina de repintado."
)


def delta_of(decision: SnapshotDecision) -> CaseDelta:
    """The decision's delta, which the pipeline always sets."""
    assert decision.delta is not None
    return decision.delta


def events_of(decision: SnapshotDecision, case_id: str) -> tuple[CaseEvent, ...]:
    """Lifecycle events of one case in the decision's delta."""
    return tuple(e.event for e in delta_of(decision).events if e.case_id == case_id)


def alerts_of(decision: SnapshotDecision) -> list[Notice]:
    """The decision's 'alerta_inmediata' notices."""
    return [n for n in decision.notices.decisions if n.tipo is NoticeType.ALERT]


def notice_of(decision: SnapshotDecision, case_id: str, tipo: NoticeType) -> Notice:
    """The one notice of 'tipo' for 'case_id'."""
    (notice,) = [n for n in decision.notices.decisions if n.case_id == case_id and n.tipo is tipo]
    return notice


def stored(run: IncidentRun, case_id: str) -> Case:
    """The case as stored in the registry."""
    case = run.registry.cases.get_case(case_id)
    assert case is not None
    return case


def links_of(run: IncidentRun) -> list[tuple[str, tuple[str, ...]]]:
    """Active cause ids in force with their linked case ids."""
    return [(cause.active_cause_id, ids) for cause, ids in run.ledger.in_force_view()]


def raise_ac2(run: IncidentRun, decision: SnapshotDecision) -> SnapshotDecision:
    """Raise AC2 {Pickup, montaje, null} citing T05 and re-decide."""
    return run.raise_cause(decision, CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05)


def test_e11_links_stay_sticky_and_a_case_opening_in_scope_opens_escalated() -> None:
    scenario = incident_scenario()
    pl_in_quality = delayed_unit(PL, Stage.QUALITY, "2026-03-03T08:00", "LOC-0304", "U-PL-001")
    scenario.units[11] = [pl_in_quality, *scenario.units[11][1:]]
    scenario.gaps[SEL] = {1: -2, 11: -3}
    scenario.units[11].append(delayed_unit(SEL, Stage.ASSEMBLY, "2026-03-03T08:00", "LOC-0304", "U-SEL-001"))
    with incident_run(scenario) as run:
        run.through(9)
        run.step(10, lambda d: raise_ac2(run, d))
        d11 = run.step(11)

        for case_id in (PL_CASE, PB_CASE):
            case = stored(run, case_id)
            assert (case.state, case.current_severity) == (CaseState.ESCALATED, Severity.CRITICAL)
        assert events_of(d11, PE_CASE) == (CaseEvent.OPENED, CaseEvent.ESCALATED)
        (alert,) = alerts_of(d11)
        assert alert.case_id == PE_CASE
        assert (alert.motivo, alert.origen) == ((Reason.LOGBOOK,), Origin.AGENT)
        assert alert.causa == Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY)
        assert alert.evidencia == (EV_T05,)
        assert run.ledger.cited([PE_CASE])[PE_CASE] == CitedCause(
            categoria=CauseCategory.LINE_STOP,
            etapa=Stage.ASSEMBLY,
            evidence=EV_T05,
            set_at="S011",
            active_cause_id=AC2,
        )
        assert links_of(run) == [(AC2, (PL_CASE, PB_CASE, PE_CASE))]
        assert d11.in_force == run.ledger.in_force_view()
        assert not stored(run, SEL_CASE).raised
        assert stored(run, SEL_CASE).state is CaseState.OPEN


def paint_variant() -> IncidentScenario:
    """SL opens at S009 in 'calidad', moves to 'pintura' at S011 and back to 'calidad' at S012."""
    scenario = incident_scenario()
    scenario.gaps[SL] = {9: -3, 10: -3, 11: -3, 12: -3}
    for number in (9, 10, 11, 12):
        stage = Stage.PAINT if number == 11 else Stage.QUALITY
        unit = delayed_unit(SL, stage, "2026-03-03T08:00", "LOC-0305", "U-SL-001")
        scenario.units.setdefault(number, []).append(unit)
    return scenario


def run_paint_variant(run: IncidentRun, cited: Cause | None, evidence: Evidence) -> SnapshotDecision:
    """Run to S011: SL optionally cited at S009, AC {SUV, pintura, null} raised at S010."""
    run.through(8)

    def cite(decision: SnapshotDecision) -> SnapshotDecision:
        assert cited is not None
        run.ledger.set_cause("S009", SL_CASE, cited, evidence, decision.candidates)
        return decision

    run.step(9, cite if cited is not None else None)
    run.step(10, lambda d: run.raise_cause(d, CauseCategory.REWORK, SUV_PAINT_ANY, EV_T05))
    assert links_of(run) == [("S010-causa-1", ())]
    return run.step(11)


def test_e11_variant_a_case_is_linked_when_its_stage_enters_the_scope_and_stays_linked() -> None:
    with incident_run(paint_variant()) as run:
        d11 = run_paint_variant(run, None, EV_T05)
        sl = stored(run, SL_CASE)
        assert (sl.state, sl.raised) == (CaseState.ESCALATED, True)
        alert = notice_of(d11, SL_CASE, NoticeType.ALERT)
        assert alert.causa == Cause(categoria=CauseCategory.REWORK, etapa=Stage.PAINT)
        assert links_of(run) == [("S010-causa-1", (SL_CASE,))]
        run.step(12)
        assert stored(run, SL_CASE).raised
        assert links_of(run) == [("S010-causa-1", (SL_CASE,))]


@pytest.mark.parametrize(
    ("cause", "evidence", "linked"),
    [
        pytest.param(
            Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY),
            EV_T02,
            False,
            id="a-other-cause",
        ),
        pytest.param(
            Cause(categoria=CauseCategory.REWORK, etapa=Stage.PAINT), T03_REPAINT, True, id="b-same-cause"
        ),
    ],
)
def test_e34_a_case_with_another_cited_cause_is_never_linked(
    cause: Cause, evidence: Evidence, linked: bool
) -> None:
    with incident_run(paint_variant()) as run:
        run_paint_variant(run, cause, evidence)
        run.step(12)
        sl = stored(run, SL_CASE)
        assert sl.raised is linked
        assert links_of(run) == [("S010-causa-1", (SL_CASE,) if linked else ())]
        cited = run.ledger.cited([SL_CASE])[SL_CASE]
        assert (cited.categoria, cited.etapa, cited.evidence) == (cause.categoria, cause.etapa, evidence)
        assert (cited.set_at, cited.active_cause_id) == ("S009", None)


def test_e12_a_case_resolved_by_the_first_track_stays_active_when_a_raise_links_it() -> None:
    scenario = incident_scenario()
    scenario.gaps[PB] = {6: -3}
    scenario.units[6].append(delayed_unit(PB, Stage.ASSEMBLY, "2026-03-02T14:00", "BRA-0304", "U-PB-001"))
    first: list[SnapshotDecision] = []

    def act(decision: SnapshotDecision) -> SnapshotDecision:
        first.append(decision)
        return raise_ac2(run, decision)

    with incident_run(scenario) as run:
        run.through(7)
        d8 = run.step(8, act)

        (before,) = [c for c in delta_of(first[0]).cases if c.case_id == PB_E12]
        assert (before.state, before.clean_streak) == (CaseState.RESOLVED, 2)
        after = stored(run, PB_E12)
        assert (after.state, after.raised, after.current_severity) == (
            CaseState.ESCALATED,
            True,
            Severity.CRITICAL,
        )
        assert events_of(d8, PB_E12) == (CaseEvent.ESCALATED, CaseEvent.SEVERITY_CHANGED)
        assert PB_E12 not in [c.case_id for c in run.registry.cases.resolved_unreported()]
        (alert,) = alerts_of(d8)
        assert (alert.case_id, alert.motivo) == (PB_E12, (Reason.LOGBOOK,))
        assert links_of(run) == [("S008-causa-1", (PB_E12,))]


@pytest.mark.parametrize(
    ("with_ac3", "state", "peak"),
    [
        pytest.param(True, CaseState.ESCALATED, None, id="two-causes"),
        pytest.param(False, CaseState.RESOLVED, Severity.CRITICAL, id="variant-no-ac3"),
    ],
)
def test_e13_a_lift_undoes_only_its_own_cause(
    with_ac3: bool, state: CaseState, peak: Severity | None
) -> None:
    with incident_run() as run:
        run.through(3)
        run.step(4, lambda d: run.raise_cause(d, CauseCategory.QUALITY_HOLD, SUV_EUROPE, EV_T02))
        ac3 = lambda d: run.raise_cause(d, CauseCategory.QUALITY_HOLD, SUV_QUALITY_ANY, EV_T02)  # noqa: E731
        run.step(5, ac3 if with_ac3 else None)
        run.through(7, first=6)
        if with_ac3:
            assert [ids for _, ids in links_of(run)] == [(SE_CASE,), (SE_CASE,)]

        d8 = run.step(8, lambda d: run.lift_cause(d, AC1, EV_T04))

        assert stored(run, SE_CASE).state is state
        lifted = run.registry.causes.get_active(AC1)
        assert lifted is not None
        assert lifted.lifted_at == "S008"
        if peak is not None:
            assert notice_of(d8, SE_CASE, NoticeType.SHIFT_REPORT).severidad_maxima is peak


def test_e14_a_raise_and_its_lift_in_one_snapshot_leave_the_cause_but_not_the_severity() -> None:
    steps: dict[str, SnapshotDecision] = {}

    def act(decision: SnapshotDecision) -> SnapshotDecision:
        decision = run.raise_cause(decision, CauseCategory.QUALITY_HOLD, SUV_EUROPE, EV_T02)
        steps["raised"] = decision
        decision = run.lift_cause(decision, "S006-causa-1", EV_T03)
        steps["lifted"] = decision
        decision = run.raise_cause(decision, CauseCategory.QUALITY_HOLD, SUV_EUROPE, EV_T03)
        steps["again"] = decision
        with pytest.raises(DuplicateRaise, match="already covers SUV in calidad, Europa"):
            run.raise_cause(decision, CauseCategory.QUALITY_HOLD, SUV_EUROPE, EV_T03)
        return decision

    with incident_run() as run:
        run.through(5)
        run.step(6, act)

        raised_alert = notice_of(steps["raised"], SE_CASE, NoticeType.ALERT)
        assert raised_alert.causa == Cause(categoria=CauseCategory.QUALITY_HOLD, etapa=Stage.QUALITY)
        assert alerts_of(steps["lifted"]) == []
        (lifted_case,) = [c for c in delta_of(steps["lifted"]).cases if c.case_id == SE_CASE]
        assert (lifted_case.state, lifted_case.current_severity) == (CaseState.FOLLOW_UP, Severity.MEDIUM)
        news = notice_of(steps["lifted"], SE_CASE, NoticeType.SHIFT_REPORT)
        assert (news.motivo, news.origen) == ((Reason.GAP,), Origin.THRESHOLD)
        assert (news.causa.categoria, news.evidencia) == (CauseCategory.QUALITY_HOLD, (EV_T02,))
        first = run.registry.causes.get_active("S006-causa-1")
        assert first is not None
        assert (first.opened_at, first.lifted_at) == ("S006", "S006")
        assert links_of(run) == [("S006-causa-2", (SE_CASE,))]
        assert stored(run, SE_CASE).state is CaseState.ESCALATED
        cited = run.ledger.cited([SE_CASE])[SE_CASE]
        assert (cited.evidence, cited.active_cause_id) == (EV_T02, "S006-causa-1")


def test_r12_news_of_a_case_resolved_earlier_in_the_shift_keeps_its_cited_cause() -> None:
    cause = Cause(categoria=CauseCategory.REWORK, etapa=Stage.QUALITY)
    scenario = incident_scenario()
    scenario.gaps[SE] = {4: -1, 5: -4, 6: -4, 7: -4}

    def cite(decision: SnapshotDecision) -> SnapshotDecision:
        run.ledger.set_cause("S005", SE_CASE, cause, EV_T03, decision.candidates)
        return decision

    with incident_run(scenario) as run:
        run.through(4)
        run.step(5, cite)
        run.through(8, first=6)
        d9 = run.step(9)
        d10 = run.step(10)

        assert [c.state for c in delta_of(d9).cases if c.case_id == SE_CASE] == [CaseState.RESOLVED]
        assert SE_CASE not in [c.case_id for c in delta_of(d10).cases]
        news = notice_of(d10, SE_CASE, NoticeType.SHIFT_REPORT)
        assert news.causa == cause
        assert news.evidencia == (EV_T03,)


def test_x1_a_raise_on_a_case_already_critical_by_threshold_adds_no_event_or_alert() -> None:
    with incident_run() as run:
        run.through(11)
        seen: dict[str, SnapshotDecision] = {}

        def act(decision: SnapshotDecision) -> SnapshotDecision:
            seen["before"] = decision
            return raise_ac2(run, decision)

        after = run.step(12, act)

        def signature(decision: SnapshotDecision) -> list[tuple[str, tuple[Reason, ...], Origin, Severity]]:
            return [(n.case_id, n.motivo, n.origen, n.severidad) for n in alerts_of(decision)]

        linked = {case_id for _, ids in links_of(run) for case_id in ids}
        assert {PL_CASE, PB_CASE} <= linked
        assert events_of(after, PL_CASE) == events_of(seen["before"], PL_CASE)
        assert signature(after) == signature(seen["before"])
        assert (PL_CASE, (Reason.GAP,), Origin.THRESHOLD, Severity.CRITICAL) in signature(after)


def test_x2_a_pipeline_without_a_ledger_ignores_a_stored_active_cause() -> None:
    stored_cause = ActiveCause(
        active_cause_id="S009-causa-1",
        categoria=CauseCategory.LINE_STOP,
        scope=PICKUP_ANY,
        opened_at="S009",
        opened_by=EV_T05,
    )

    def open_cause(decision: SnapshotDecision) -> SnapshotDecision:
        run.registry.causes.open(stored_cause)
        return decision

    with incident_run(with_ledger=False) as run:
        run.through(8)
        run.step(9, open_cause)
        d10 = run.step(10)

        assert run.registry.causes.in_force() == (stored_cause,)
        assert d10.in_force == ()
        assert not stored(run, PL_CASE).raised
        assert stored(run, PL_CASE).state is CaseState.OPEN


def test_risk_decision_cited_holds_the_cases_whose_cause_is_cited() -> None:
    """Risk: the investigator task would list a case that already has its cause as still without one."""
    with incident_run() as run:
        run.through(9)

        def cite(decision: SnapshotDecision) -> SnapshotDecision:
            cause = Cause(categoria=CauseCategory.LINE_STOP, etapa=Stage.ASSEMBLY)
            run.ledger.set_cause("S010", PL_CASE, cause, EV_T05, decision.candidates)
            return run.pipeline.redecide(decision)

        decision = run.step(10, cite)
    assert decision.cited == frozenset({PL_CASE})
