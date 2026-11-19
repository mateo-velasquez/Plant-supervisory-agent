"""Pure HTML pages of reports and alerts, escape by default, and the held-out filter (spec 014)."""

import html
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from string import Template
from typing import Final
from urllib.parse import quote

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.cases import case_snapshot_id
from plant_monitor.domain.causes import Evidence
from plant_monitor.domain.enums import Market, Model, Severity
from plant_monitor.domain.notices import (
    ActiveCaseRow,
    Notice,
    NoticeType,
    ShiftReport,
    report_id_for,
)
from plant_monitor.domain.numbers import DECIMALS, round_display
from plant_monitor.domain.text import escape_controls

EMPTY: Final = "—"
INDEX_NAME: Final = "index.html"

SNAPSHOT_ID: Final = r"S[0-9]{3}"
SHIFT_ID: Final = r"T[0-9]{2}"
CASE_ID: Final = (
    rf"{SNAPSHOT_ID}-(?:{'|'.join(re.escape(m.value) for m in Model)})"
    rf"-(?:{'|'.join(re.escape(m.value) for m in Market)})"
)
NOTICE_ID: Final = (
    rf"{SNAPSHOT_ID}-(?:{re.escape(NoticeType.ALERT.value)}|{re.escape(NoticeType.SHIFT_REPORT.value)})"
    rf"-{CASE_ID}"
)
_SNAPSHOT_RE: Final = re.compile(SNAPSHOT_ID)
_SHIFT_RE: Final = re.compile(SHIFT_ID)
_CASE_RE: Final = re.compile(CASE_ID)
_NOTICE_RE: Final = re.compile(NOTICE_ID)


class Markup(str):
    """Already-escaped HTML; created only by '_fill', '_join' and the template constants."""


class UnsafeId(ValueError):
    """An id outside its allowed pattern; the message names the field and the escaped value."""


@dataclass(frozen=True)
class Page:
    """One rendered file: its name and its UTF-8 bytes."""

    name: str
    data: bytes


@dataclass(frozen=True)
class _ShownIds:
    snapshots: frozenset[str]
    shifts: frozenset[str]


type Deliverable = Notice | ShiftReport


def escape_text(value: str) -> str:
    """'value' with control characters made visible, then HTML-escaped."""
    return html.escape(escape_controls(value), quote=True)


def _fill(template: Template, **values: str) -> Markup:
    """Fill 'template': 'Markup' values as is, every other 'str' escaped."""
    safe = {k: v if isinstance(v, Markup) else escape_text(v) for k, v in values.items()}
    return Markup(template.substitute(safe))


def _join(parts: Iterable[Markup]) -> Markup:
    """The 'parts' separated by line breaks."""
    return Markup("\n".join(parts))


def _template(*lines: str) -> Template:
    return Template("\n".join(lines))


CSS: Final = Markup(
    "\n".join(
        [
            "body{font-family:system-ui,sans-serif;margin:2rem;max-width:72rem;color:#1a1a1a}",
            "table{border-collapse:collapse}",
            "th,td{border:1px solid #999;padding:.25rem .5rem;text-align:left}",
            ".sev{padding:0 .4rem;border:1px solid #555;border-radius:.2rem;font-weight:bold}",
            ".sev-ninguna{background:#e9ecef}",
            ".sev-media{background:#fff3bf}",
            ".sev-alta{background:#ffc078}",
            ".sev-critica{background:#c92a2a;color:#fff}",
            ".peak{outline:2px solid #c92a2a}",
            ".notice{border-top:1px solid #ccc;padding:.5rem 0}",
            ".empty{font-style:italic}",
            "blockquote{margin:.25rem 0;padding-left:.75rem;border-left:3px solid #999}",
            "figure{margin:.25rem 1rem}",
            "code{background:#f1f3f5;padding:0 .2rem}",
        ]
    )
)

