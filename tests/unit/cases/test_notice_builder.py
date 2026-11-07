"""004 T6-T7, T11: 'motivo', 'origen', default cause, 'case_notice' (E19-E23), decisions (E37-E39)."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from plant_monitor.cases.facts import CaseFacts
from plant_monitor.cases.notice_builder import (
    ShiftClose,
    build_snapshot_notices,
    case_notice,
    default_cause,
    origin_for,
    reasons_for,
)
from plant_monitor.cases.novelty import NewsReason, active_rows, news_reasons
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.tracker import CaseDelta, CaseTracker, TrackedEvent
from plant_monitor.domain.cases import CaseEvent, CaseState
from plant_monitor.domain.causes import Cause, CauseCategory
from plant_monitor.domain.enums import Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, SnapshotCommit, all_combinations
from plant_monitor.domain.notices import Notice, NoticeType, Origin, Reason
from plant_monitor.metrics.thresholds import load_thresholds

from builders import PICKUP_BRAZIL, case_with, combination_of, history_row, measured, metrics_with

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "plant"
NO_RAISES: frozenset[Combination] = frozenset()

OPEN = CaseState.OPEN
FOLLOW_UP = CaseState.FOLLOW_UP
ESCALATED = CaseState.ESCALATED
RESOLVED = CaseState.RESOLVED
NONE = Severity.NONE
MEDIUM = Severity.MEDIUM
HIGH = Severity.HIGH
CRITICAL = Severity.CRITICAL

E22A_TEXT = (
    "Pickup × Brasil escaló a crítica en S020 por gap: gap −12 u (−40 %), retraso 1 día. "  # noqa: RUF001
    "Causa no declarada, etapa montaje."
)


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id and no anomalies or units."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def pb(gap: Severity, delay: Severity, bottleneck: Stage | None = Stage.ASSEMBLY) -> CombinationMetrics:
    """Pickup-Brasil metrics with the given gap and delay severities."""
    return measured(PICKUP_BRAZIL, -4.0, -13.33, 0.0, bottleneck, gap, delay)


def e4_facts() -> CaseFacts:
    """E4's case and metrics at S020 with cause row S020 'montaje'."""
    case = case_with("S015-Pickup-Brasil", ESCALATED, CRITICAL, CRITICAL, at="S020")
    current = measured(PICKUP_BRAZIL, -12.0, -40.0, 1.0, Stage.ASSEMBLY, CRITICAL, HIGH)
    return CaseFacts(case, current, history_row(case.case_id, "S020", Stage.ASSEMBLY, minimum=CRITICAL))


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


@pytest.fixture
def tracker(registry: SqliteRegistry) -> CaseTracker:
    """Real tracker on the registry's cases, with fixture resolution thresholds."""
    return CaseTracker(registry.cases, load_thresholds(FIXTURES / "umbrales.yaml").resolucion)


# --- T6 · E19 'motivo' and 'origen' (Q-31) ---

PB_ID = "S010-Pickup-Brasil"
PB_ROW = history_row(PB_ID, "S010", Stage.ASSEMBLY)


