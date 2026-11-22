"""016: the forecast route, its assets, read-only access and the started server (E19, E22, E25, E28)."""

import hashlib
import json
import socket
import sqlite3
import threading
import urllib.request
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
import trace_builders
from dashboard_builders import HOST, app_of
from trace_builders import copied

from plant_monitor.config import Settings
from plant_monitor.dashboard import server
from plant_monitor.dashboard.server import DashboardApp, Response

thresholds_dir = trace_builders.thresholds_dir

SECURITY_HEADERS = ("Content-Security-Policy", "X-Content-Type-Options", "Cache-Control")


@pytest.fixture(scope="module")
def th_app(thresholds_dir: Settings) -> DashboardApp:
    """The dashboard app over TH_DIR; 'handle' only reads, so one instance serves the module."""
    return app_of(thresholds_dir)


def _assert_r14_headers(response: Response) -> None:
    """Every 014 R14 header is present and the CSP is the exact one."""
    headers = dict(response.headers)
    assert all(headers.get(name) for name in SECURITY_HEADERS)
    assert headers["Content-Security-Policy"] == server.CSP


def _json_of(app: DashboardApp, target: str) -> tuple[int, dict[str, Any]]:
    response = app.handle("GET", target, HOST)
    body: dict[str, Any] = json.loads(response.body)
    return response.status, body


def _tree(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    ("method", "target", "host", "status", "content_type"),
    [
        ("GET", "/pronostico", HOST, 200, "text/html; charset=utf-8"),
        ("GET", "/forecast.js?x=1", HOST, 200, "text/javascript; charset=utf-8"),
        ("GET", "/pronostico/", HOST, 404, None),
        ("GET", "/forecast.js/", HOST, 404, None),
        ("GET", "/pronostico.html", HOST, 404, None),
        ("POST", "/api/forecast", HOST, 405, None),
        ("GET", "/api/forecast", "evil.example:8765", 403, None),
        ("GET", "/api/forecast", HOST, 200, "application/json"),
    ],
)
def test_e22_routes_methods_and_hosts(
    th_app: DashboardApp, method: str, target: str, host: str, status: int, content_type: str | None
) -> None:
    """016 E22 (R17): status and type per new route, method and Host, with the 014 R14 headers."""
    response = th_app.handle(method, target, host)
    headers = dict(response.headers)
    assert response.status == status
    _assert_r14_headers(response)
    if status == 405:
        assert headers["Allow"] == "GET"
    if content_type is not None:
        assert headers["Content-Type"] == content_type


def test_e22_invalid_at_is_400_with_headers(th_app: DashboardApp) -> None:
    """016 E22 (R11): 'at=abc' on '/api/forecast' gives 400 with the fixed body and the R14 headers."""
    response = th_app.handle("GET", "/api/forecast?at=abc", HOST)
    assert (response.status, json.loads(response.body)) == (400, {"error": "dashboard: invalid at"})
    _assert_r14_headers(response)


def test_e22_snapshot_is_ignored_by_the_forecast_route(th_app: DashboardApp) -> None:
    """016 E22 (I10): 'snapshot=../x' is not validated on '/api/forecast' and changes nothing."""
    plain = th_app.handle("GET", "/api/forecast", HOST)
    odd = th_app.handle("GET", "/api/forecast?snapshot=../x", HOST)
    assert (odd.status, odd.body) == (200, plain.body)