_PAGE: Final = Template(
    "\n".join(
        [
            "<!DOCTYPE html>",
            '<html lang="es">',
            "<head>",
            '<meta charset="utf-8">',
            '<meta http-equiv="Content-Security-Policy" '
            "content=\"default-src 'none'; style-src 'unsafe-inline'\">",
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            "<title>$title</title>",
            "<style>",
            "$css",
            "</style>",
            "</head>",
            "<body>",
            "$body",
            "</body>",
            "</html>",
            "",
        ]
    )
)

_REPORT: Final = _template(
    '<nav><a href="index.html">Índice</a></nav>',
    "<h1>$title</h1>",
    "<p>Snapshot de cierre: $snapshot_id</p>",
    "<h2>Novedades</h2>",
    "$news",
    "<h2>Casos activos</h2>",
    "$active",
)
_NO_NEWS: Final = Markup('<p class="empty">Sin novedades en este turno</p>')
_NO_ACTIVE: Final = Markup('<p class="empty">Sin casos activos</p>')

_NOTICE: Final = _template(
    '<article class="notice">',
    "<h3>$case_id</h3>",
    "<p>Severidad $severity · Máxima $maximum · Estado $estado</p>",
    "<p>Motivo: $motivo · Origen: $origen</p>",
    '<p class="text">$texto</p>',
    "<p>Causa: $categoria · Etapa: $etapa</p>",
    "$evidence",
    "<p>Traza: <code>plant-monitor trace $notice_id</code></p>",
    "</article>",
)
_NO_EVIDENCE: Final = Markup("<p>Evidencia: —</p>")
_EVIDENCE_HEAD: Final = Markup("<p>Evidencia:</p>")
_QUOTE: Final = Template(
    "<figure><blockquote>$fragmento</blockquote><figcaption>Bitácora $bitacora</figcaption></figure>"
)

_ALERT: Final = _template(
    '<nav><a href="index.html">Índice</a></nav>',
    "<h1>$title</h1>",
    "<p>Snapshot: $snapshot_id</p>",
    "$notice",
)

_INDEX_TITLE: Final = "Informes y alertas"
_INDEX: Final = _template(
    "<h1>$title</h1>",
    "$entries",
)
_LIST_OPEN: Final = Markup('<ol class="timeline">')
_LIST_CLOSE: Final = Markup("</ol>")
_NO_ENTRIES: Final = Markup('<p class="empty">Sin informes ni alertas</p>')
_ALERT_ENTRY: Final = Template(
    '<li><a href="$href">$snapshot_id · Alerta inmediata · $case_id</a> $badge</li>'
)
_REPORT_ENTRY: Final = Template(
    '<li><a href="$href">$snapshot_id · Informe de turno $turno_id</a>'
    " · Novedades: $news · Casos activos: $active</li>"
)

_BADGE: Final = Template('<span class="sev sev-$value">$value</span>')
_PEAK_BADGE: Final = Template('<span class="sev sev-$value peak">$value</span> <strong>pico</strong>')

_TABLE: Final = _template(
    "<table>",
    "<thead><tr><th>Caso</th><th>Modelo</th><th>Mercado</th><th>Gap (u)</th><th>Gap (%)</th>"
    "<th>Retraso (días)</th><th>Severidad</th><th>Máxima</th><th>Estado</th>"
    "<th>Etapa cuello</th></tr></thead>",
    "<tbody>",
    "$rows",
    "</tbody>",
    "</table>",
)
_ROW: Final = Template(
    "<tr><td>$case_id</td><td>$modelo</td><td>$mercado</td><td>$gap_unidades</td><td>$gap_pct</td>"
    "<td>$retraso_dias</td><td>$severity</td><td>$maximum</td><td>$estado</td><td>$etapa_cuello</td></tr>"
)


def format_plain(value: float | None) -> str:
    """Integral floats as integers, others in their shortest 'repr', None as a dash."""
    if value is None:
        return EMPTY
    return str(int(value)) if value.is_integer() else repr(value)


def format_pct(value: float | None) -> str:
    """One-decimal percentage, never '-0.0%', None as a dash."""
    if value is None:
        return EMPTY
    return f"{round_display(value) + 0.0:.{DECIMALS}f}%"