@pytest.mark.parametrize(
    ("facts", "motivo", "origen"),
    [
        pytest.param(
            CaseFacts(case_with(PB_ID, FOLLOW_UP, HIGH, HIGH, at="S020"), pb(HIGH, NONE), PB_ROW),
            (Reason.GAP,),
            Origin.THRESHOLD,
            id="a-gap-only",
        ),
        pytest.param(
            CaseFacts(
                case_with(PB_ID, ESCALATED, CRITICAL, CRITICAL, at="S020"), pb(CRITICAL, CRITICAL), PB_ROW
            ),
            (Reason.GAP, Reason.DELAY),
            Origin.THRESHOLD,
            id="b-gap-and-delay",
        ),
        pytest.param(
            CaseFacts(case_with(PB_ID, FOLLOW_UP, HIGH, HIGH, at="S020"), pb(MEDIUM, HIGH), PB_ROW),
            (Reason.DELAY,),
            Origin.THRESHOLD,
            id="c-gap-below-effective",
        ),
        pytest.param(
            CaseFacts(
                case_with(PB_ID, ESCALATED, MEDIUM, CRITICAL, at="S020", raised=True),
                pb(MEDIUM, NONE),
                PB_ROW,
            ),
            (Reason.LOGBOOK,),
            Origin.AGENT,
            id="d-necessary-raise",
        ),
        pytest.param(
            CaseFacts(
                case_with(PB_ID, ESCALATED, CRITICAL, CRITICAL, at="S020", raised=True),
                pb(CRITICAL, HIGH),
                PB_ROW,
            ),
            (Reason.GAP,),
            Origin.THRESHOLD,
            id="e-unnecessary-raise",
        ),
        pytest.param(
            CaseFacts(
                case_with(PB_ID, FOLLOW_UP, NONE, MEDIUM, at="S011", clean_streak=1), pb(NONE, NONE), PB_ROW
            ),
            (),
            Origin.THRESHOLD,
            id="f-clean-snapshot",
        ),
        pytest.param(
            CaseFacts(
                case_with(
                    PB_ID, RESOLVED, NONE, NONE, at="S011", reported=(FOLLOW_UP, NONE, "S010"), clean_streak=2
                ),
                None,
                PB_ROW,
            ),
            (),
            Origin.THRESHOLD,
            id="g-resolved-earlier",
        ),
    ],
)
def test_e19_motivo_and_origen(facts: CaseFacts, motivo: tuple[Reason, ...], origen: Origin) -> None:
    assert reasons_for(facts) == motivo
    assert origin_for(motivo) is origen


def test_e19h_active_case_above_ninguna_without_metrics_raises_naming_it() -> None:
    facts = CaseFacts(case_with(PB_ID, FOLLOW_UP, MEDIUM, MEDIUM, at="S011"), None, PB_ROW)
    with pytest.raises(ValueError, match=PB_ID):
        reasons_for(facts)


# --- T7 · E20 default cause and its stage (Q-17, Q-32) ---


def test_e20a_default_cause_is_no_declarada_with_the_given_stage() -> None:
    assert default_cause(Stage.ASSEMBLY) == Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY)
    assert default_cause(None) == Cause(categoria=CauseCategory.UNDECLARED, etapa=None)


def test_e20b_deviation_now_takes_this_snapshot_bottleneck() -> None:
    case = case_with("S020-Pickup-Brasil", OPEN, HIGH, HIGH, at="S020")
    facts = CaseFacts(case, pb(HIGH, NONE, Stage.ASSEMBLY), history_row(case.case_id, "S020", Stage.ASSEMBLY))
    notice = case_notice(NoticeType.SHIFT_REPORT, facts, "S020")
    assert notice.causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY)
    assert notice.evidencia == ()


def test_e20c_clean_case_takes_its_last_deviation_stage_while_the_row_keeps_the_current_one() -> None:
    case = case_with(
        "S019-Pickup-Brasil", FOLLOW_UP, NONE, NONE, at="S021", reported=(FOLLOW_UP, HIGH, "S020")
    )
    current = pb(NONE, NONE, Stage.BODY)
    notice = case_notice(
        NoticeType.SHIFT_REPORT,
        CaseFacts(case, current, history_row(case.case_id, "S020", Stage.ASSEMBLY)),
        "S021",
    )
    assert notice.causa.etapa is Stage.ASSEMBLY
    assert notice.evidencia == ()
    (row,) = active_rows([case], {PICKUP_BRAZIL: current})
    assert row.etapa_cuello is Stage.BODY


