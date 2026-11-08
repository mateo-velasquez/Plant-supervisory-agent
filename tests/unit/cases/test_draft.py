"""007 T9: 'NoticeDraft' required texts (E1) and the rebuilt notices (E14, R1, R10)."""

import pytest
from draft_builders import (
    MAX_CHARS,
    SUV_SILENT_TEXT,
    agent_text,
    empty_close_notices,
    s001_notices,
    s003_notices,
    s004_notices,
    s010_notices,
)

from plant_monitor.cases.draft import NoticeDraft
from plant_monitor.cases.notice_builder import SnapshotNotices

from notice_builders import PICKUP_BRAZIL_CASE, PICKUP_LOCAL_CASE, SEDAN_LOCAL_CASE, SUV_LOCAL_CASE

NEWS_CASES = (SEDAN_LOCAL_CASE, PICKUP_LOCAL_CASE, PICKUP_BRAZIL_CASE)


@pytest.mark.parametrize(
    ("notices", "expected"),
    [
        pytest.param(s001_notices(), (), id="a-e41-s001"),
        pytest.param(empty_close_notices(), (), id="b-e39-empty-report"),
        pytest.param(s003_notices(), ("S003-alerta_inmediata-S001-Sedán-Local",), id="c-e37-alert"),
        pytest.param(
            s010_notices(),
            (
                "S010-alerta_inmediata-S008-Sedán-Local",
                "S010-informe_de_turno-S008-Sedán-Local",
                "S010-informe_de_turno-S007-Pickup-Brasil",
            ),
            id="d-e38-alert-and-news",
        ),
    ],
)
def test_e1_required_texts_are_the_alerts_then_the_report_news(
    notices: SnapshotNotices, expected: tuple[str, ...]
) -> None:
    """E1: with no required text the model is not called."""
    draft = NoticeDraft(notices, MAX_CHARS)
    assert draft.required() == expected
    assert draft.missing() == expected


def test_e14a_build_with_nothing_written_equals_the_input() -> None:
    """E14a: no write, no change."""
    notices = s004_notices()
    assert NoticeDraft(notices, MAX_CHARS).build() == notices


def test_e14b_written_news_reach_the_decisions_and_the_report_and_nothing_else_changes() -> None:
    """E14b: the same agent text in the decision and in 'novedades'; the rest is untouched."""
    notices = s004_notices()
    draft = NoticeDraft(notices, MAX_CHARS)
    ids = tuple(f"S004-informe_de_turno-{case}" for case in NEWS_CASES)
    draft.write_news([(case, agent_text(i)) for case, i in zip(NEWS_CASES, ids, strict=True)])
    built = draft.build()
    texts = {n.notice_id: n.texto for n in built.decisions}
    assert [texts[i] for i in ids] == [agent_text(i) for i in ids]
    silent = f"S004-sin_aviso-{SUV_LOCAL_CASE}"
    assert texts[silent] == SUV_SILENT_TEXT
    assert built.report is not None and notices.report is not None
    assert [n.texto for n in built.report.novedades] == [agent_text(i) for i in ids]
    assert built.report.casos_activos == notices.report.casos_activos
    assert (built.report.turno_id, built.report.snapshot_id) == ("T02", "S004")
    assert built.to_mark == notices.to_mark
    for before, after in zip(notices.decisions, built.decisions, strict=True):
        assert before.model_dump(exclude={"texto"}) == after.model_dump(exclude={"texto"})


def test_written_alert_text_reaches_the_built_decision() -> None:
    """Risk: an alert text written through 'write_alert' is lost when the notices are rebuilt."""
    draft = NoticeDraft(s003_notices(), MAX_CHARS)
    alert_id = "S003-alerta_inmediata-S001-Sedán-Local"
    draft.write_alert(SEDAN_LOCAL_CASE, f"  {agent_text(alert_id)}  ")
    built = draft.build()
    assert built.decisions[0].texto == agent_text(alert_id)
    assert draft.written() == (alert_id,)
    assert draft.missing() == ()
