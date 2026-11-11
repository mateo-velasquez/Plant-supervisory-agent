"""Paid run of days 1-7 (008 R22, 009 R17): S001-S042 through investigator and coordinator; never in CI."""

import sqlite3
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from plant_monitor.agents.anthropic_model import AnthropicModel
from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import get_settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import load_arrivals_until
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds
from plant_monitor.notify.file import FileNotifier
from plant_monitor.runner.agent_pipeline import build_agent_pipeline
from plant_monitor.runner.outbox import OutboxDispatcher
from plant_monitor.runner.post_commit import PostCommitChain
from plant_monitor.runner.series import RunAborted, run_series
from plant_monitor.telemetry.trace import TraceWriter, read_trace, run_totals, trace_path

_SHIFTS_FILE = "turnos.csv"
_PLAN_FILE = "plan_produccion.csv"
_STANDARDS_FILE = "tiempos_estandar.csv"
_SHIPMENTS_FILE = "embarques.csv"
_THRESHOLDS_FILE = "umbrales.yaml"
_ARRIVALS_FILE = "llegadas.csv"
_REGISTRY_FILE = "registry.sqlite3"
_FIRST_HELD_OUT_SHIFT = "T22"  # S001-S042 only: days 8-10 stay held out for this run


def main() -> int:
    """Run S001-S042 through the agent pipeline in a new directory; 0 on success, 2 on failure."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]).upper() for err in exc.errors())
        print(f"settings: invalid or missing {fields}", file=sys.stderr)
        return 2
    started = datetime.now(UTC)
    clock = time.monotonic()
    trace_file: Path | None = None
    try:
        shifts = load_shifts(settings.plant_dir / _SHIFTS_FILE)
        ctx = PlantContext(
            plan=load_plan(settings.plant_dir / _PLAN_FILE, shifts),
            shifts=shifts,
            standards=StandardsTable.from_rows(load_standards(settings.plant_dir / _STANDARDS_FILE)),
            shipments=ShipmentsTable.from_rows(load_shipments(settings.plant_dir / _SHIPMENTS_FILE)),
            thresholds=load_thresholds(settings.rules_dir / _THRESHOLDS_FILE),
        )
        policy = HeldOutPolicy.from_calendar(shifts, _FIRST_HELD_OUT_SHIFT, is_open=False)
        arrivals = load_arrivals_until(settings.snapshots_dir / _ARRIVALS_FILE, policy)
        out = settings.output_dir / f"agent-{started:%Y%m%dT%H%M%SZ}"
        out.mkdir(parents=True)  # fresh run directory; fails if it already exists
        trace_file = trace_path(out / "traces", started)
        trace_file.parent.mkdir()
        trace = TraceWriter(trace_file)
        model = AnthropicModel.from_settings(settings)
        with SqliteRegistry(out / _REGISTRY_FILE) as registry:
            pipeline = build_agent_pipeline(settings, registry, ctx, policy, model, trace)
            outbox = OutboxDispatcher(registry.notices, FileNotifier(out / "notices"))
            summary = run_series(
                arrivals, shifts, registry, pipeline, post_commit=PostCommitChain([trace, outbox])
            )
    except (RunAborted, DataLoadError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"agent run failed: {exc}", file=sys.stderr)
        if trace_file is not None and trace_file.exists():
            try:
                _print_cost(trace_file, clock)
            except (OSError, ValueError) as trace_error:
                print(f"trace unreadable: {trace_error}", file=sys.stderr)
        return 2

    print(f"run directory: {out}")
    print(f"processed: {', '.join(summary.processed) or '-'}")
    print(f"skipped: {', '.join(summary.skipped) or '-'}")
    _print_cost(trace_file, clock)
    return 0


def _print_cost(trace_file: Path, clock: float) -> None:
    """Print the trace path, the run totals, the per-agent split and the duration."""
    totals = run_totals(read_trace(trace_file))
    print(f"trace: {trace_file}")
    print(
        f"snapshots={totals.snapshots} called={totals.called} model_calls={totals.model_calls} "
        f"input_tokens={totals.input_tokens} output_tokens={totals.output_tokens} usd={totals.usd}"
    )
    for agent, share in totals.by_agent.items():
        print(
            f"  {agent}: runs={share.runs} model_calls={share.model_calls} "
            f"input_tokens={share.input_tokens} output_tokens={share.output_tokens} usd={share.usd}"
        )
    print(f"duration: {time.monotonic() - clock:.1f}s")


if __name__ == "__main__":
    sys.exit(main())
