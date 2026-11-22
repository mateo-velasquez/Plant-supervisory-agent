"""014 T10: the dashboard HTTP surface, in process and over a real socket (E1, E16, E17, E21, E24)."""

import hashlib
import json
import socket
import sqlite3
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import closing, contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
import trace_builders
from dashboard_builders import HOST, app_of, get_json
from trace_builders import copied

from plant_monitor.config import Settings
from plant_monitor.dashboard import server
from plant_monitor.dashboard.server import CSP, DashboardApp

thresholds_dir = trace_builders.thresholds_dir

EXPECTED_CSP = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": EXPECTED_CSP,
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "no-store",
}
ASSET_NAMES = (
    "index.html",
    "agentes.html",
    "metricas.html",
    "app.css",
    "dom.js",
    "app.js",
    "agents.js",
    "metrics.js",
    "pronostico.html",
    "forecast.js",
)


@pytest.fixture(scope="module")
def th_app(thresholds_dir: Settings) -> DashboardApp:
    """The dashboard app over TH_DIR; 'handle' only reads, so one instance serves the module."""
    return app_of(thresholds_dir)


@pytest.mark.parametrize("query", ["at=abc", "at=-1", "at=1234567", "at="])
@pytest.mark.parametrize("route", ["/api/state", "/api/agents", "/api/metrics", "/api/forecast"])
def test_e1_invalid_at_is_400(th_app: DashboardApp, route: str, query: str) -> None:
    """014 E1 (R3): a non-number, negative, oversized or blank 'at' gives 400 with the fixed body."""
    status, body = get_json(th_app, f"{route}?{query}")
    assert (status, body) == (400, {"error": "dashboard: invalid at"})


@pytest.mark.parametrize("query", ["snapshot=abc", "snapshot=", "snapshot=S12", "snapshot=S0123"])
def test_e1_invalid_snapshot_is_400(th_app: DashboardApp, query: str) -> None:
    """014 E1 (R8): a 'snapshot' that is not 'S[0-9]{3}' gives 400 with the fixed body."""
    status, body = get_json(th_app, f"/api/agents?{query}")
    assert (status, body) == (400, {"error": "dashboard: invalid snapshot"})