def test_e22_locked_registry_is_503_busy(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """016 E22 (R17): a write lock gives 503 'registry busy' on the forecast route, with the R14 headers."""
    settings = copied(thresholds_dir, tmp_path)
    app = app_of(settings)
    real_connect = sqlite3.connect

    def quick(database: str, *, uri: bool, autocommit: bool, timeout: float) -> sqlite3.Connection:
        return real_connect(database, timeout=0.05, uri=uri, autocommit=autocommit)

    monkeypatch.setattr(sqlite3, "connect", quick)
    with closing(real_connect(settings.registry_path, isolation_level=None)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        response = app.handle("GET", "/api/forecast", HOST)
        writer.execute("ROLLBACK")
    assert response.status == 503
    assert json.loads(response.body) == {"error": "dashboard: registry busy"}
    _assert_r14_headers(response)


def _unavailable_copy(settings: Settings, tmp: Path, variant: str) -> Settings:
    """A copy of TH_DIR whose forecast table is gone with 'user_version' 4, or holds one '{}' payload."""
    broken = copied(settings, tmp)
    with closing(sqlite3.connect(broken.registry_path, isolation_level=None)) as conn:
        if variant == "v4":
            conn.execute("DROP TABLE gap_forecasts")
            conn.execute("PRAGMA user_version = 4")
        else:
            conn.execute(
                "UPDATE gap_forecasts SET payload = '{}' WHERE rowid = (SELECT MIN(rowid) FROM gap_forecasts)"
            )
    return broken


def _without_markers(state: dict[str, Any]) -> dict[str, Any]:
    """'/api/state' with every cell's 'forecast' set to None, to compare it with an unmarked twin."""
    return {**state, "cells": [{**cell, "forecast": None} for cell in state["cells"]]}


@pytest.mark.parametrize("variant", ["v4", "unreadable_payload"])
def test_e19_v4_and_unreadable_tables_are_unavailable_not_errors(
    thresholds_dir: Settings, tmp_path: Path, variant: str
) -> None:
    """016 E19 (R12, R16): no table or a bad payload gives 'unavailable', 200 everywhere, nothing written."""
    intact_state = _json_of(app_of(thresholds_dir), "/api/state")[1]
    settings = _unavailable_copy(thresholds_dir, tmp_path, variant)
    app = app_of(settings)
    registry_before = _sha(settings.registry_path)
    paths_before = _tree(settings.output_dir)

    forecast_status, forecast = _json_of(app, "/api/forecast")
    state_status, state = _json_of(app, "/api/state")
    metrics_status, _ = _json_of(app, "/api/metrics")

    assert (forecast_status, state_status, metrics_status) == (200, 200, 200)
    assert forecast["state"] == "unavailable"
    assert forecast["warnings"] == []
    assert forecast["combinations"] == []
    assert forecast["accuracy"]["episodes"] == []
    assert all(cell["forecast"] is None for cell in state["cells"])
    assert _without_markers(state) == _without_markers(intact_state)
    assert _sha(settings.registry_path) == registry_before
    assert _tree(settings.output_dir) == paths_before


def test_e25_an_emptied_table_is_unavailable_over_http(thresholds_dir: Settings, tmp_path: Path) -> None:
    """016 E25(a) (R12 amendment; Q-139): a v5 copy with no forecast row is 'unavailable', nothing written."""
    settings = copied(thresholds_dir, tmp_path)
    with closing(sqlite3.connect(settings.registry_path, isolation_level=None)) as conn:
        conn.execute("DELETE FROM gap_forecasts")
    app = app_of(settings)
    registry_before = _sha(settings.registry_path)
    paths_before = _tree(settings.output_dir)

    forecast_status, forecast = _json_of(app, "/api/forecast")
    state_status, state = _json_of(app, "/api/state")

    assert (forecast_status, state_status) == (200, 200)
    assert (forecast["registry"], forecast["state"]) == ("ok", "unavailable")
    assert forecast["warnings"] == forecast["combinations"] == []
    assert all(cell["forecast"] is None for cell in state["cells"])
    assert _sha(settings.registry_path) == registry_before
    assert _tree(settings.output_dir) == paths_before


def _get(port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as reply:
        return int(reply.status), dict(reply.headers), bytes(reply.read())


def test_e28_start_dashboard_serves_in_a_thread_until_stopped(th_app: DashboardApp) -> None:
    """016 E28 (R20; 014 R1, R14): the started server answers over 127.0.0.1, then 'stop' frees the port."""
    handle = server.start_dashboard(th_app, 0)
    try:
        page_status, page_headers, _ = _get(handle.port, "/")
        api_status, api_headers, body = _get(handle.port, "/api/forecast")
    finally:
        handle.stop()
    handle.stop()
    assert (page_status, api_status) == (200, 200)
    assert page_headers["Content-Type"] == "text/html; charset=utf-8"
    assert json.loads(body)["state"] == "ok"
    assert all(api_headers.get(name) for name in SECURITY_HEADERS)
    with pytest.raises(OSError), socket.create_connection(("127.0.0.1", handle.port), timeout=1):
        pass
    assert not any(t.name == server.DASHBOARD_THREAD and t.is_alive() for t in threading.enumerate())
