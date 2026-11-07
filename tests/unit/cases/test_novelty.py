"""004 T3-T5: alerts from the last delta, novelty reasons, the report set and active rows (E4-E18, E46)."""

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from plant_monitor.cases.novelty import (
    NewsItem,
    NewsReason,
    active_rows,
    alerted_case_ids,
    alerts_for,
    expected_news,
    news_reasons,
    report_set,
)
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.tracker import CaseDelta, CaseTracker, TrackedEvent
from plant_monitor.domain.cases import Case, CaseEvent, CaseState
from plant_monitor.domain.enums import Market, Model, Severity, Stage
from plant_monitor.domain.models import Combination, CombinationMetrics, SnapshotCommit, all_combinations
from plant_monitor.domain.notices import ActiveCaseRow
from plant_monitor.metrics.thresholds import load_thresholds

from builders import PICKUP_BRAZIL, case_with, measured, metrics_with

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

PB_E4 = "S015-Pickup-Brasil"
E4_CASE = case_with(PB_E4, ESCALATED, CRITICAL, CRITICAL, at="S020")
E4_METRICS = {PICKUP_BRAZIL: measured(PICKUP_BRAZIL, -12.0, -40.0, 1.0, Stage.ASSEMBLY, CRITICAL, HIGH)}
E4_DELTA = CaseDelta(
    snapshot_id="S020",
    events=(TrackedEvent(PB_E4, CaseEvent.ESCALATED), TrackedEvent(PB_E4, CaseEvent.SEVERITY_CHANGED)),
    cases=(E4_CASE,),
)


def commit(snapshot_id: str) -> SnapshotCommit:
    """Commit with a hash derived from the snapshot id and no anomalies or units."""
    return SnapshotCommit(
        snapshot_id=snapshot_id, content_hash=f"hash-{snapshot_id}", anomalies=(), new_units={}
    )


def pb_metrics(pb: CombinationMetrics) -> dict[Combination, CombinationMetrics]:
    """All 9 combinations at 'ninguna' except Pickup-Brasil."""
    metrics = {combo: metrics_with(NONE, combination=combo) for combo in all_combinations()}
    metrics[PICKUP_BRAZIL] = pb
    return metrics


@pytest.fixture
def registry() -> Iterator[SqliteRegistry]:
    """In-memory registry, closed after the test."""
    with SqliteRegistry(":memory:") as reg:
        yield reg


@pytest.fixture
def tracker(registry: SqliteRegistry) -> CaseTracker:
    """Real tracker on the registry's cases, with fixture resolution thresholds."""
    return CaseTracker(registry.cases, load_thresholds(FIXTURES / "umbrales.yaml").resolucion)


# --- T3 · Alerts from the last delta (E4-E8) ---


def test_e4_escalated_case_is_alerted() -> None:
    assert alerted_case_ids(E4_DELTA) == (PB_E4,)
    assert alerts_for(E4_DELTA, E4_METRICS) == (E4_CASE,)


@pytest.mark.parametrize(
    ("snapshot_id", "case", "events"),
    [
        pytest.param(
            "S021", case_with(PB_E4, ESCALATED, CRITICAL, CRITICAL, at="S021"), (), id="S021-no-events"
        ),
        pytest.param(
            "S022",
            case_with(PB_E4, ESCALATED, HIGH, CRITICAL, at="S022"),
            (CaseEvent.SEVERITY_CHANGED,),
            id="S022-severity-changed",
        ),
    ],
)
def test_e5_no_second_alert_after_escalation(
    snapshot_id: str, case: Case, events: tuple[CaseEvent, ...]
) -> None:
    delta = CaseDelta(snapshot_id, tuple(TrackedEvent(PB_E4, e) for e in events), (case,))
    assert alerted_case_ids(delta) == ()
    assert alerts_for(delta, E4_METRICS) == ()


def test_e6_case_opening_critical_is_alerted() -> None:
    case = case_with("S010-Pickup-Brasil", ESCALATED, CRITICAL, CRITICAL)
    delta = CaseDelta(
        "S010",
        (TrackedEvent(case.case_id, CaseEvent.OPENED), TrackedEvent(case.case_id, CaseEvent.ESCALATED)),
        (case,),
    )
    metrics = {PICKUP_BRAZIL: measured(PICKUP_BRAZIL, -11.0, -36.7, 0.0, None, CRITICAL, NONE)}
    assert alerts_for(delta, metrics) == (case,)