@pytest.mark.parametrize(
    ("method", "target", "host", "status", "content_type"),
    [
        ("GET", "/", HOST, 200, "text/html; charset=utf-8"),
        ("GET", "/app.js?x=1", HOST, 200, "text/javascript; charset=utf-8"),
        ("GET", "/index.html", HOST, 404, None),
        ("GET", "/app.js/", HOST, 404, None),
        ("GET", "/../registry.sqlite3", HOST, 404, None),
        ("GET", "/%2e%2e/x", HOST, 404, None),
        ("GET", "/frontend/app.js", HOST, 404, None),
        ("POST", "/api/state", HOST, 405, None),
        ("HEAD", "/", HOST, 405, None),
        ("GET", "/api/state", "evil.example:8765", 403, None),
        ("GET", "/api/state", "localhost:9999", 200, "application/json"),
        ("GET", "/api/state", "127.0.0.1", 200, "application/json"),
        ("GET", "/api/state", None, 403, None),
    ],
)
def test_e16_routes_methods_and_hosts(
    th_app: DashboardApp, method: str, target: str, host: str | None, status: int, content_type: str | None
) -> None:
    """014 E16 (R14, Q-98): status per route, method and Host (port ignored); headers on every response."""
    response = th_app.handle(method, target, host)
    headers = dict(response.headers)
    assert response.status == status
    assert {name: headers.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS
    assert CSP == EXPECTED_CSP
    if status == 405:
        assert headers["Allow"] == "GET"
    if content_type is not None:
        assert headers["Content-Type"] == content_type


def test_e16_unreadable_registry_is_500_without_values(thresholds_dir: Settings, tmp_path: Path) -> None:
    """014 E16 (R14): a registry that is not sqlite gives 500 with the class name only, same headers."""
    settings = copied(thresholds_dir, tmp_path)
    settings.registry_path.write_bytes(b"not sqlite")
    response = app_of(settings).handle("GET", "/api/state", HOST)
    assert response.status == 500
    assert json.loads(response.body) == {
        "error": "dashboard: registry.sqlite3 is not a readable registry (DatabaseError)"
    }
    assert dict(response.headers)["Content-Security-Policy"] == EXPECTED_CSP


@pytest.mark.parametrize("route", ["/api/state", "/api/agents"])
def test_e16_view_build_failure_is_500_with_the_class_name_and_headers(
    th_app: DashboardApp, monkeypatch: pytest.MonkeyPatch, route: str
) -> None:
    """014 E16 (R14): a view-build error gives 500 'view failed (<ErrorClass>)' with the R14 headers."""

    def failing(*args: object) -> object:
        raise ValueError("secret value S011")

    monkeypatch.setattr(server, "build_state", failing)
    monkeypatch.setattr(server, "build_agents", failing)
    response = th_app.handle("GET", route, HOST)
    headers = dict(response.headers)
    assert response.status == 500
    assert json.loads(response.body) == {"error": "dashboard: view failed (ValueError)"}
    assert {name: headers.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS


@pytest.mark.parametrize("target", ["build_state", "build_agents"])
def test_e16_view_build_oserror_is_500_with_the_class_name_and_headers(
    th_app: DashboardApp, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """014 E16 (R14): an 'OSError' while building a view also gives 500 'view failed (OSError)'."""

    def failing(*args: object) -> object:
        raise OSError("C:\\secret\\path")

    monkeypatch.setattr(server, target, failing)
    route = "/api/state" if target == "build_state" else "/api/agents"
    response = th_app.handle("GET", route, HOST)
    headers = dict(response.headers)
    assert response.status == 500
    assert json.loads(response.body) == {"error": "dashboard: view failed (OSError)"}
    assert {name: headers.get(name) for name in SECURITY_HEADERS} == SECURITY_HEADERS


@pytest.mark.parametrize("query", ["snapshot=bad", "at=abc"])
def test_e1_e24_invalid_params_are_400_before_any_registry_io(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, query: str
) -> None:
    """014 E1, E24 (R2, R3, R8): params are validated before I/O, so a locked registry still gives 400."""
    settings = copied(thresholds_dir, tmp_path)
    app = app_of(settings)
    real_connect = sqlite3.connect

    def quick(database: str, *, uri: bool, autocommit: bool, timeout: float) -> sqlite3.Connection:
        return real_connect(database, timeout=0.05, uri=uri, autocommit=autocommit)

    monkeypatch.setattr(sqlite3, "connect", quick)
    with closing(real_connect(settings.registry_path, isolation_level=None)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        status, body = get_json(app, f"/api/agents?{query}")
        writer.execute("ROLLBACK")
    assert status == 400
    assert body == {"error": f"dashboard: invalid {query.split('=')[0]}"}


def test_e16_view_failure_over_the_socket_writes_nothing_to_stderr(
    thresholds_dir: Settings, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]
) -> None:
    """014 E16 (R14): an 'OSError' in a view build is a 500 reply, with no traceback or line on stderr."""

    def failing(*args: object) -> object:
        raise OSError("boom")

    monkeypatch.setattr(server, "build_state", failing)
    with (
        _serving(app_of(thresholds_dir), monkeypatch) as port,
        pytest.raises(urllib.error.HTTPError) as caught,
    ):
        _fetch(port, "/api/state")
    assert caught.value.code == 500
    assert json.loads(caught.value.read()) == {"error": "dashboard: view failed (OSError)"}
    assert capfd.readouterr().err == ""


@contextmanager
def _serving(app: DashboardApp, patch: pytest.MonkeyPatch) -> Iterator[int]:
    """Run 'serve_dashboard' on an ephemeral port in a thread; yield the port, shut down on exit."""
    started = threading.Event()
    ports: list[int] = []
    servers: list[ThreadingHTTPServer] = []
    real_make = server.make_server

    def capture(target: DashboardApp, port: int) -> ThreadingHTTPServer:
        servers.append(real_make(target, port))
        return servers[0]

    def on_ready(port: int) -> None:
        ports.append(port)
        started.set()

    patch.setattr(server, "make_server", capture)
    thread = threading.Thread(target=server.serve_dashboard, args=(app, 0, on_ready), daemon=True)
    thread.start()
    try:
        assert started.wait(5), "on_ready was not called"
        yield ports[0]
    finally:
        if servers:
            servers[0].shutdown()
        thread.join(5)
    assert not thread.is_alive()


def _fetch(port: int, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as reply:
        return int(reply.status), bytes(reply.read())


def test_e17_real_socket_serves_the_same_bodies_and_writes_nothing(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """014 E17 (R1, R2, R14): four GETs over 127.0.0.1 match 'handle'; no byte or file changes."""
    settings = copied(thresholds_dir, tmp_path)
    app = app_of(settings)
    before_bytes = hashlib.sha256(settings.registry_path.read_bytes()).hexdigest()
    before_paths = sorted(p.relative_to(settings.output_dir) for p in settings.output_dir.rglob("*"))
    paths = ["/", "/agentes", "/api/state", "/api/agents?snapshot=S012"]
    with _serving(app, monkeypatch) as port:
        assert port > 0
        replies = [_fetch(port, path) for path in paths]
    assert [status for status, _ in replies] == [200] * 4
    for path, (_, body) in zip(paths, replies, strict=True):
        assert body == app.handle("GET", path, HOST).body
    assert hashlib.sha256(settings.registry_path.read_bytes()).hexdigest() == before_bytes
    assert sorted(p.relative_to(settings.output_dir) for p in settings.output_dir.rglob("*")) == before_paths


def _raw_reply(port: int, request: bytes) -> tuple[bytes, dict[str, str]]:
    """Send raw 'request' bytes and return the status line with the lower-cased reply headers."""
    with socket.create_connection(("127.0.0.1", port), timeout=5) as conn:
        conn.sendall(request)
        data = b""
        while chunk := conn.recv(4096):
            data += chunk
    head = data.split(b"\r\n\r\n", 1)[0].decode("latin-1").split("\r\n")
    return head[0].encode(), {k.lower(): v for k, v in (ln.split(": ", 1) for ln in head[1:] if ": " in ln)}


@pytest.mark.parametrize(
    ("request_bytes", "status"),
    [
        (b"TRACE / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n", b"501"),
        (b"GET / HTTPX\r\nHost: 127.0.0.1\r\n\r\n", b"400"),
    ],
)
def test_e16_unsupported_method_and_malformed_request_keep_the_r14_headers(
    thresholds_dir: Settings,
    monkeypatch: pytest.MonkeyPatch,
    request_bytes: bytes,
    status: bytes,
) -> None:
    """014 E16 (R14): errors the stdlib raises before 'handle' still carry CSP, nosniff and no-store."""
    with _serving(app_of(thresholds_dir), monkeypatch) as port:
        line, headers = _raw_reply(port, request_bytes)
    assert status in line
    assert {k: headers.get(k.lower()) for k in SECURITY_HEADERS} == SECURITY_HEADERS


def test_e17_missing_output_dir_serves_empty_state_and_is_not_created(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """014 E17 (R2): without an 'OUTPUT_DIR' the state says 'missing', 0 positions, and nothing is created."""
    missing = tmp_path / "nowhere"
    app = app_of(thresholds_dir.model_copy(update={"output_dir": missing}))
    with _serving(app, monkeypatch) as port:
        status, body = _fetch(port, "/api/state")
    state = json.loads(body)
    assert (status, state["registry"], state["latest"]) == (200, "missing", 0)
    assert not missing.exists()


def test_e21_missing_asset_raises_value_error_naming_it(thresholds_dir: Settings, tmp_path: Path) -> None:
    """014 E21 (R1, R15): a frontend folder without 'agents.js' fails with the named message."""
    for name in ASSET_NAMES:
        if name != "agents.js":
            (tmp_path / name).write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\Adashboard: frontend asset not found: agents\.js\Z"):
        DashboardApp.from_settings(thresholds_dir, frontend_dir=tmp_path)


def test_e24_locked_registry_is_503_then_200_after_release(
    thresholds_dir: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """014 E24 (R2): a write lock gives 503 'registry busy', never 500; released, it answers 200."""
    settings = copied(thresholds_dir, tmp_path)
    app = app_of(settings)
    real_connect = sqlite3.connect

    def quick(database: str, *, uri: bool, autocommit: bool, timeout: float) -> sqlite3.Connection:
        return real_connect(database, timeout=0.05, uri=uri, autocommit=autocommit)

    monkeypatch.setattr(sqlite3, "connect", quick)
    with closing(real_connect(settings.registry_path, isolation_level=None)) as writer:
        writer.execute("BEGIN EXCLUSIVE")
        assert get_json(app, "/api/state") == (503, {"error": "dashboard: registry busy"})
        writer.execute("ROLLBACK")
    assert get_json(app, "/api/state")[0] == 200