def test_e20d_case_resolved_earlier_carries_its_opening_stage() -> None:
    case = case_with(
        "S009-Pickup-Brasil",
        RESOLVED,
        NONE,
        NONE,
        at="S011",
        reported=(FOLLOW_UP, NONE, "S010"),
        clean_streak=2,
    )
    facts = CaseFacts(case, None, history_row(case.case_id, "S009", Stage.PAINT, state=OPEN))
    notice = case_notice(NoticeType.SHIFT_REPORT, facts, "S012")
    assert (notice.tipo, notice.estado) == (NoticeType.SHIFT_REPORT, RESOLVED)
    assert notice.causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.PAINT)
    assert notice.evidencia == ()


def test_e20e_last_deviation_without_bottleneck_gives_null_stage() -> None:
    case = case_with(
        "S020-Pickup-Brasil", FOLLOW_UP, NONE, NONE, at="S022", reported=(FOLLOW_UP, MEDIUM, "S021")
    )
    facts = CaseFacts(case, pb(NONE, NONE, Stage.ASSEMBLY), history_row(case.case_id, "S021", None))
    notice = case_notice(NoticeType.SHIFT_REPORT, facts, "S022")
    assert notice.causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=None)
    assert notice.evidencia == ()


# --- T7 · E23 full alert (US-04 #3), also E4's notice ---


def test_e23_full_alert_notice() -> None:
    notice = case_notice(NoticeType.ALERT, e4_facts(), "S020")
    assert notice.model_dump(mode="json") == {
        "notice_id": "S020-alerta_inmediata-S015-Pickup-Brasil",
        "snapshot_id": "S020",
        "case_id": "S015-Pickup-Brasil",
        "modelo": "Pickup",
        "mercado": "Brasil",
        "tipo": "alerta_inmediata",
        "severidad": "critica",
        "severidad_maxima": "critica",
        "estado": "escalado",
        "origen": "umbral",
        "motivo": ["gap"],
        "causa": {"categoria": "no_declarada", "etapa": "montaje"},
        "evidencia": [],
        "texto": E22A_TEXT,
    }


@pytest.mark.parametrize(
    ("tipo", "facts"),
    [
        pytest.param(
            NoticeType.ALERT,
            CaseFacts(e4_facts().case, None, e4_facts().cause_row),
            id="alert-without-current-metrics",
        ),
        pytest.param(
            NoticeType.SHIFT_REPORT,
            CaseFacts(
                case_with(PB_ID, FOLLOW_UP, MEDIUM, MEDIUM, at="S012", reported=(FOLLOW_UP, MEDIUM, "S010")),
                pb(MEDIUM, NONE),
                PB_ROW,
            ),
            id="informe-for-a-case-that-is-not-news",
        ),
        pytest.param(
            NoticeType.NO_NOTICE,
            CaseFacts(case_with(PB_ID, OPEN, MEDIUM, MEDIUM, at="S010"), pb(MEDIUM, NONE), PB_ROW),
            id="sin-aviso-for-a-news-case",
        ),
    ],
)
def test_case_notice_rejects_a_type_that_contradicts_the_rules(tipo: NoticeType, facts: CaseFacts) -> None:
    """Plan guards on 'case_notice', so a caller cannot silence news or alert without metrics."""
    with pytest.raises(ValueError):
        case_notice(tipo, facts, facts.case.last_snapshot_id)


# --- Notice parts of E6, E7 and E17 ---


def test_e17_decisions_are_informe_at_mid_and_sin_aviso_at_close() -> None:
    reported = (FOLLOW_UP, MEDIUM, "S010")
    row = history_row(PB_ID, "S010", Stage.ASSEMBLY)
    at_mid = case_with(PB_ID, FOLLOW_UP, NONE, NONE, at="S011", reported=reported, clean_streak=1)
    at_close = case_with(PB_ID, FOLLOW_UP, MEDIUM, MEDIUM, at="S012", reported=reported)
    mid = case_notice(NoticeType.SHIFT_REPORT, CaseFacts(at_mid, pb(NONE, NONE), row), "S011")
    close_metrics = pb(MEDIUM, NONE)
    close = case_notice(
        NoticeType.NO_NOTICE,
        CaseFacts(at_close, close_metrics, history_row(PB_ID, "S012", Stage.ASSEMBLY)),
        "S012",
    )
    assert (mid.notice_id, mid.tipo) == ("S011-informe_de_turno-S010-Pickup-Brasil", NoticeType.SHIFT_REPORT)
    assert (close.notice_id, close.tipo) == ("S012-sin_aviso-S010-Pickup-Brasil", NoticeType.NO_NOTICE)
    assert [r.case_id for r in active_rows([at_close], {PICKUP_BRAZIL: close_metrics})] == [PB_ID]


