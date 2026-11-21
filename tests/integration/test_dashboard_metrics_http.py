"""015 T8: the metrics route, assets and read-only guarantee over the HTTP surface (E1, E18, E24)."""

import hashlib
import json
import shutil
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest
import trace_builders
from dashboard_builders import HOST, app_of, get_json
from metrics_builders import MT
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


def _quick_locks(monkeypatch: pytest.MonkeyPatch) -> Callable[..., sqlite3.Connection]:
    """Make dashboard sqlite connections give up after 50 ms; return the real 'connect' for the writer."""
    real_connect = sqlite3.connect

    def quick(database: str, *, uri: bool, autocommit: bool, timeout: float) -> sqlite3.Connection:
        return real_connect(database, timeout=0.05, uri=uri, autocommit=autocommit)

    monkeypatch.setattr(sqlite3, "connect", quick)
    return real_connect


def test_e1_invalid_at_is_400_before_any_registry_io(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """015 E1 (R1): 'at=-1' with a write lock held is 400, never 503."""
    app = app_of(copied(thresholds_dir, tmp_path))
    connect = _quick_locks(monkeypatch)
    with closing(connect(copied_registry(tmp_path), isolation_level=None)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        status, body = get_json(app, "/api/metrics?at=-1")
        writer.execute("ROLLBACK")
    assert (status, body) == (400, {"error": "dashboard: invalid at"})


def copied_registry(tmp: Path) -> Path:
    """The registry path inside the 'copied' output folder under 'tmp'."""
    return tmp / "out" / "registry.sqlite3"


@pytest.mark.parametrize(
    ("method", "target", "host", "status", "content_type"),
    [
        ("GET", "/metricas", HOST, 200, "text/html; charset=utf-8"),
        ("GET", "/metrics.js?x=1", HOST, 200, "text/javascript; charset=utf-8"),
        ("GET", "/metricas.html", HOST, 404, None),
        ("GET", "/metrics.js/", HOST, 404, None),
        ("GET", "/metricas/", HOST, 404, None),
        ("POST", "/api/metrics", HOST, 405, None),
        ("GET", "/api/metrics", "evil.example:8765", 403, None),
        ("GET", "/api/metrics", HOST, 200, "application/json"),
    ],
)
def test_e18_routes_methods_and_hosts(
    th_app: DashboardApp, method: str, target: str, host: str, status: int, content_type: str | None
) -> None:
    """015 E18 (R14): status and type per new route, method and Host, with the R14 headers."""
    response = th_app.handle(method, target, host)
    headers = dict(response.headers)
    assert response.status == status
    assert all(headers.get(name) for name in SECURITY_HEADERS)
    assert headers["Content-Security-Policy"] == server.CSP
    if status == 405:
        assert headers["Allow"] == "GET"
    if content_type is not None:
        assert headers["Content-Type"] == content_type


def test_e18_snapshot_is_ignored_by_the_metrics_route(th_app: DashboardApp) -> None:
    """015 E18 (I12): 'snapshot=../x' is not validated on '/api/metrics' and changes nothing."""
    plain = th_app.handle("GET", "/api/metrics", HOST)
    odd = th_app.handle("GET", "/api/metrics?snapshot=../x", HOST)
    assert (odd.status, odd.body) == (200, plain.body)


def _assert_security_headers(response: Response) -> None:
    """Every R14 header is present and the CSP is the exact one."""
    headers = dict(response.headers)
    assert all(headers.get(name) for name in SECURITY_HEADERS)
    assert headers["Content-Security-Policy"] == server.CSP


def test_e18_locked_registry_is_503_busy(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """015 E18 (R14): a write lock gives 503 'registry busy' on the metrics route."""
    app = app_of(copied(thresholds_dir, tmp_path))
    connect = _quick_locks(monkeypatch)
    with closing(connect(copied_registry(tmp_path), isolation_level=None)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        response = app.handle("GET", "/api/metrics", HOST)
        writer.execute("ROLLBACK")
    assert response.status == 503
    assert json.loads(response.body) == {"error": "dashboard: registry busy"}
    _assert_security_headers(response)


def test_e18_unreadable_registry_is_500_without_values(thresholds_dir: Settings, tmp_path: Path) -> None:
    """015 E18 (R14): a registry that is not sqlite gives 500 with the class name only."""
    settings = copied(thresholds_dir, tmp_path)
    settings.registry_path.write_bytes(b"not sqlite")
    response = app_of(settings).handle("GET", "/api/metrics", HOST)
    assert response.status == 500
    assert json.loads(response.body) == {
        "error": "dashboard: registry.sqlite3 is not a readable registry (DatabaseError)"
    }
    _assert_security_headers(response)


def test_e18_build_failure_is_500_with_the_class_name_only(
    th_app: DashboardApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """015 E18 (R14): a 'build_metrics' error gives 500 'view failed (ValueError)' without the value."""

    def failing(*args: object) -> object:
        raise ValueError("secret S011")

    monkeypatch.setattr(server, "build_metrics", failing)
    response = th_app.handle("GET", "/api/metrics", HOST)
    assert response.status == 500
    assert json.loads(response.body) == {"error": "dashboard: view failed (ValueError)"}
    _assert_security_headers(response)


def _tree(root: Path) -> list[Path]:
    return sorted(p.relative_to(root) for p in root.rglob("*"))


def test_e24_metrics_reads_write_and_create_nothing(thresholds_dir: Settings, tmp_path: Path) -> None:
    """015 E24 (R2): no 'runs/' or 'evals/' is created, and the registry and path set do not change."""
    settings = copied(thresholds_dir, tmp_path)
    shutil.rmtree(settings.runs_dir, ignore_errors=True)
    assert not settings.evals_dir.exists()
    registry_before = hashlib.sha256(settings.registry_path.read_bytes()).hexdigest()
    paths_before = _tree(settings.output_dir)
    app = app_of(settings)
    assert MT(settings)["latest"] == 12
    assert get_json(app, "/api/metrics?at=3")[0] == 200
    assert hashlib.sha256(settings.registry_path.read_bytes()).hexdigest() == registry_before
    assert _tree(settings.output_dir) == paths_before
    assert not settings.runs_dir.exists()
    assert not settings.evals_dir.exists()


def test_e24_missing_output_dir_is_an_empty_window_and_not_created(
    thresholds_dir: Settings, tmp_path: Path
) -> None:
    """015 E24 (R2): without an 'OUTPUT_DIR' the window is 'missing' with 0 positions, nothing created."""
    missing = tmp_path / "nowhere"
    metrics = MT(thresholds_dir.model_copy(update={"output_dir": missing}))
    assert (metrics["registry"], metrics["latest"]) == ("missing", 0)
    assert not missing.exists()