def test_e7_alerts_come_only_from_the_last_delta(registry: SqliteRegistry, tracker: CaseTracker) -> None:
    with registry.processing(commit("S009")):
        tracker.track("S009", pb_metrics(metrics_with(HIGH)), NO_RAISES)
    m = pb_metrics(measured(PICKUP_BRAZIL, -7.0, -23.3, 0.0, Stage.ASSEMBLY, HIGH, NONE))
    with registry.processing(commit("S010")):
        d1 = tracker.track("S010", m, NO_RAISES)
        d2 = tracker.track("S010", m, frozenset({PICKUP_BRAZIL}))
    assert alerts_for(d1, m) == ()
    (alerted,) = alerts_for(d2, m)
    assert (alerted.case_id, alerted.state, alerted.current_severity) == (
        "S009-Pickup-Brasil",
        ESCALATED,
        CRITICAL,
    )


def test_e8_alerted_case_without_metrics_raises_naming_it() -> None:
    with pytest.raises(ValueError, match=PB_E4):
        alerts_for(E4_DELTA, {})


def test_importing_novelty_loads_no_sqlite_tracker_or_registry(tmp_path: Path) -> None:
    """Fresh interpreter, so modules imported by other tests do not pollute 'sys.modules'."""
    watched = ["sqlite3", "plant_monitor.cases.tracker", "plant_monitor.cases.registry"]
    probe = (
        "import json, sys\n"
        "import plant_monitor.cases.novelty\n"
        f"print(json.dumps(sorted(m for m in {watched!r} if m in sys.modules)))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False, cwd=tmp_path
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


# --- T4 · Novelty reasons (E9-E17) ---


def test_e9_new_and_resolved_at_mid_are_news_in_case_order() -> None:
    suv_local = case_with("S011-SUV-Local", OPEN, HIGH, HIGH, at="S012")
    pickup_brazil = case_with(
        "S007-Pickup-Brasil",
        RESOLVED,
        NONE,
        NONE,
        at="S011",
        reported=(FOLLOW_UP, NONE, "S010"),
        clean_streak=2,
    )
    assert expected_news([pickup_brazil, suv_local]) == (
        NewsItem(suv_local, (NewsReason.NEW,)),
        NewsItem(pickup_brazil, (NewsReason.RESOLVED,)),
    )


def test_e10_unchanged_case_is_not_news() -> None:
    case = case_with(
        "S005-Pickup-Brasil", FOLLOW_UP, HIGH, HIGH, at="S012", reported=(FOLLOW_UP, HIGH, "S010")
    )
    assert news_reasons(case) == ()
    assert expected_news([case]) == ()


def test_e11_abierto_and_en_seguimiento_are_the_same_state() -> None:
    reported = (OPEN, MEDIUM, "S010")
    same = case_with("S010-Pickup-Brasil", FOLLOW_UP, MEDIUM, MEDIUM, at="S012", reported=reported)
    escalated = case_with("S010-Pickup-Brasil", ESCALATED, CRITICAL, CRITICAL, at="S012", reported=reported)
    assert news_reasons(same) == ()
    assert news_reasons(escalated) == (NewsReason.STATE_CHANGED, NewsReason.SEVERITY_CHANGED)


def test_e12_peak_above_the_closing_severity_is_news() -> None:
    case = case_with(
        "S010-Pickup-Brasil", FOLLOW_UP, MEDIUM, HIGH, at="S012", reported=(FOLLOW_UP, MEDIUM, "S010")
    )
    assert news_reasons(case) == (NewsReason.PEAK,)


def test_e13_drop_to_ninguna_is_a_severity_change() -> None:
    case = case_with(
        "S010-Pickup-Brasil",
        FOLLOW_UP,
        NONE,
        MEDIUM,
        at="S012",
        reported=(FOLLOW_UP, MEDIUM, "S010"),
        clean_streak=1,
    )
    assert news_reasons(case) == (NewsReason.SEVERITY_CHANGED, NewsReason.PEAK)


def test_e14_reported_peak_is_not_repeated_after_marking() -> None:
    case = case_with(
        "S010-Pickup-Brasil", FOLLOW_UP, MEDIUM, MEDIUM, at="S014", reported=(FOLLOW_UP, MEDIUM, "S012")
    )
    assert news_reasons(case) == ()
    assert expected_news([case]) == ()


def test_e15_case_reported_as_resolved_is_never_news() -> None:
    case = case_with(
        "S007-Pickup-Brasil",
        RESOLVED,
        NONE,
        None,
        at="S011",
        reported=(RESOLVED, NONE, "S012"),
        clean_streak=2,
    )
    assert news_reasons(case) == ()
    assert expected_news([case]) == ()


def test_e16_new_case_with_a_peak() -> None:
    case = case_with("S011-Pickup-Local", FOLLOW_UP, MEDIUM, HIGH, at="S012")
    assert news_reasons(case) == (NewsReason.NEW, NewsReason.PEAK)


def test_e17_dip_reverted_by_the_close_is_news_only_at_mid() -> None:
    reported = (FOLLOW_UP, MEDIUM, "S010")
    at_mid = case_with(
        "S010-Pickup-Brasil", FOLLOW_UP, NONE, NONE, at="S011", reported=reported, clean_streak=1
    )
    at_close = case_with("S010-Pickup-Brasil", FOLLOW_UP, MEDIUM, MEDIUM, at="S012", reported=reported)
    assert news_reasons(at_mid) == (NewsReason.SEVERITY_CHANGED,)
    assert news_reasons(at_close) == ()
    assert expected_news([at_close]) == ()


# --- T4 · Report set (E46) ---

E46_SEDAN = case_with("S010-Sedán-Local", FOLLOW_UP, MEDIUM, MEDIUM, at="S010")
E46_PB_EVALUATED = case_with(
    "S007-Pickup-Brasil", RESOLVED, NONE, NONE, at="S010", reported=(FOLLOW_UP, NONE, "S008"), clean_streak=2
)
E46_PB_AS_READ = case_with(
    "S007-Pickup-Brasil", RESOLVED, NONE, NONE, at="S010", reported=(FOLLOW_UP, NONE, "S008"), clean_streak=2
)
E46_SUV = case_with(
    "S004-SUV-Local", RESOLVED, NONE, NONE, at="S009", reported=(FOLLOW_UP, NONE, "S008"), clean_streak=2
)


def test_e46_report_set_dedupes_with_the_evaluated_version_in_case_order() -> None:
    result = report_set([E46_SEDAN, E46_PB_EVALUATED], [E46_PB_AS_READ, E46_SUV])
    assert [c.case_id for c in result] == ["S010-Sedán-Local", "S004-SUV-Local", "S007-Pickup-Brasil"]
    assert result[2] is E46_PB_EVALUATED


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(case_with("S004-SUV-Local", FOLLOW_UP, MEDIUM, MEDIUM, at="S010"), id="active"),
        pytest.param(
            case_with(
                "S004-SUV-Local",
                RESOLVED,
                NONE,
                None,
                at="S009",
                reported=(RESOLVED, NONE, "S010"),
                clean_streak=2,
            ),
            id="reported-as-resuelto",
        ),
    ],
)
def test_e46_report_set_rejects_an_invalid_resolved_unreported_case(bad: Case) -> None:
    with pytest.raises(ValueError, match="S004-SUV-Local"):
        report_set([E46_SEDAN], [bad])


