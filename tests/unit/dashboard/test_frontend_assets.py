"""Frontend asset scan for the live dashboard (014 R15, E21)."""

import re
from pathlib import Path

import pytest
import trace_builders

from plant_monitor.config import Settings
from plant_monitor.dashboard.server import ASSETS, FRONTEND_DIR, DashboardApp

thresholds_dir = trace_builders.thresholds_dir

_SRC_FRONTEND = Path(__file__).resolve().parents[3] / "src" / "frontend"
_ALLOWED_SUFFIXES = {".html", ".css", ".js"}
_FILES = sorted(p for p in _SRC_FRONTEND.rglob("*") if p.is_file())
_SINKS = (
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
    "srcdoc",
    'setTimeout("',
    "setTimeout('",
    'setAttribute("on',
    "setAttribute('on",
    "http:",
    "https:",
    "@import",
)
_REMOTE_URL = re.compile(r"url\(\s*['\"]?\s*(?:https?:|//)")
_LINK_SINK = re.compile(r"\.href\s*=(?!=)|window\.open\(")
_ALLOWED_LINK = re.compile(
    r"""(?:\.href\s*=\s*|window\.open\(\s*)(?:"/agentes"|`/agentes#\$\{sid\}`|"/pronostico")\s*(?:[;,)]|$)"""
)
_SVG_NAMESPACE = re.compile(r"""(["'])http://www\.w3\.org/2000/svg\1""")
_SID_CHECK = re.compile(r"\^S\[0-9\]\{3\}\$")


def test_e21_assets_exist_and_frontend_dir_agrees() -> None:
    """E21: every ASSETS file exists in 'src/frontend' and FRONTEND_DIR resolves to it."""
    assert FRONTEND_DIR.resolve() == _SRC_FRONTEND.resolve()
    for name, _ in ASSETS.values():
        assert (FRONTEND_DIR / name).is_file(), name
        assert (_SRC_FRONTEND / name).is_file(), name


def test_e21_frontend_holds_only_html_css_js() -> None:
    """E21: 'src/frontend' has no file besides HTML, CSS and JS (no .py)."""
    assert _FILES
    assert [p.name for p in _FILES if p.suffix not in _ALLOWED_SUFFIXES] == []


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_e21_no_forbidden_sinks_or_external_resources(path: Path) -> None:
    """E21: no DOM-string sink, no remote resource and no remote 'url(' in any asset (R15)."""
    text = _without_svg_namespace(path.read_text(encoding="utf-8"))
    assert [s for s in _SINKS if s in text] == []
    assert _REMOTE_URL.search(text) is None


def _without_svg_namespace(text: str) -> str:
    """'text' without the quoted SVG namespace literal, the only URL a file may hold (R15 amendment)."""
    return _SVG_NAMESPACE.sub("", text)


@pytest.mark.parametrize(
    ("text", "clean"),
    [
        ('document.createElementNS("http://www.w3.org/2000/svg", "svg")', True),
        ("""createElementNS('http://www.w3.org/2000/svg', "svg")""", True),
        ('"http://www.w3.org/2000/svg2"', False),
        ('"http://www.w3.org/2000/svg/x"', False),
        ('"https://www.w3.org/2000/svg"', False),
        ('"http://example.com/a"', False),
        ('"http://www.w3.org/2000/" + "svg"', False),
    ],
)
def test_e21_only_the_exact_svg_namespace_literal_is_allowed(text: str, clean: bool) -> None:
    """Risk: 014 E21 (R15): the SVG namespace exemption must not let any other http(s) URL through."""
    stripped = _without_svg_namespace(text)
    assert (not any(s in stripped for s in _SINKS)) is clean


@pytest.mark.parametrize("path", _FILES, ids=lambda p: p.name)
def test_e21_links_use_only_allowed_forms(path: Path) -> None:
    """E21: '.href =' and 'window.open(' take only the two plan forms, sid checked (R15)."""
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if _LINK_SINK.search(ln)]
    assert [ln for ln in lines if not _ALLOWED_LINK.search(ln)] == []
    if any("#${sid}" in ln for ln in lines):
        assert _SID_CHECK.search(text), "sid must be checked against /^S[0-9]{3}$/"