def test_e6_mid_snapshot_alert_is_the_only_decision_for_a_new_critical_case() -> None:
    """Needs 'build_snapshot_notices' (T11); E6's alert selection itself is in 'test_novelty.py'."""
    case = case_with("S010-Pickup-Brasil", ESCALATED, CRITICAL, CRITICAL)
    delta = CaseDelta(
        "S010",
        (TrackedEvent(case.case_id, CaseEvent.OPENED), TrackedEvent(case.case_id, CaseEvent.ESCALATED)),
        (case,),
    )
    metrics = {PICKUP_BRAZIL: measured(PICKUP_BRAZIL, -11.0, -36.7, 0.0, None, CRITICAL, NONE)}
    rows = {case.case_id: history_row(case.case_id, "S010", None, minimum=CRITICAL, state=ESCALATED)}
    built = build_snapshot_notices(delta, metrics, rows, None)
    assert [n.notice_id for n in built.decisions] == ["S010-alerta_inmediata-S010-Pickup-Brasil"]
    assert built.report is None
    assert built.to_mark == ()


def test_e7_notice_from_the_last_delta_is_the_only_alert(
    registry: SqliteRegistry, tracker: CaseTracker
) -> None:
    """Needs 'last_deviation_row' (T8), as E7 reads cause rows from the registry."""
    all_none = {combo: metrics_with(NONE, combination=combo) for combo in all_combinations()}
    with registry.processing(commit("S009")):
        tracker.track("S009", {**all_none, PICKUP_BRAZIL: metrics_with(HIGH)}, NO_RAISES)
    m = {**all_none, PICKUP_BRAZIL: measured(PICKUP_BRAZIL, -7.0, -23.3, 0.0, Stage.ASSEMBLY, HIGH, NONE)}
    with registry.processing(commit("S010")):
        tracker.track("S010", m, NO_RAISES)
        d2 = tracker.track("S010", m, frozenset({PICKUP_BRAZIL}))
        cause_row = registry.cases.last_deviation_row("S009-Pickup-Brasil")
    assert cause_row is not None
    (alerted,) = d2.cases
    notice = case_notice(NoticeType.ALERT, CaseFacts(alerted, m[PICKUP_BRAZIL], cause_row), "S010")
    assert notice.notice_id == "S010-alerta_inmediata-S009-Pickup-Brasil"
    assert notice.motivo == (Reason.LOGBOOK,)
    assert notice.origen is Origin.AGENT
    assert notice.causa == Cause(categoria=CauseCategory.UNDECLARED, etapa=Stage.ASSEMBLY)
    assert notice.evidencia == ()


# --- T11 · E37-E39 decisions of one snapshot ---


def ids_of(notices: tuple[Notice, ...]) -> list[str]:
    """'notice_id' of each notice, in order."""
    return [n.notice_id for n in notices]


