"""Eval CLI: scores a registry run against the golden set (005, E37); paths and policy come from settings."""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from plant_monitor.config import get_settings
from plant_monitor.evaluation.cli import run_eval
from plant_monitor.evaluation.golden import Capability

_SHIFTS_FILE = "turnos.csv"


def _capability_list(value: str) -> list[Capability]:
    """Capabilities of one comma-separated list; an unknown name is an argument error."""
    try:
        return [Capability(part.strip()) for part in value.split(",") if part.strip()]
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"unknown capability: {error}") from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score a registry run against the golden set.")
    parser.add_argument("--registry", type=Path, required=True, help="registry SQLite file of the run")
    parser.add_argument("--golden", type=Path, required=True, help="directory of golden .yaml files")
    parser.add_argument(
        "--capabilities",
        action="append",
        type=_capability_list,
        default=[],
        metavar="CAP[,CAP...]",
        help="capabilities the run has (repeatable or comma-separated; default none)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the evaluation and return its exit code (0, 1 or 2)."""
    args = _parser().parse_args(argv)
    settings = get_settings()
    capabilities: frozenset[Capability] = frozenset(
        capability for group in args.capabilities for capability in group
    )
    return run_eval(
        registry=args.registry,
        golden_dir=args.golden,
        shifts_path=settings.plant_dir / _SHIFTS_FILE,
        logbooks_dir=settings.logbooks_dir,
        first_held_out_shift=settings.heldout_first_shift,
        held_out_open=settings.heldout_open,
        capabilities=capabilities,
        out_dir=settings.evals_dir,
        now=datetime.now(UTC),
        out=sys.stdout,
        err=sys.stderr,
    )


if __name__ == "__main__":
    sys.exit(main())
