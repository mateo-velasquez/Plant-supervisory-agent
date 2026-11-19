"""Spec 014: HTML rendering (formatting, golden pages, ids, escaping, held-out filter)."""

import re
from collections.abc import Sequence

import pytest
from html_builders import A1, E6_ALERT, EMPTY_T06, N_PB, REPORT_T05, ROW_SE, golden, variant

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import CaseState
from plant_monitor.domain.causes import Evidence
from plant_monitor.domain.enums import Severity
from plant_monitor.domain.notices import (
    Notice,
    ShiftReport,
    notice_id_for,
)
from plant_monitor.notify.html import (
    UnsafeId,
    format_pct,
    format_plain,
    render_alert,
    render_report,
    render_site,
    select_shown,
)

from notice_builders import alert_notice, news_notice, plant_shifts, shift_report

A1_NAME = "S009-alerta_inmediata-S001-Sedán-Local.html"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-4.0, "-4"), (-2.5, "-2.5"), (-0.0, "0"), (12.0, "12"), (None, "—")],
)
def test_e1_format_plain(value: float | None, expected: str) -> None:
    """014 E1: plain numbers drop an integral '.0' and keep the JSON form otherwise."""
    assert format_plain(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(23.61111, "23.6%"), (-13.33333, "-13.3%"), (-0.04, "0.0%"), (None, "—")],
)
def test_e1_format_pct(value: float | None, expected: str) -> None:
    """014 E1: percentages show one decimal, never '-0.0%'."""
    assert format_pct(value) == expected


def test_e2_report_page_equals_the_golden_file() -> None:
    """014 E2: the T05 report page is byte-exact with the hand-written golden."""
    assert render_report(REPORT_T05) == golden("report_T05.html")


def test_e3_silence_is_visible_in_the_report() -> None:
    """014 E3: an empty news list and an empty active table say so."""
    only_row = render_report(
        ShiftReport(turno_id="T04", snapshot_id="S008", novedades=(), casos_activos=(ROW_SE,))
    )
    news = '<p class="empty">Sin novedades en este turno</p>'
    assert news in only_row
    assert only_row.index(news) < only_row.index("<h2>Casos activos</h2>")
    assert only_row.count("<tr><td>S005-SUV-Europa</td>") == 1

    empty = render_report(EMPTY_T06)
    assert "Sin novedades en este turno" in empty
    assert '<p class="empty">Sin casos activos</p>' in empty
    assert "<table>" not in empty


def test_r5_resolved_news_shows_empty_motivo_and_ninguna() -> None:
    """014 R5 (criterio 4, resolved in the shift): empty 'motivo' shows '—' and severity 'ninguna'."""
    resolved = variant(
        N_PB,
        estado=CaseState.RESOLVED,
        severidad=Severity.NONE,
        severidad_maxima=Severity.NONE,
        motivo=(),
    )
    page = render_report(
        ShiftReport(turno_id="T05", snapshot_id="S010", novedades=(resolved,), casos_activos=())
    )
    assert "<p>Motivo: — · Origen: umbral</p>" in page
    assert '<span class="sev sev-ninguna">ninguna</span>' in page
    assert "Estado resuelto</p>" in page


def test_e4_alert_page_structure() -> None:
    """014 E4: the alert page shows title, back link, snapshot, badges, cause and trace command."""
    page = render_alert(A1)
    assert "<title>Alerta inmediata · S001-Sedán-Local</title>" in page
    assert '<nav><a href="index.html">Índice</a></nav>' in page
    assert "<p>Snapshot: S009</p>" in page
    assert page.count('<span class="sev sev-critica">critica</span>') == 2
    assert " peak" not in page.split("</style>", 1)[1]
    assert "pico" not in page
    assert "<p>Evidencia: —</p>" in page
    assert "<p>Causa: no_declarada · Etapa: montaje</p>" in page
    assert "<code>plant-monitor trace S009-alerta_inmediata-S001-Sedán-Local</code>" in page


def test_e5_site_pages_in_order_with_golden_index() -> None:
    """014 E5: names in order, report page and index equal their golden bytes."""
    pages = render_site((A1, REPORT_T05, EMPTY_T06))
    assert [page.name for page in pages] == [
        A1_NAME,
        "T05-informe.html",
        "T06-informe.html",
        "index.html",
    ]
    assert pages[1].data == golden("report_T05.html").encode("utf-8")
    assert pages[3].data == golden("index.html").encode("utf-8")


def test_e6_a_logbook_cannot_inject_markup() -> None:
    """Risk: 014 E6 a logbook fragment or text could open a tag, close the style or inject control codes."""
    page = render_alert(E6_ALERT)
    assert "<blockquote>&lt;script&gt;alert(1)&lt;/script&gt;&lt;/style&gt;\\x1b[31mrojo</blockquote>" in page
    assert '<p class="text">it&#x27;s x&quot; onmouseover=&quot;y</p>' in page
    assert "<script" not in page
    assert page.count("</style>") == 1
    assert re.search("[\x00-\x09\x0b-\x1f\x7f-\x9f]", page) is None


