"""Smoke run over days 1-7 (005, A3): replays the arrivals into a new registry, prints the timeline."""

import sqlite3
import sys
from datetime import UTC, datetime

from pydantic import ValidationError

from plant_monitor.cases.registry import SqliteRegistry
from plant_monitor.config import get_settings
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.evaluation.sources import load_run_output
from plant_monitor.evaluation.timeline import case_timeline
from plant_monitor.ingestion import DataLoadError
from plant_monitor.ingestion.arrivals import load_arrivals_until
from plant_monitor.ingestion.plant import load_plan, load_shifts, load_shipments, load_standards
from plant_monitor.metrics.engine import PlantContext
from plant_monitor.metrics.tables import ShipmentsTable, StandardsTable
from plant_monitor.metrics.thresholds import load_thresholds
from plant_monitor.notify.file import FileNotifier
from plant_monitor.runner.outbox import OutboxDispatcher
from plant_monitor.runner.pipeline import ThresholdPipeline
from plant_monitor.runner.series import RunAborted, run_series

_SHIFTS_FILE = "turnos.csv"
_PLAN_FILE = "plan_produccion.csv"
_STANDARDS_FILE = "tiempos_estandar.csv"
_SHIPMENTS_FILE = "embarques.csv"
_THRESHOLDS_FILE = "umbrales.yaml"
_ARRIVALS_FILE = "llegadas.csv"
_REGISTRY_FILE = "registry.sqlite3"


def main() -> int:
    """Replay days 1-7 into a new run directory; 0 when no notice is pending, 1 otherwise, 2 on failure."""
    try:
        settings = get_settings()
    except ValidationError as exc:
        fields = ", ".join(str(err["loc"][0]).upper() for err in exc.errors())
        print(
            f"settings: invalid or missing {fields} (unused by this script; set any value)", file=sys.stderr
        )
        return 2
    try:
        shifts = load_shifts(settings.plant_dir / _SHIFTS_FILE)
        ctx = PlantContext(
            plan=load_plan(settings.plant_dir / _PLAN_FILE, shifts),
            shifts=shifts,
            standards=StandardsTable.from_rows(load_standards(settings.plant_dir / _STANDARDS_FILE)),
            shipments=ShipmentsTable.from_rows(load_shipments(settings.plant_dir / _SHIPMENTS_FILE)),
            thresholds=load_thresholds(settings.rules_dir / _THRESHOLDS_FILE),
        )
        policy = HeldOutPolicy.from_calendar(shifts, settings.heldout_first_shift, settings.heldout_open)
        arrivals = load_arrivals_until(settings.snapshots_dir / _ARRIVALS_FILE, policy)
        out = settings.evals_dir / f"smoke-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        out.mkdir(parents=True)  # fresh run directory; fails if it already exists
        registry_path = out / _REGISTRY_FILE
        with SqliteRegistry(registry_path) as registry:
            summary = run_series(
                arrivals,
                shifts,
                registry,
                ThresholdPipeline.from_registry(registry, ctx),
                post_commit=OutboxDispatcher(registry.notices, FileNotifier(out / "notices")),
            )
            pending = registry.notices.pending()
        run = load_run_output(registry_path, policy)  # read after the registry is closed
    except (RunAborted, DataLoadError, ValueError, OSError, sqlite3.Error) as exc:
        print(f"smoke run failed: {exc}", file=sys.stderr)
        return 2

    print(f"run directory: {out}")
    print(f"processed: {', '.join(summary.processed) or '-'}")
    print(f"skipped: {', '.join(summary.skipped) or '-'}")
    for anomaly in summary.anomalies:
        print(f"anomaly: {anomaly.kind} {anomaly.snapshot_id} {anomaly.detail}")
    for timeline in case_timeline(run):
        print(
            f"{timeline.case_id}: first_reported_in={timeline.first_reported_in} "
            f"alerted_at={', '.join(timeline.alerted_at) or '-'} resolved_in={timeline.resolved_in}"
        )
    if pending:
        print("pending notices: " + ", ".join(item.notice_id for item in pending))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
