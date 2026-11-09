"""008 T7: 'NoticeDraft.rebase' keeps or drops written texts after a re-decide (E16, R13)."""

import pytest
from draft_builders import MAX_CHARS, agent_text, s010_notices
from incident_runs import AC2, EV_T02, EV_T03, EV_T05, EV_T06, PICKUP_ANY, SUV_EUROPE, incident_run

from plant_monitor.cases.draft import NoticeDraft
from plant_monitor.cases.notice_builder import SnapshotNotices
from plant_monitor.domain.causes import CauseCategory
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import Notice, NoticeType
from plant_monitor.runner.pipeline import SnapshotDecision

from notice_builders import news_notice

PL_CASE = "S010-Pickup-Local"
PB_CASE = "S010-Pickup-Brasil"
PE_CASE = "S011-Pickup-Europa"
SE_CASE = "S005-SUV-Europa"


def alert_id(snapshot_id: str, case_id: str) -> str:
    """Notice id of an alert."""
    return f"{snapshot_id}-alerta_inmediata-{case_id}"


def news_id(snapshot_id: str, case_id: str) -> str:
    """Notice id of a report news item."""
    return f"{snapshot_id}-informe_de_turno-{case_id}"


def write_all_news(draft: NoticeDraft, decision: SnapshotDecision) -> None:
    """Write the agent text of every news item of the decision's report."""
    report = decision.notices.report
    assert report is not None
    draft.write_news([(n.case_id, agent_text(n.notice_id)) for n in report.novedades])


def _with_news(notices: SnapshotNotices, news: tuple[Notice, ...]) -> SnapshotNotices:
    """The notices with 'news' swapped into the decisions (by notice id) and the report's novedades."""
    by_case = {n.case_id: n for n in news}
    decisions = tuple(
        n if n.tipo is NoticeType.ALERT else by_case.get(n.case_id, n) for n in notices.decisions
    )
    assert notices.report is not None
    report = notices.report.model_copy(update={"novedades": news})
    return SnapshotNotices(decisions, report, notices.to_mark)


def _louder(notice: Notice) -> Notice:
    """The same news with a different 'severidad_maxima'."""
    data = {**notice.model_dump(), "severidad_maxima": Severity.CRITICAL}
    return Notice.model_validate(data)


@pytest.mark.parametrize("variant", ["one_item_changes", "item_added"])
def test_e16d_report_texts_survive_a_rebase_only_as_a_unit(variant: str) -> None:
    first = s010_notices()
    assert first.report is not None
    sel, pb = first.report.novedades
    alert = alert_id("S010", sel.case_id)
    news: tuple[Notice, ...]
    if variant == "one_item_changes":
        news = (_louder(sel), pb)
    else:
        news = (sel, news_notice("S010", "S008-SUV-Local"), pb)
    second = _with_news(first, news)
    draft = NoticeDraft(first, MAX_CHARS)
    draft.write_alert(sel.case_id, agent_text(alert))
    draft.write_news([(n.case_id, agent_text(n.notice_id)) for n in (sel, pb)])

    draft.rebase(second)

    news_ids = tuple(n.notice_id for n in news)
    assert draft.written() == (alert,)
    assert draft.missing() == news_ids
    texts = [(n.case_id, agent_text(n.notice_id)) for n in news]
    assert draft.write_news(texts) == news_ids
    assert draft.missing() == ()


def test_e16a_a_new_alert_makes_the_written_news_pending_again() -> None:
    with incident_run() as run:
        run.through(9)

        def act(first: SnapshotDecision) -> SnapshotDecision:
            draft = NoticeDraft(first.notices, MAX_CHARS)
            write_all_news(draft, first)
            assert draft.missing() == ()
            second = run.raise_cause(first, CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05)
            pending = draft.rebase(second.notices)

            expected = (
                alert_id("S010", PL_CASE),
                alert_id("S010", PB_CASE),
                news_id("S010", PL_CASE),
                news_id("S010", PB_CASE),
            )
            assert draft.written() == ()
            assert draft.required() == expected
            assert draft.missing() == expected
            assert {n.notice_id for n in pending} == set(expected)
            assert draft.build() == second.notices
            return second

        run.step(10, act)


def test_e16b_a_written_news_text_survives_a_lift_that_leaves_its_item_unchanged() -> None:
    with incident_run() as run:
        run.through(9)
        run.step(10, lambda d: run.raise_cause(d, CauseCategory.LINE_STOP, PICKUP_ANY, EV_T05))
        run.step(11)

        def act(first: SnapshotDecision) -> SnapshotDecision:
            draft = NoticeDraft(first.notices, MAX_CHARS)
            write_all_news(draft, first)
            written = draft.written()
            assert news_id("S012", PE_CASE) in written
            second = run.lift_cause(first, AC2, EV_T06)
            draft.rebase(second.notices)

            assert draft.written() == written
            assert draft.missing() == ()
            report = draft.build().report
            assert report is not None
            assert agent_text(news_id("S012", PE_CASE)) in {n.texto for n in report.novedades}
            return second

        run.step(12, act)


def test_e16c_a_lift_that_removes_an_alert_takes_its_written_text_with_it() -> None:
    with incident_run() as run:
        run.through(5)

        def act(first: SnapshotDecision) -> SnapshotDecision:
            raised = run.raise_cause(first, CauseCategory.QUALITY_HOLD, SUV_EUROPE, EV_T02)
            draft = NoticeDraft(raised.notices, MAX_CHARS)
            alert = alert_id("S006", SE_CASE)
            assert alert in draft.required()
            draft.write_alert(SE_CASE, agent_text(alert))
            lifted = run.lift_cause(raised, "S006-causa-1", EV_T03)
            draft.rebase(lifted.notices)

            assert alert not in draft.required()
            assert alert not in draft.written()
            assert all(n.tipo is not NoticeType.ALERT for n in draft.build().decisions)
            return lifted

        run.step(6, act)
