"""The 'plant-monitor run' command: top-level composition root of the full-series run (012, ADR-0018)."""

import argparse
import logging
import math
import sqlite3
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import ValidationError

from plant_monitor.agents.anthropic_model import AnthropicModel
from plant_monitor.agents.model import ModelPort
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.config import Settings, get_settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.models import Shift
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import Arrival, load_arrivals, load_arrivals_until
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds
from plant_monitor.notify.file import FileNotifier
from plant_monitor.runner.agent_pipeline import build_agent_pipeline
from plant_monitor.runner.outbox import OutboxDispatcher
from plant_monitor.runner.pipeline import ThresholdPipeline
from plant_monitor.runner.ports import PostCommit, SnapshotPipeline
from plant_monitor.runner.post_commit import Pacer, PostCommitChain
from plant_monitor.runner.series import RunAborted, run_series
from plant_monitor.runner.summary import (
    Mode,
    RunOutcome,
    RunReport,
    build_report,
    render_report,
    report_path,
    write_report,
)
from plant_monitor.telemetry.trace import TraceLine, TraceWriter, read_trace, trace_path

_SHIFTS_FILE = "turnos.csv"
_PLAN_FILE = "plan_produccion.csv"
_STANDARDS_FILE = "tiempos_estandar.csv"
_SHIPMENTS_FILE = "embarques.csv"
_THRESHOLDS_FILE = "umbrales.yaml"
_ARRIVALS_FILE = "llegadas.csv"
_TRACE_GLOB = "trace-*.jsonl"
_COMMAND = "run"
_EXIT_CODES = {"ok": 0, "aborted": 2, "interrupted": 130}
_USAGE_ERROR = 2


@dataclass(frozen=True)
class RunOptions:
    """The parsed command line."""

    mode: Mode
    until: str | None
    speed: float


def _seconds(text: str) -> float:
    """A finite, non-negative number of seconds."""
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from None
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"must be a finite number >= 0: {text!r}")
    return value


def parse_args(argv: Sequence[str] | None) -> RunOptions:
    """Parse 'run [--thresholds-only] [--until ID] [--speed SECONDS]'; argparse exits on errors."""
    parser = argparse.ArgumentParser(prog="plant-monitor")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser(_COMMAND, help="process the full series of snapshots")
    run.add_argument("--thresholds-only", action="store_true", help="no model: thresholds and templates only")
    run.add_argument("--until", metavar="SNAPSHOT_ID", help="stop after the first arrival of this snapshot")
    run.add_argument(
        "--speed", type=_seconds, default=0.0, metavar="SECONDS", help="pause after each snapshot"
    )
    args = parser.parse_args(argv)
    mode: Mode = "thresholds_only" if args.thresholds_only else "agent"
    return RunOptions(mode=mode, until=args.until, speed=args.speed)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class CliDeps:
    """Injectable seams of 'main'; the defaults are the real ones."""

    settings: Callable[[], Settings] = get_settings
    model_factory: Callable[[Settings], ModelPort] = AnthropicModel.from_settings
    sleep: Callable[[float], None] = time.sleep
    monotonic: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = field(default=_utc_now)


def select_arrivals(arrivals: Sequence[Arrival], until: str | None, policy: HeldOutPolicy) -> list[Arrival]:
    """Keep the arrivals up to the first one of 'until'; ValueError when it is not among them."""
    if until is None:
        return list(arrivals)
    for index, arrival in enumerate(arrivals):
        if arrival.snapshot_id == until:
            return list(arrivals[: index + 1])
    if until in policy.refused_snapshots:
        raise ValueError(f"--until {until}: snapshot is held out and the held-out guard is closed")
    raise ValueError(f"--until {until}: snapshot is not among the arrivals")


@dataclass(frozen=True)
class Prepared:
    """Plant data and the arrivals to process."""

    ctx: PlantContext
    shifts: tuple[Shift, ...]
    policy: HeldOutPolicy
    arrivals: tuple[Arrival, ...]


def _prepare(opts: RunOptions, settings: Settings) -> Prepared:
    """Load the plant, the held-out policy and the selected arrivals."""
    shifts = load_shifts(settings.plant_dir / _SHIFTS_FILE)
    ctx = PlantContext(
        plan=load_plan(settings.plant_dir / _PLAN_FILE, shifts),
        shifts=shifts,
        standards=StandardsTable.from_rows(load_standards(settings.plant_dir / _STANDARDS_FILE)),
        shipments=ShipmentsTable.from_rows(load_shipments(settings.plant_dir / _SHIPMENTS_FILE)),
        thresholds=load_thresholds(settings.rules_dir / _THRESHOLDS_FILE),
    )
    policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
    path = settings.snapshots_dir / _ARRIVALS_FILE
    loaded = load_arrivals(path) if policy.is_open else load_arrivals_until(path, policy)
    return Prepared(ctx, tuple(shifts), policy, tuple(select_arrivals(loaded, opts.until, policy)))


def _chain(steps: list[PostCommit], deps: CliDeps, opts: RunOptions) -> PostCommit:
    """The post-commit chain; the pacer goes last and only when '--speed' is above 0."""
    if opts.speed > 0:
        steps.append(Pacer(opts.speed, deps.sleep))
    return PostCommitChain(steps)


def _wire_thresholds(
    registry: SqliteRegistry, prepared: Prepared, settings: Settings, deps: CliDeps, opts: RunOptions
) -> tuple[SnapshotPipeline, PostCommit]:
    """Threshold-only wiring: no model, no trace."""
    pipeline = ThresholdPipeline.from_registry(registry, prepared.ctx)
    outbox = OutboxDispatcher(registry.notices, FileNotifier(settings.notices_dir), deps.now)
    return pipeline, _chain([outbox], deps, opts)


