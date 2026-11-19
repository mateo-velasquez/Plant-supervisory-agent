"""014 T6: the 'plant-monitor html' command over the synthetic threshold-only run, no model (E11-E15)."""

import hashlib
import io
import re
import sys
from pathlib import Path
from urllib.parse import quote

import pytest
from cli_builders import cli_deps
from html_builders import A1, rendered, variant
from trace_builders import copied, thresholds_dir

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.config import Settings
from plant_monitor.domain.notices import Notice, ShiftReport, report_id_for
from plant_monitor.runner.cli import main

from builders import isolate_settings_env
from notice_builders import shift_report

__all__ = ["thresholds_dir"]


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_env(monkeypatch, tmp_path)


def _page_name(item: Notice | ShiftReport) -> str:
    """The file name of the page of one stored deliverable."""
    stem = report_id_for(item.turno_id) if isinstance(item, ShiftReport) else item.notice_id
    return f"{stem}.html"


def _tree(root: Path) -> set[Path]:
    """Every path under 'root', relative to it."""
    return {p.relative_to(root) for p in root.rglob("*")}


def test_e11_full_render_is_read_only_and_repeatable(
    thresholds_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """014 E11: all pages and the index, registry untouched, no model, second render byte-identical."""
    settings = copied(thresholds_dir, tmp_path)
    items = read_deliverables(settings.registry_path)
    alerts = sum(isinstance(i, Notice) for i in items)
    digest = hashlib.sha256(settings.registry_path.read_bytes()).hexdigest()
    before = _tree(settings.output_dir)

    code, out, err = rendered(settings, capsys)

    assert (code, err) == (0, "")
    assert out == f"html: shift reports 6, alerts {alerts}, in {settings.html_dir}\n"
    names = [_page_name(i) for i in items]
    assert sorted(p.name for p in settings.html_dir.iterdir()) == sorted([*names, "index.html"])
    index = (settings.html_dir / "index.html").read_text(encoding="utf-8")
    assert re.findall(r'href="([^"]*)"', index) == [quote(n, safe="") for n in names]
    assert hashlib.sha256(settings.registry_path.read_bytes()).hexdigest() == digest
    after = _tree(settings.output_dir)
    html = settings.html_dir.relative_to(settings.output_dir)
    assert {p for p in after if html not in p.parents and p != html} == before
    first = {p.name: p.read_bytes() for p in settings.html_dir.iterdir()}

    assert rendered(settings, capsys)[0] == 0
    assert {p.name: p.read_bytes() for p in settings.html_dir.iterdir()} == first


def test_e12_closed_guard_omits_held_out_items(
    thresholds_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """014 E12: with the guard closed no page or id of S011, S012 or T06 is written."""
    settings = copied(thresholds_dir, tmp_path).model_copy(update={"heldout_open": False})
    items = read_deliverables(settings.registry_path)
    k = sum(i.snapshot_id in {"S011", "S012"} for i in items)

    code, out, err = rendered(settings, capsys)

    assert k >= 2
    assert code == 0
    assert err == f"html: {k} held-out or unverifiable items omitted (HELDOUT_OPEN=false)\n"
    assert out.startswith("html: shift reports 5,")
    pages = list(settings.html_dir.iterdir())
    assert not (settings.html_dir / "T06-informe.html").exists()
    assert not (settings.html_dir / "S012-alerta_inmediata-S010-Pickup-Local.html").exists()
    for page in pages:
        text = page.read_text(encoding="utf-8")
        assert re.search(r"S011|S012|T06", text) is None, page.name
    assert not any(p.name.startswith(("S011", "S012")) for p in pages)


def test_e13_registry_missing_exit_2_and_nothing_created(
    thresholds_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """014 E13a: a missing registry exits 2 and the output directory is not created."""
    missing = tmp_path / "O2"

    code, _out, err = rendered(thresholds_dir.model_copy(update={"output_dir": missing}), capsys)

    assert code == 2
    assert "registry not found" in err
    assert not missing.exists()


def test_e13_unknown_first_heldout_shift_exit_2(
    thresholds_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """014 E13b: a first held-out shift that is not in 'turnos.csv' exits 2."""
    settings = copied(thresholds_dir, tmp_path).model_copy(update={"heldout_first_shift": "T99"})

    code, _out, err = rendered(settings, capsys)

    assert code == 2
    assert err.splitlines() == ["first held-out shift T99 is not in turnos.csv"]


def test_e13_unsafe_id_exit_2_and_nothing_written(
    thresholds_dir: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """014 E13c: with the guard open an unsafe id exits 2 and 'html_dir' is not created."""
    settings = copied(thresholds_dir, tmp_path)
    monkeypatch.setattr(
        "plant_monitor.runner.cli.read_deliverables", lambda _path: (shift_report("../T05", "S010"),)
    )

    code, _out, err = rendered(settings, capsys)

    assert code == 2
    assert err.splitlines() == ["html: invalid turno_id: ../T05"]
    assert not settings.html_dir.exists()


def test_e13_empty_registry_renders_only_the_index(
    thresholds_dir: Settings, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """014 E13d: a registry with no rows exits 0 and writes only 'index.html'."""
    out_dir = tmp_path / "fresh"
    out_dir.mkdir()
    settings = thresholds_dir.model_copy(update={"output_dir": out_dir})
    SqliteRegistry(settings.registry_path).close()

    code, out, err = rendered(settings, capsys)

    assert (code, err) == (0, "")
    assert out == f"html: shift reports 0, alerts 0, in {settings.html_dir}\n"
    assert [p.name for p in settings.html_dir.iterdir()] == ["index.html"]
    assert '<p class="empty">Sin informes ni alertas</p>' in (settings.html_dir / "index.html").read_text(
        encoding="utf-8"
    )


def test_e14_cp1252_stderr_survives_a_non_ascii_id(
    thresholds_dir: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Risk: 014 E14 an error naming U+2212 must not raise inside the error path on a cp1252 stderr."""
    settings = copied(thresholds_dir, tmp_path)
    monkeypatch.setattr(
        "plant_monitor.runner.cli.read_deliverables",
        lambda _path: (shift_report("T05\N{MINUS SIGN}", "S010"),),
    )
    buffer = io.BytesIO()
    stderr = io.TextIOWrapper(buffer, encoding="cp1252", newline="")
    monkeypatch.setattr(sys, "stderr", stderr)

    code = main(["html"], deps=cli_deps(settings, None))
    stderr.flush()

    assert code == 2
    assert buffer.getvalue() == b"html: invalid turno_id: T05\\u2212\n"


def test_e15b_unencodable_text_exit_2_and_nothing_written(
    thresholds_dir: Settings,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """014 E15b: a lone surrogate in a stored text exits 2 before any write."""
    settings = copied(thresholds_dir, tmp_path)
    bad = variant(A1, texto="x\ud800")
    monkeypatch.setattr("plant_monitor.runner.cli.read_deliverables", lambda _path: (bad,))

    code, _out, err = rendered(settings, capsys)

    assert code == 2
    assert err.splitlines() == ["html: S009-alerta_inmediata-S001-Sedán-Local.html is not encodable as UTF-8"]
    assert not settings.html_dir.exists()