@pytest.mark.parametrize("name", ["index.html", "agentes.html", "metricas.html", "pronostico.html"])
def test_e21_html_pages_reference_only_allowlisted_assets(name: str) -> None:
    """E21: pages load only ASSETS routes, with no inline script, style or 'on...=' attribute (R15)."""
    html = (_SRC_FRONTEND / name).read_text(encoding="utf-8")
    refs = re.findall(r"""<(?:script|link|img)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']*)["']""", html, re.I)
    assert [r for r in refs if r not in ASSETS] == []
    assert re.search(r"<script\b(?![^>]*\bsrc=)[^>]*>", html, re.I) is None
    assert re.search(r"<script\b[^>]*>(?!\s*</script>)", html, re.I) is None
    assert re.search(r"<style\b|\sstyle\s*=|\son[a-z]+\s*=", html, re.I) is None


def test_e19_metricas_page_loads_exactly_css_dom_and_metrics_js() -> None:
    """E19 (R15): 'metricas.html' loads only '/app.css', '/dom.js' and '/metrics.js'."""
    html = (_SRC_FRONTEND / "metricas.html").read_text(encoding="utf-8")
    refs = re.findall(r"""<(?:script|link|img)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']*)["']""", html, re.I)
    assert sorted(refs) == ["/app.css", "/dom.js", "/metrics.js"]


@pytest.mark.parametrize("name", ["index.html", "agentes.html"])
def test_e19_planta_and_agentes_link_to_the_metricas_window(name: str) -> None:
    """E19 (R15, Q-101): both 014 pages hold the 'Métricas ↗' link opening the 'metricas' window."""
    html = (_SRC_FRONTEND / name).read_text(encoding="utf-8")
    assert re.search(r"""<a\s+href="/metricas"\s+target="metricas"[^>]*>Métricas ↗</a>""", html)
    assert 'href="/metricas" target="metricas"' in html


def test_e23_pronostico_page_loads_exactly_css_dom_and_forecast_js() -> None:
    """E23 (R18): 'pronostico.html' loads only '/app.css', '/dom.js' and '/forecast.js'."""
    html = (_SRC_FRONTEND / "pronostico.html").read_text(encoding="utf-8")
    refs = re.findall(r"""<(?:script|link|img)\b[^>]*?\b(?:src|href)\s*=\s*["']([^"']*)["']""", html, re.I)
    assert sorted(refs) == ["/app.css", "/dom.js", "/forecast.js"]


@pytest.mark.parametrize("name", ["index.html", "agentes.html", "metricas.html"])
def test_e23_other_pages_link_to_the_pronostico_window(name: str) -> None:
    """E23 (R18, Q-125): the other three pages hold the 'Pronóstico ↗' link to the 'pronostico' window."""
    html = (_SRC_FRONTEND / name).read_text(encoding="utf-8")
    assert '<a href="/pronostico" target="pronostico" rel="noopener">Pronóstico ↗</a>' in html


def test_e23_pronostico_page_marks_itself_active_and_links_the_other_three() -> None:
    """E23 (R18, Q-125): 'pronostico.html' has its own tab active and links Planta, Agentes and Métricas."""
    html = (_SRC_FRONTEND / "pronostico.html").read_text(encoding="utf-8")
    assert '<a href="/pronostico" class="on">Pronóstico</a>' in html
    assert 'target="pronostico"' not in html
    for href, label in [("/", "Planta"), ("/agentes", "Agentes"), ("/metricas", "Métricas")]:
        assert f'<a href="{href}">{label}</a>' in html


def test_e23_app_js_marker_opens_the_pronostico_window_from_cell_forecast() -> None:
    """E23 (R16, Q-126): 'app.js' draws the ⚠ from 'cell.forecast' and opens the literal '/pronostico'."""
    js = (_SRC_FRONTEND / "app.js").read_text(encoding="utf-8")
    assert 'window.open("/pronostico", "pronostico")' in js
    assert "cell.forecast" in js
    assert "⚠" in js


def test_e19_missing_metrics_js_raises_value_error_naming_it(
    thresholds_dir: Settings, tmp_path: Path
) -> None:
    """E19 (R15): a frontend folder without 'metrics.js' fails with the named message."""
    for name, _ in ASSETS.values():
        if name != "metrics.js":
            (tmp_path / name).write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\Adashboard: frontend asset not found: metrics\.js\Z"):
        DashboardApp.from_settings(thresholds_dir, frontend_dir=tmp_path)