def _wire_agent(
    registry: SqliteRegistry,
    prepared: Prepared,
    settings: Settings,
    deps: CliDeps,
    opts: RunOptions,
    started: datetime,
) -> tuple[SnapshotPipeline, PostCommit]:
    """Agent wiring: investigator and coordinator, trace, outbox and optional pacer."""
    criteria = settings.criteria_path.read_text("utf-8-sig")
    model = deps.model_factory(settings)
    trace = TraceWriter(trace_path(settings.traces_dir, started))
    pipeline = build_agent_pipeline(settings, registry, prepared.ctx, prepared.policy, model, trace, criteria)
    outbox = OutboxDispatcher(registry.notices, FileNotifier(settings.notices_dir), deps.now)
    return pipeline, _chain([trace, outbox], deps, opts)


def _execute(
    arrivals: Sequence[Arrival],
    shifts: Sequence[Shift],
    registry: SqliteRegistry,
    pipeline: SnapshotPipeline,
    chain: PostCommit,
    deps: CliDeps,
) -> RunOutcome:
    """Run the series; only an abort and Ctrl-C become an outcome."""
    t0 = deps.monotonic()
    try:
        summary = run_series(arrivals, shifts, registry, pipeline, post_commit=chain)
    except RunAborted as exc:
        cause = f"{type(exc.cause).__name__}: {exc.cause}"
        return RunOutcome("aborted", exc.summary, (exc.snapshot_id, cause), deps.monotonic() - t0)
    except KeyboardInterrupt:
        return RunOutcome("interrupted", None, None, deps.monotonic() - t0)
    return RunOutcome("ok", summary, None, deps.monotonic() - t0)


def _report(settings: Settings, mode: Mode, started: datetime, outcome: RunOutcome) -> RunReport:
    """Build the report from this run's trace, every trace and the registry's deliverables."""
    run_file = trace_path(settings.traces_dir, started)
    run_lines = read_trace(run_file) if run_file.exists() else ()
    series_lines: list[TraceLine] = []
    for path in sorted(settings.traces_dir.glob(_TRACE_GLOB)):
        series_lines.extend(read_trace(path))
    return build_report(
        mode=mode,
        started_at=started,
        outcome=outcome,
        run_lines=run_lines,
        series_lines=series_lines,
        deliverables=read_deliverables(settings.registry_path),
    )


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return _USAGE_ERROR


def _run(opts: RunOptions, settings: Settings, deps: CliDeps) -> tuple[RunOutcome, datetime]:
    """Steps 3-8 of 'main': checks, wiring and the run. Raises the setup errors."""
    if opts.mode == "agent" and settings.anthropic_api_key is None:
        raise ValueError("ANTHROPIC_API_KEY is not set (needed in agent mode; use --thresholds-only)")
    # Q-71: a directory with agent-mode traces never gets threshold-only commits.
    if opts.mode == "thresholds_only" and any(settings.traces_dir.glob(_TRACE_GLOB)):
        raise ValueError(
            f"{settings.traces_dir} holds agent-mode traces: resume in agent mode or use a new OUTPUT_DIR"
        )
    logging.basicConfig(level=settings.log_level, stream=sys.stderr)
    prepared = _prepare(opts, settings)
    started = deps.now()
    for taken in (trace_path(settings.traces_dir, started), report_path(settings.runs_dir, started)):
        if taken.exists():
            raise ValueError(f"{taken} already exists: wait a second and run again")
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    # A 'sqlite3.Error' on registry close counts as a setup error (exit 2, no report): accepted, unlikely.
    with SqliteRegistry(settings.registry_path) as registry:
        if opts.mode == "agent":
            pipeline, chain = _wire_agent(registry, prepared, settings, deps, opts, started)
        else:
            pipeline, chain = _wire_thresholds(registry, prepared, settings, deps, opts)
        outcome = _execute(prepared.arrivals, prepared.shifts, registry, pipeline, chain, deps)
    return outcome, started


def _emit(settings: Settings, opts: RunOptions, started: datetime, outcome: RunOutcome) -> None:
    """Write and print the report; the registry is already closed."""
    report = _report(settings, opts.mode, started, outcome)
    path = report_path(settings.runs_dir, started)
    write_report(report, path)
    print(render_report(report))
    print(f"summary: {path}")


def main(argv: Sequence[str] | None = None, *, deps: CliDeps | None = None) -> int:
    """Run the command; 0 finished, 2 setup error or aborted run, 130 Ctrl-C."""
    deps = deps or CliDeps()
    try:
        opts = parse_args(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    try:
        settings = deps.settings()
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]).upper() for err in exc.errors() if err["loc"])
        detail = fields or str(exc.errors()[0]["msg"])
        return _fail(f"settings: invalid or missing {detail}")
    try:
        outcome, started = _run(opts, settings, deps)
    except (DataLoadError, ValueError, OSError, sqlite3.Error) as exc:
        return _fail(str(exc))
    if outcome.aborted is not None:
        print(f"run aborted at {outcome.aborted[0]}: {outcome.aborted[1]}", file=sys.stderr)
    try:
        _emit(settings, opts, started, outcome)
    except (OSError, ValueError) as exc:
        print(f"summary unavailable: {exc}", file=sys.stderr)
    return _EXIT_CODES[outcome.status]


if __name__ == "__main__":
    sys.exit(main())
