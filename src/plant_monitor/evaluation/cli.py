"""Eval run core: load the inputs, score, print the table and write the summary (005, E37)."""

from datetime import datetime
from pathlib import Path
from typing import TextIO

from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.evaluation.golden import Capability, load_golden
from plant_monitor.evaluation.sources import load_run_output
from plant_monitor.evaluation.summary import evaluate, exit_code, render_table, write_summary
from plant_monitor.ingestion.logbooks import read_logbook_texts
from plant_monitor.ingestion.plant import load_shifts

EXIT_LOAD_ERROR = 2


def run_eval(
    *,
    registry: Path,
    golden_dir: Path,
    shifts_path: Path,
    logbooks_dir: Path,
    first_held_out_shift: str,
    held_out_open: bool,
    capabilities: frozenset[Capability],
    out_dir: Path,
    now: datetime,
    out: TextIO,
    err: TextIO,
) -> int:
    """Score 'registry' against 'golden_dir'; 0 or 1 after a summary, 2 on a load error with no summary."""
    try:
        shifts = load_shifts(shifts_path)
        policy = HeldOutPolicy.from_calendar(shifts, first_held_out_shift, held_out_open)
        run = load_run_output(registry, policy)
        golden = load_golden(
            golden_dir, shifts, policy, lambda turnos: read_logbook_texts(logbooks_dir, turnos, policy)
        )
    except (ValueError, OSError) as error:  # DataLoadError is a ValueError
        print(f"eval failed: {error}", file=err)
        return EXIT_LOAD_ERROR
    summary = evaluate(
        run,
        golden,
        shifts,
        capabilities=capabilities,
        registry=str(registry),
        golden_dir=str(golden_dir),
    )
    print(render_table(summary), file=out, end="")
    path = write_summary(summary, out_dir, now)
    print(f"summary: {path}", file=out)
    return exit_code(summary)