def test_e37_mid_snapshot_decisions_alert_silence_news_and_resolution() -> None:
    sel = case_with(
        "S001-Sedán-Local", ESCALATED, CRITICAL, CRITICAL, at="S003", reported=(FOLLOW_UP, HIGH, "S002")
    )
    suv = case_with("S002-SUV-Local", FOLLOW_UP, HIGH, HIGH, at="S003", reported=(OPEN, HIGH, "S002"))
    pl = case_with(
        "S001-Pickup-Local", FOLLOW_UP, HIGH, HIGH, at="S003", reported=(FOLLOW_UP, MEDIUM, "S002")
    )
    pb = case_with(
        "S001-Pickup-Brasil",
        RESOLVED,
        NONE,
        NONE,
        at="S003",
        reported=(FOLLOW_UP, NONE, "S002"),
        clean_streak=2,
    )
    delta = CaseDelta(
        "S003",
        (
            TrackedEvent(sel.case_id, CaseEvent.ESCALATED),
            TrackedEvent(sel.case_id, CaseEvent.SEVERITY_CHANGED),
            TrackedEvent(pl.case_id, CaseEvent.SEVERITY_CHANGED),
            TrackedEvent(pb.case_id, CaseEvent.RESOLVED),
        ),
        (sel, suv, pl, pb),
    )
    metrics = {
        combination_of(sel.case_id): measured(
            combination_of(sel.case_id), -18.0, -50.0, 0.0, None, CRITICAL, NONE
        ),
        combination_of(suv.case_id): measured(
            combination_of(suv.case_id), -6.0, -25.0, 0.0, None, HIGH, NONE
        ),
        combination_of(pl.case_id): measured(combination_of(pl.case_id), -7.0, -23.3, 0.0, None, HIGH, NONE),
        combination_of(pb.case_id): measured(combination_of(pb.case_id), 0.0, 0.0, 0.0, None, NONE, NONE),
    }
    rows = {
        sel.case_id: history_row(sel.case_id, "S003", None, minimum=CRITICAL, state=ESCALATED),
        suv.case_id: history_row(suv.case_id, "S003", None, minimum=HIGH),
        pl.case_id: history_row(pl.case_id, "S003", None, minimum=HIGH),
        pb.case_id: history_row(pb.case_id, "S001", Stage.ASSEMBLY, state=OPEN),
    }
    built = build_snapshot_notices(delta, metrics, rows, None)
    assert ids_of(built.decisions) == [
        "S003-alerta_inmediata-S001-Sedán-Local",
        "S003-sin_aviso-S002-SUV-Local",
        "S003-informe_de_turno-S001-Pickup-Local",
        "S003-informe_de_turno-S001-Pickup-Brasil",
    ]
    assert [n.tipo for n in built.decisions] == [
        NoticeType.ALERT,
        NoticeType.NO_NOTICE,
        NoticeType.SHIFT_REPORT,
        NoticeType.SHIFT_REPORT,
    ]
    assert news_reasons(pl) == (NewsReason.SEVERITY_CHANGED,)
    assert news_reasons(pb) == (NewsReason.RESOLVED,)
    assert built.decisions[3].causa.etapa is Stage.ASSEMBLY
    assert built.report is None
    assert built.to_mark == ()


def test_e38_closing_snapshot_decisions_report_and_marking_set() -> None:
    sel = case_with(
        "S008-Sedán-Local", ESCALATED, CRITICAL, CRITICAL, at="S010", reported=(FOLLOW_UP, HIGH, "S008")
    )
    suv = case_with(
        "S008-SUV-Local", FOLLOW_UP, MEDIUM, MEDIUM, at="S010", reported=(FOLLOW_UP, MEDIUM, "S008")
    )
    pb = case_with(
        "S007-Pickup-Brasil",
        RESOLVED,
        NONE,
        NONE,
        at="S009",
        reported=(FOLLOW_UP, MEDIUM, "S008"),
        clean_streak=2,
    )
    delta = CaseDelta(
        "S010",
        (
            TrackedEvent(sel.case_id, CaseEvent.ESCALATED),
            TrackedEvent(sel.case_id, CaseEvent.SEVERITY_CHANGED),
        ),
        (sel, suv),
    )
    metrics = {
        combination_of(sel.case_id): measured(
            combination_of(sel.case_id), -14.0, -38.9, 0.0, Stage.PAINT, CRITICAL, NONE
        ),
        combination_of(suv.case_id): measured(
            combination_of(suv.case_id), -4.0, -11.1, 0.0, Stage.ASSEMBLY, MEDIUM, NONE
        ),
    }
    rows = {
        sel.case_id: history_row(sel.case_id, "S010", Stage.PAINT, minimum=CRITICAL, state=ESCALATED),
        suv.case_id: history_row(suv.case_id, "S010", Stage.ASSEMBLY),
        pb.case_id: history_row(pb.case_id, "S007", Stage.PAINT, state=OPEN),
    }
    built = build_snapshot_notices(delta, metrics, rows, ShiftClose("T05", (pb,)))
    assert ids_of(built.decisions) == [
        "S010-alerta_inmediata-S008-Sedán-Local",
        "S010-informe_de_turno-S008-Sedán-Local",
        "S010-sin_aviso-S008-SUV-Local",
        "S010-informe_de_turno-S007-Pickup-Brasil",
    ]
    report = built.report
    assert report is not None
    assert (report.turno_id, report.snapshot_id) == ("T05", "S010")
    assert report.novedades == (built.decisions[1], built.decisions[3])
    assert [(row.case_id, row.severidad, row.estado) for row in report.casos_activos] == [
        (sel.case_id, CRITICAL, ESCALATED),
        (suv.case_id, MEDIUM, FOLLOW_UP),
    ]
    assert built.to_mark == (sel.case_id, suv.case_id, pb.case_id)


