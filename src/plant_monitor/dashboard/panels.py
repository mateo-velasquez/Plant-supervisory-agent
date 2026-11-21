"""The fixed panels of the metrics window: the stored evaluation and the run reports (015 R11, R13)."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from plant_monitor.dashboard.heldout import json_shown
from plant_monitor.domain.calendar import HeldOutPolicy
from plant_monitor.evaluation.summary_file import EVAL_NAME, StoredSummary, read_summary
from plant_monitor.telemetry.run_report import REPORT_NAME, parse_report
from plant_monitor.telemetry.trace import ISO_Z_FORMAT, STAMP_FORMAT, TRACE_NAME, TraceMode


@dataclass(frozen=True)
class AccuracyPanel:
    """The latest stored evaluation of this registry, or why there is none (R11)."""

    state: Literal["ok", "none", "omitted"]
    file: str | None
    evaluated_at: str | None
    summary: StoredSummary | None
    earlier: int
    unreadable: int

    def __post_init__(self) -> None:
        if self.state == "ok" and self.summary is None:
            raise ValueError("an 'ok' accuracy panel needs a summary")


@dataclass(frozen=True)
class RunItem:
    """One run: a report, or a trace with no report ('running', no file)."""

    file: str | None
    mode: TraceMode
    status: Literal["ok", "aborted", "interrupted", "running"]
    started_at: str
    duration_seconds: float | None


@dataclass(frozen=True)
class RunsPanel:
    """The runs of 'runs_dir' by start time, with the unreadable and held-out-omitted counts (R13)."""

    items: tuple[RunItem, ...]
    unreadable: int
    omitted: int


@dataclass(frozen=True)
class _Named:
    """A listed file name with its raw stamp and the stamp as 'YYYY-MM-DDTHH:MM:SSZ'."""

    name: str
    stamp: str
    iso: str


def _names(directory: Path, pattern: re.Pattern[str]) -> tuple[list[_Named], int]:
    """Sorted matching names with a valid date stamp, and how many matched with an impossible date."""
    try:
        found = sorted(p.name for p in directory.iterdir() if pattern.fullmatch(p.name))
    except OSError:
        return [], 0
    named: list[_Named] = []
    bad = 0
    for name in found:
        match = pattern.fullmatch(name)
        if match is None:
            continue
        stamp = match["stamp"]
        try:
            iso = datetime.strptime(stamp, STAMP_FORMAT).strftime(ISO_Z_FORMAT)
        except ValueError:
            bad += 1
            continue
        named.append(_Named(name, stamp, iso))
    return named, bad


def _same_registry(stored: str, registry_path: Path) -> bool:
    try:
        return Path(stored).resolve() == registry_path.resolve()
    except OSError, ValueError:
        return False


def _decoded_shown(path: Path, policy: HeldOutPolicy) -> bool:
    """Whether the file's decoded JSON passes the held-out filter; undecodable counts as not shown."""
    try:
        return json_shown(json.loads(path.read_bytes()), policy)
    except OSError, ValueError:
        return False


def load_accuracy(evals_dir: Path, registry_path: Path, policy: HeldOutPolicy) -> AccuracyPanel:
    """The newest stored evaluation of 'registry_path', counting older matches and unreadable files (R11)."""
    listed, unreadable = _names(evals_dir, EVAL_NAME)
    matches: list[tuple[_Named, StoredSummary]] = []
    for entry in reversed(listed):
        try:
            stored = read_summary(evals_dir / entry.name)
        except ValueError:
            unreadable += 1
            continue
        if _same_registry(stored.registry, registry_path):
            matches.append((entry, stored))
    if not matches:
        return AccuracyPanel("none", None, None, None, 0, unreadable)
    entry, summary = matches[0]
    earlier = len(matches) - 1
    if not _decoded_shown(evals_dir / entry.name, policy):
        return AccuracyPanel("omitted", None, None, None, earlier, unreadable)
    return AccuracyPanel("ok", entry.name, entry.iso, summary, earlier, unreadable)


def load_runs(runs_dir: Path, traces_dir: Path, policy: HeldOutPolicy) -> RunsPanel:
    """Every run report by start time plus a 'running' item per trace without a report (R13)."""
    reports, unreadable = _names(runs_dir, REPORT_NAME)
    paired = {entry.stamp for entry in reports}
    items: list[RunItem] = []
    omitted = 0
    for entry in reports:
        try:
            data = (runs_dir / entry.name).read_bytes()
            report = parse_report(data, entry.name)
            shown = json_shown(json.loads(data), policy)
        except OSError, ValueError:
            unreadable += 1
            continue
        if not shown:
            omitted += 1
            continue
        items.append(
            RunItem(
                file=entry.name,
                mode=report.mode,
                status=report.status,
                started_at=report.started_at.astimezone(UTC).strftime(ISO_Z_FORMAT),
                duration_seconds=report.duration_seconds,
            )
        )
    traces, _ = _names(traces_dir, TRACE_NAME)
    for entry in traces:
        if entry.stamp not in paired:
            items.append(RunItem(None, "agent", "running", entry.iso, None))
    items.sort(key=lambda item: item.started_at)
    return RunsPanel(tuple(items), unreadable, omitted)