def _badge(severity: Severity, *, peak: bool = False) -> Markup:
    """The severity badge, with the 'pico' marker when 'peak'."""
    return _fill(_PEAK_BADGE if peak else _BADGE, value=severity)


def _evidence(items: Sequence[Evidence]) -> Markup:
    """The evidence block of a notice, or a dash when there is none."""
    if not items:
        return _NO_EVIDENCE
    quotes = (_fill(_QUOTE, fragmento=e.fragmento, bitacora=e.bitacora) for e in items)
    return _join([_EVIDENCE_HEAD, *quotes])


def _notice(notice: Notice) -> Markup:
    """The notice block (R5)."""
    peak = notice.severidad_maxima > notice.severidad
    return _fill(
        _NOTICE,
        case_id=notice.case_id,
        severity=_badge(notice.severidad),
        maximum=_badge(notice.severidad_maxima, peak=peak),
        estado=notice.estado,
        motivo=", ".join(notice.motivo) or EMPTY,
        origen=notice.origen,
        texto=notice.texto,
        categoria=notice.causa.categoria,
        etapa=notice.causa.etapa or EMPTY,
        evidence=_evidence(notice.evidencia),
        notice_id=notice.notice_id,
    )


def _row(row: ActiveCaseRow) -> Markup:
    """One table row of the active cases."""
    return _fill(
        _ROW,
        case_id=row.case_id,
        modelo=row.modelo,
        mercado=row.mercado,
        gap_unidades=format_plain(row.gap_unidades),
        gap_pct=format_pct(row.gap_pct),
        retraso_dias=format_plain(row.retraso_dias),
        severity=_badge(row.severidad),
        maximum=_badge(row.severidad_maxima, peak=row.severidad_maxima > row.severidad),
        estado=row.estado,
        etapa_cuello=row.etapa_cuello or EMPTY,
    )


def _page(title: str, body: Markup) -> str:
    """The full page around 'body'."""
    return _fill(_PAGE, title=title, css=CSS, body=body)


def _check(field: str, value: str, pattern: re.Pattern[str]) -> None:
    """Raise 'UnsafeId' unless 'value' fully matches 'pattern'."""
    if pattern.fullmatch(value) is None:
        raise UnsafeId(f"html: invalid {field}: {escape_controls(value)}")


def _validate_notice(notice: Notice) -> None:
    """The id checks of one notice: snapshot, case, notice id, then each evidence logbook."""
    _check("snapshot_id", notice.snapshot_id, _SNAPSHOT_RE)
    _check("case_id", notice.case_id, _CASE_RE)
    _check("notice_id", notice.notice_id, _NOTICE_RE)
    for item in notice.evidencia:
        _check("bitacora", item.bitacora, _SHIFT_RE)


def validate_ids(item: Deliverable) -> None:
    """Raise 'UnsafeId' for the first id outside its pattern (R10 order)."""
    if isinstance(item, ShiftReport):
        _check("turno_id", item.turno_id, _SHIFT_RE)
        _check("snapshot_id", item.snapshot_id, _SNAPSHOT_RE)
        for news in item.novedades:
            _validate_notice(news)
        for row in item.casos_activos:
            _check("case_id", row.case_id, _CASE_RE)
        return
    if item.tipo is not NoticeType.ALERT:
        raise UnsafeId(f"html: invalid tipo: {escape_controls(item.tipo)}")
    _validate_notice(item)


def page_name(item: Deliverable) -> str:
    """The file name of the page of 'item'; call after 'validate_ids'."""
    if isinstance(item, ShiftReport):
        return f"{report_id_for(item.turno_id)}.html"
    return f"{item.notice_id}.html"


def _href(name: str) -> str:
    """The URL-quoted link target of a page name."""
    return quote(name, safe="")