def test_e39_empty_shift_still_yields_an_empty_report() -> None:
    built = build_snapshot_notices(CaseDelta("S010", (), ()), {}, {}, ShiftClose("T05", ()))
    assert built.decisions == ()
    report = built.report
    assert report is not None
    assert (report.turno_id, report.snapshot_id) == ("T05", "S010")
    assert report.novedades == ()
    assert report.casos_activos == ()
    assert built.to_mark == ()


def test_an_alerted_case_never_also_gets_sin_aviso_and_raises_naming_it() -> None:
    """Review finding: an 'escalated' event on an already-reported case would double-decide it at close."""
    case = case_with(
        "S008-Sedán-Local", ESCALATED, CRITICAL, CRITICAL, at="S010", reported=(ESCALATED, CRITICAL, "S009")
    )
    delta = CaseDelta("S010", (TrackedEvent(case.case_id, CaseEvent.ESCALATED),), (case,))
    combo = combination_of(case.case_id)
    metrics = {combo: measured(combo, -14.0, -38.9, 0.0, Stage.PAINT, CRITICAL, NONE)}
    rows = {case.case_id: history_row(case.case_id, "S010", Stage.PAINT, minimum=CRITICAL, state=ESCALATED)}
    with pytest.raises(ValueError, match=case.case_id):
        build_snapshot_notices(delta, metrics, rows, ShiftClose("T05", ()))


def test_e38b_case_resolved_at_the_closing_snapshot_is_reported_and_marked_once() -> None:
    """A case in the delta and in 'resolved_unreported' (passed raw) is decided, listed and marked once."""
    pb = case_with(
        "S007-Pickup-Brasil",
        RESOLVED,
        NONE,
        NONE,
        at="S010",
        reported=(FOLLOW_UP, NONE, "S008"),
        clean_streak=2,
    )
    delta = CaseDelta("S010", (TrackedEvent(pb.case_id, CaseEvent.RESOLVED),), (pb,))
    metrics = {PICKUP_BRAZIL: measured(PICKUP_BRAZIL, 0.0, 0.0, 0.0, None, NONE, NONE)}
    rows = {pb.case_id: history_row(pb.case_id, "S007", Stage.PAINT, state=OPEN)}
    built = build_snapshot_notices(delta, metrics, rows, ShiftClose("T05", (pb,)))
    assert news_reasons(pb) == (NewsReason.RESOLVED,)
    assert ids_of(built.decisions) == ["S010-informe_de_turno-S007-Pickup-Brasil"]
    report = built.report
    assert report is not None
    assert report.casos_activos == ()
    assert report.novedades == built.decisions
    assert built.to_mark == (pb.case_id,)
