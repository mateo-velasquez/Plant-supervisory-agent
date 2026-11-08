"""Run output read from a registry file, with the held-out refusal applied (Q-33, FR-40)."""

from pathlib import Path

from plant_monitor.cases.registry.notices import read_deliverables
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.domain.notices import Notice, ShiftReport
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.ingestion.errors import DataLoadError
from plant_monitor.ingestion.held_out import check_ids


def load_run_output(path: Path, policy: HeldOutPolicy) -> RunOutput:
    """read_deliverables, held-out refusal and split; ValueError from the reader becomes DataLoadError."""
    try:
        items = read_deliverables(path)
    except ValueError as error:
        raise DataLoadError(str(error)) from error
    shifts = tuple(i.turno_id for i in items if isinstance(i, ShiftReport))
    check_ids(policy, shifts=shifts, snapshots=(item.snapshot_id for item in items), where=str(path))
    alerts = tuple(item for item in items if isinstance(item, Notice))
    reports = tuple(item for item in items if isinstance(item, ShiftReport))
    return RunOutput(alerts=alerts, reports=reports)