@pytest.mark.parametrize("forbidden", ["<script", "src=", "http:", "https:", "url(", "@import"])
def test_e7_report_page_has_no_script_and_no_network(forbidden: str) -> None:
    """Risk: 014 E7 a report page could run script or fetch a resource despite the CSP."""
    page = render_report(REPORT_T05)
    assert '<meta charset="utf-8">' in page
    assert (
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'\">"
    ) in page
    assert forbidden not in page


@pytest.mark.parametrize("forbidden", ["<script", "src=", "http:", "https:", "url(", "@import"])
def test_e7_every_site_page_has_no_script_and_no_network(forbidden: str) -> None:
    """Risk: 014 E7 an alert page or the index could run script or fetch a resource despite the CSP."""
    csp = (
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'\">"
    )
    for page in render_site((A1, REPORT_T05, EMPTY_T06)):
        text = page.data.decode("utf-8")
        assert text.count('<meta charset="utf-8">') == 1
        assert text.count(csp) == 1
        assert forbidden not in text


def _with_case_id(notice: Notice, case_id: str) -> Notice:
    """The notice with another 'case_id' and the matching 'notice_id'."""
    return variant(
        notice,
        case_id=case_id,
        notice_id=notice_id_for(notice.snapshot_id, notice.tipo, case_id),
    )


@pytest.mark.parametrize(
    ("items", "message"),
    [
        ((shift_report("../T05", "S010"),), "html: invalid turno_id: ../T05"),
        ((shift_report("T5", "S010"),), "html: invalid turno_id: T5"),
        (
            (_with_case_id(A1, "S001-Sedán-Local/x"),),
            "html: invalid case_id: S001-Sedán-Local/x",
        ),
        (
            (variant(A1, evidencia=(Evidence(bitacora="T05\n", fragmento="x"),)),),
            "html: invalid bitacora: T05\\x0a",
        ),
        (
            (news_notice("S010", "S010-Pickup-Local"),),
            "html: invalid tipo: informe_de_turno",
        ),
    ],
    ids=["a", "b", "c", "d", "f"],
)
def test_e8_unsafe_ids_are_refused(items: Sequence[Notice | ShiftReport], message: str) -> None:
    """014 E8 (a)-(d), (f): an id outside its pattern, or a non-alert notice, raises 'UnsafeId'."""
    with pytest.raises(UnsafeId) as error:
        render_site(items)
    assert str(error.value) == message


def test_e8_e_duplicate_page_name_is_refused() -> None:
    """014 E8 (e): two items with one page name raise 'ValueError', not 'UnsafeId'."""
    with pytest.raises(ValueError, match="html: duplicate page") as error:
        render_site((A1, A1))
    assert not isinstance(error.value, UnsafeId)
    assert str(error.value) == f"html: duplicate page {A1_NAME}"


def test_e15_a_unencodable_text_fails_before_any_page() -> None:
    """014 E15 (a): a lone surrogate raises 'ValueError' naming the page, with no page returned."""
    with pytest.raises(ValueError, match="not encodable") as error:
        render_site((variant(A1, texto="\ud800"),))
    assert str(error.value) == f"html: {A1_NAME} is not encodable as UTF-8"


def _e9_items() -> tuple[Notice | ShiftReport, ...]:
    """The six items of E9, in order."""
    cited = variant(
        news_notice("S004", "S003-Pickup-Local"), evidencia=(Evidence(bitacora="T03", fragmento="x"),)
    )
    return (
        alert_notice("S004", "S003-Pickup-Local"),
        ShiftReport(turno_id="T02", snapshot_id="S004", novedades=(cited,), casos_activos=()),
        shift_report("T02", "S004", active=("S005-Pickup-Brasil",)),
        alert_notice("S005", "S005-SUV-Local"),
        shift_report("T03", "S006"),
        shift_report("../T03", "S004"),
    )


def test_e9_closed_guard_omits_held_out_and_unverifiable_items() -> None:
    """014 E9 (a): items showing a refused shift or snapshot, or an unverifiable id, are omitted."""
    items = _e9_items()
    policy = HeldOutPolicy.from_calendar(plant_shifts(), "T03", False)
    assert select_shown(items, policy) == ((items[0],), 5)


def test_e9_open_guard_keeps_everything_and_ids_fail_at_render() -> None:
    """014 E9 (b): with the guard open nothing is omitted and the bad id errors in 'render_site'."""
    items = _e9_items()
    policy = HeldOutPolicy.from_calendar(plant_shifts(), "T03", True)
    kept, omitted = select_shown(items, policy)
    assert kept == items
    assert omitted == 0
    with pytest.raises(UnsafeId) as error:
        render_site(kept)
    assert str(error.value) == "html: invalid turno_id: ../T03"