def _shown_ids(item: Deliverable) -> _ShownIds:
    """The snapshot and shift ids 'item' would show (R12); never raises."""
    if isinstance(item, ShiftReport):
        snapshots = {item.snapshot_id}
        shifts = {item.turno_id}
        for news in item.novedades:
            snapshots |= {news.snapshot_id, case_snapshot_id(news.case_id)}
            shifts |= {e.bitacora for e in news.evidencia}
        snapshots |= {case_snapshot_id(row.case_id) for row in item.casos_activos}
        return _ShownIds(frozenset(snapshots), frozenset(shifts))
    return _ShownIds(
        frozenset({item.snapshot_id, case_snapshot_id(item.case_id)}),
        frozenset(e.bitacora for e in item.evidencia),
    )


def _is_unverifiable(item: Deliverable) -> bool:
    """Whether 'validate_ids' rejects 'item'."""
    try:
        validate_ids(item)
    except UnsafeId:
        return True
    return False


def select_shown(items: Sequence[Deliverable], policy: HeldOutPolicy) -> tuple[tuple[Deliverable, ...], int]:
    """The items to show, in order, and how many were omitted (held out or unverifiable)."""
    kept: list[Deliverable] = []
    for item in items:
        shown = _shown_ids(item)
        refused = bool(shown.snapshots & policy.refused_snapshots) or bool(
            shown.shifts & policy.refused_shifts
        )
        if refused or (not policy.is_open and _is_unverifiable(item)):
            continue
        kept.append(item)
    return tuple(kept), len(items) - len(kept)


def render_report(report: ShiftReport) -> str:
    """The HTML page of a shift report."""
    validate_ids(report)
    title = f"Informe de turno {report.turno_id}"
    news = _join(_notice(n) for n in report.novedades) if report.novedades else _NO_NEWS
    active = (
        _fill(_TABLE, rows=_join(_row(r) for r in report.casos_activos))
        if report.casos_activos
        else _NO_ACTIVE
    )
    body = _fill(_REPORT, title=title, snapshot_id=report.snapshot_id, news=news, active=active)
    return _page(title, body)


def render_alert(notice: Notice) -> str:
    """The HTML page of an immediate alert."""
    validate_ids(notice)
    title = f"Alerta inmediata · {notice.case_id}"
    body = _fill(
        _ALERT,
        title=title,
        snapshot_id=notice.snapshot_id,
        notice=_notice(notice),
    )
    return _page(title, body)


def _entry(item: Deliverable) -> Markup:
    """The index line of one page."""
    href = _href(page_name(item))
    if isinstance(item, ShiftReport):
        return _fill(
            _REPORT_ENTRY,
            href=href,
            snapshot_id=item.snapshot_id,
            turno_id=item.turno_id,
            news=str(len(item.novedades)),
            active=str(len(item.casos_activos)),
        )
    return _fill(
        _ALERT_ENTRY,
        href=href,
        snapshot_id=item.snapshot_id,
        case_id=item.case_id,
        badge=_badge(item.severidad),
    )


def render_index(items: Sequence[Deliverable]) -> str:
    """The index page linking every item, in the given order."""
    for item in items:
        validate_ids(item)
    entries = _join([_LIST_OPEN, *(_entry(i) for i in items), _LIST_CLOSE]) if items else _NO_ENTRIES
    return _page(_INDEX_TITLE, _fill(_INDEX, title=_INDEX_TITLE, entries=entries))


def render_site(items: Sequence[Deliverable]) -> tuple[Page, ...]:
    """Every page, UTF-8 encoded, index last; raises before returning anything on a bad item."""
    for item in items:
        validate_ids(item)
    names = [page_name(item) for item in items]
    counts = Counter(names)
    for name in names:
        if counts[name] > 1:
            raise ValueError(f"html: duplicate page {name}")
    texts = [render_report(item) if isinstance(item, ShiftReport) else render_alert(item) for item in items]
    texts.append(render_index(items))
    pages: list[Page] = []
    for name, text in zip([*names, INDEX_NAME], texts, strict=True):
        try:
            pages.append(Page(name=name, data=text.encode("utf-8")))
        except UnicodeEncodeError as error:
            raise ValueError(f"html: {name} is not encodable as UTF-8") from error
    return tuple(pages)