# --- T5 · Active rows (E18) ---

E18_SEDAN = case_with("S001-Sedán-Local", ESCALATED, CRITICAL, CRITICAL, at="S004")
E18_PICKUP = case_with("S001-Pickup-Local", FOLLOW_UP, MEDIUM, HIGH, at="S004")
E18_METRICS = {
    E18_SEDAN.combination: measured(E18_SEDAN.combination, -24.0, -66.67, 0.0, None, CRITICAL, NONE),
    E18_PICKUP.combination: measured(E18_PICKUP.combination, -4.0, -13.33, 0.0, Stage.ASSEMBLY, MEDIUM, NONE),
}


def test_e18_every_active_case_is_listed_in_case_order() -> None:
    assert active_rows([E18_PICKUP, E18_SEDAN], E18_METRICS) == (
        ActiveCaseRow(
            case_id="S001-Sedán-Local",
            modelo=Model.SEDAN,
            mercado=Market.LOCAL,
            gap_unidades=-24.0,
            gap_pct=-66.67,
            retraso_dias=0.0,
            severidad=CRITICAL,
            severidad_maxima=CRITICAL,
            estado=ESCALATED,
            etapa_cuello=None,
        ),
        ActiveCaseRow(
            case_id="S001-Pickup-Local",
            modelo=Model.PICKUP,
            mercado=Market.LOCAL,
            gap_unidades=-4.0,
            gap_pct=-13.33,
            retraso_dias=0.0,
            severidad=MEDIUM,
            severidad_maxima=HIGH,
            estado=FOLLOW_UP,
            etapa_cuello=Stage.ASSEMBLY,
        ),
    )


@pytest.mark.parametrize(
    ("case", "metrics"),
    [
        pytest.param(
            case_with(
                "S001-Pickup-Local",
                RESOLVED,
                NONE,
                NONE,
                at="S004",
                reported=(FOLLOW_UP, NONE, "S002"),
                clean_streak=2,
            ),
            E18_METRICS,
            id="a-resolved",
        ),
        pytest.param(
            E18_PICKUP, {E18_SEDAN.combination: E18_METRICS[E18_SEDAN.combination]}, id="b-missing-metrics"
        ),
        pytest.param(
            case_with(
                "S001-Pickup-Local", FOLLOW_UP, MEDIUM, None, at="S004", reported=(FOLLOW_UP, MEDIUM, "S004")
            ),
            E18_METRICS,
            id="c-empty-max",
        ),
    ],
)
def test_e18_active_rows_rejects_an_invalid_case_naming_it(
    case: Case, metrics: dict[Combination, CombinationMetrics]
) -> None:
    with pytest.raises(ValueError, match="S001-Pickup-Local"):
        active_rows([case], metrics)
