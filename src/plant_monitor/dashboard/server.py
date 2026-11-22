"""The local, read-only HTTP surface of the dashboard (014 R1, R2, R14, R15)."""

import json
import re
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Final
from urllib.parse import parse_qs, urlsplit

from plant_monitor.cases.registry.run_reader import RegistryBusy
from plant_monitor.config import Settings
from plant_monitor.dashboard.agents import build_agents
from plant_monitor.dashboard.forecast import build_forecast
from plant_monitor.dashboard.heldout import SNAPSHOT_ID
from plant_monitor.dashboard.metrics import build_metrics
from plant_monitor.dashboard.panels import load_accuracy, load_runs
from plant_monitor.dashboard.source import Calendar, load_calendar, load_view
from plant_monitor.dashboard.state import build_state
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.logbooks.store import LogbookStore

FRONTEND_DIR: Final = Path(__file__).resolve().parents[2] / "frontend"
_HTML: Final = "text/html; charset=utf-8"
_JS: Final = "text/javascript; charset=utf-8"
_CSS: Final = "text/css; charset=utf-8"
_JSON: Final = "application/json"
ASSETS: Final[Mapping[str, tuple[str, str]]] = {
    "/": ("index.html", _HTML),
    "/agentes": ("agentes.html", _HTML),
    "/app.css": ("app.css", _CSS),
    "/dom.js": ("dom.js", _JS),
    "/app.js": ("app.js", _JS),
    "/agents.js": ("agents.js", _JS),
    "/metricas": ("metricas.html", _HTML),
    "/metrics.js": ("metrics.js", _JS),
    "/pronostico": ("pronostico.html", _HTML),
    "/forecast.js": ("forecast.js", _JS),
}
_API_ROUTES: Final = frozenset({"/api/state", "/api/agents", "/api/metrics", "/api/forecast"})
_IGNORES_SNAPSHOT: Final = frozenset({"/api/metrics", "/api/forecast"})
CSP: Final = (
    "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
ALLOWED_HOSTS: Final = frozenset({"127.0.0.1", "localhost"})
_LOOPBACK: Final = "127.0.0.1"
_PORT_SUFFIX: Final = re.compile(r":[0-9]+$")
_AT: Final = re.compile(r"[0-9]{1,6}")
_SNAPSHOT: Final = re.compile(SNAPSHOT_ID)
_METHODS: Final = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


@dataclass(frozen=True)
class Response:
    """A status, headers and body, ready to be written to a socket."""

    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes


def _response(status: int, content_type: str, body: bytes, *extra: tuple[str, str]) -> Response:
    headers = (
        ("Content-Type", content_type),
        ("Content-Security-Policy", CSP),
        ("X-Content-Type-Options", "nosniff"),
        ("Cache-Control", "no-store"),
        *extra,
    )
    return Response(status, headers, body)


def _json(status: int, payload: object, *extra: tuple[str, str]) -> Response:
    return _response(status, _JSON, json.dumps(payload, ensure_ascii=True).encode("ascii"), *extra)


def _error(status: int, message: str, *extra: tuple[str, str]) -> Response:
    return _json(status, {"error": message}, *extra)


class DashboardApp:
    """Maps a request to a response; holds collaborators and asset bytes, never any run state."""

    def __init__(
        self,
        *,
        calendar: Calendar,
        logbooks: LogbookStore,
        policy: HeldOutPolicy,
        registry_path: Path,
        traces_dir: Path,
        evals_dir: Path,
        runs_dir: Path,
        assets: Mapping[str, bytes],
        history_window: int | None = None,
    ) -> None:
        self._calendar = calendar
        self._history_window = history_window
        self._logbooks = logbooks
        self._policy = policy
        self._registry_path = registry_path
        self._traces_dir = traces_dir
        self._evals_dir = evals_dir
        self._runs_dir = runs_dir
        self._assets = dict(assets)

    @classmethod
    def from_settings(cls, settings: Settings, frontend_dir: Path = FRONTEND_DIR) -> DashboardApp:
        """Startup steps 2-5 of R1: shifts and policy, plan, logbook store, frontend assets."""
        calendar, policy, shifts = load_calendar(settings)
        logbooks = LogbookStore(settings.logbooks_dir, shifts, policy)
        assets: dict[str, bytes] = {}
        for name, _ in ASSETS.values():
            path = frontend_dir / name
            if not path.is_file():
                raise ValueError(f"dashboard: frontend asset not found: {name}")
            assets[name] = path.read_bytes()
        return cls(
            calendar=calendar,
            logbooks=logbooks,
            policy=policy,
            registry_path=settings.registry_path,
            traces_dir=settings.traces_dir,
            evals_dir=settings.evals_dir,
            runs_dir=settings.runs_dir,
            assets=assets,
            history_window=settings.early_warning_window_snapshots,
        )

    def handle(self, method: str, target: str, host: str | None) -> Response:
        """Method, then Host, then route; the API reads the files afresh on every call."""
        if method != "GET":
            return _error(405, "dashboard: method not allowed", ("Allow", "GET"))
        if host is None or _PORT_SUFFIX.sub("", host) not in ALLOWED_HOSTS:
            return _error(403, "dashboard: host not allowed")
        split = urlsplit(target)
        route = split.path
        if route in ASSETS:
            name, content_type = ASSETS[route]
            return _response(200, content_type, self._assets[name])
        if route not in _API_ROUTES:
            return _error(404, "dashboard: not found")
        return self._api(route, parse_qs(split.query, keep_blank_values=True))

    def _api(self, route: str, query: Mapping[str, list[str]]) -> Response:
        raw_at = query.get("at", [None])[0]
        if raw_at is not None and _AT.fullmatch(raw_at) is None:
            return _error(400, "dashboard: invalid at")
        snapshot = query.get("snapshot", [None])[0]
        if route not in _IGNORES_SNAPSHOT and snapshot is not None and _SNAPSHOT.fullmatch(snapshot) is None:
            return _error(400, "dashboard: invalid snapshot")
        try:
            view = load_view(self._registry_path, self._traces_dir, self._policy)
        except RegistryBusy as error:
            return _error(503, str(error))
        except ValueError as error:
            return _error(500, str(error))
        at = view.resolve_at(None if raw_at is None else int(raw_at))
        try:
            if route == "/api/state":
                return _json(200, build_state(view, self._calendar, at))
            if route == "/api/metrics":
                accuracy = load_accuracy(self._evals_dir, self._registry_path, self._policy)
                runs = load_runs(self._runs_dir, self._traces_dir, self._policy)
                return _json(200, build_metrics(view, self._calendar, at, accuracy, runs))
            if route == "/api/forecast":
                return _json(200, build_forecast(view, self._calendar, at, self._history_window))
            return _json(200, build_agents(view, self._logbooks, at, snapshot))
        except Exception as error:  # last resort: a failed view is a 500, never a stack trace
            return _error(500, f"dashboard: view failed ({type(error).__name__})")


def make_server(app: DashboardApp, port: int) -> ThreadingHTTPServer:
    """A threading server bound to 127.0.0.1 only; port 0 picks a free one."""

    class Handler(BaseHTTPRequestHandler):
        def _serve(self) -> None:
            reply = app.handle(self.command, self.path, self.headers.get("Host"))
            self.send_response(reply.status)
            for name, value in reply.headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(reply.body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(reply.body)

        def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
            """Malformed requests get the same headers and JSON body as every other reply."""
            reply = _error(code, "dashboard: bad request")
            # Older 3.14 patches leave 'HTTP/0.9' on a bad version, which drops the status line and headers.
            if self.request_version not in ("HTTP/1.0", "HTTP/1.1"):
                self.request_version = "HTTP/1.0"
            self.send_response(code)
            for name, value in reply.headers:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(reply.body)))
            self.send_header("Connection", "close")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(reply.body)

        def log_message(self, format: str, *args: object) -> None:
            """No request lines."""

    for method in _METHODS:
        setattr(Handler, f"do_{method}", Handler._serve)

    class QuietServer(ThreadingHTTPServer):
        def handle_error(self, request: object, client_address: object) -> None:
            """Nothing reaches stderr."""

    server = QuietServer((_LOOPBACK, port), Handler)
    server.daemon_threads = True
    return server


DASHBOARD_THREAD: Final = "plant-monitor-dashboard"


@dataclass(frozen=True)
class RunningDashboard:
    """A server serving in its own thread; 'stop' is idempotent."""

    port: int
    stop: Callable[[], None]


def start_dashboard(app: DashboardApp, port: int) -> RunningDashboard:
    """Bind on 127.0.0.1 and serve in a daemon thread; 'OSError' when the port cannot be bound (016 R20)."""
    server = make_server(app, port)
    thread = threading.Thread(target=server.serve_forever, name=DASHBOARD_THREAD, daemon=True)
    thread.start()
    lock = threading.Lock()
    stopped = False

    def stop() -> None:
        nonlocal stopped
        with lock:
            if stopped:
                return
            stopped = True
        server.shutdown()
        server.server_close()
        thread.join()

    return RunningDashboard(port=server.server_address[1], stop=stop)


def serve_dashboard(app: DashboardApp, port: int, on_ready: Callable[[int], None]) -> None:
    """Bind, report the bound port, then serve until interrupted."""
    server = make_server(app, port)
    try:
        on_ready(server.server_address[1])
        server.serve_forever()
    finally:
        server.server_close()
