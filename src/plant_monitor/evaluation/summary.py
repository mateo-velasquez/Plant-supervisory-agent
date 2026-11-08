"""Evaluation summary: gating errors, the metrics table, the JSON file and the exit code (005, Q-35)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from plant_monitor.domain.models import Shift
from plant_monitor.evaluation.golden import Capability, GoldenSet
from plant_monitor.evaluation.noise import NoiseScore, count_noise
from plant_monitor.evaluation.output import RunOutput
from plant_monitor.evaluation.results import ALERT_ERRORS, NEWS_ERRORS, Result, errors, tally
from plant_monitor.evaluation.scoring import score_alerts, score_news

_JSON_NAME = "eval-{stamp:%Y%m%dT%H%M%SZ}.json"
_JSON_INDENT = 2


@dataclass(frozen=True)
class EvalSummary:
    """Everything one evaluation produced: the inputs' names, the scored results and the noise."""

    registry: str
    golden: str
    capabilities: frozenset[Capability]
    covered_shifts: tuple[str, ...]
    alerts: tuple[Result, ...]
    news: tuple[Result, ...]
    noise: NoiseScore

    @property
    def gating_errors(self) -> int:
        """Gated alert errors, gated news errors and noise repeats; the number that fails the run."""
        return (
            errors(tally(self.alerts, gated=True), ALERT_ERRORS)
            + errors(tally(self.news, gated=True), NEWS_ERRORS)
            + self.noise.errors
        )

    def to_json(self) -> dict[str, object]:
        """The summary as plain JSON values: tallies per section, the facts behind them, and the exit code."""
        return {
            "registry": self.registry,
            "golden": self.golden,
            "capabilities": sorted(capability.value for capability in self.capabilities),
            "covered_shifts": list(self.covered_shifts),
            "alerts": _section_json(self.alerts),
            "news": _section_json(self.news),
            "noise": {
                "errors": self.noise.errors,
                "repeats": [
                    {"turno_id": r.turno_id, "case_id": r.case_id, "previous_turno_id": r.previous_turno_id}
                    for r in self.noise.repeats
                ],
                "duplicate_alerts": [
                    {"case_id": case_id, "alerts": count} for case_id, count in self.noise.duplicate_alerts
                ],
            },
            "gating_errors": self.gating_errors,
            "exit_code": exit_code(self),
        }


def evaluate(
    run: RunOutput,
    golden: GoldenSet,
    shifts: Sequence[Shift],
    *,
    capabilities: frozenset[Capability],
    registry: str,
    golden_dir: str,
) -> EvalSummary:
    """Score the run's alerts, news and noise against the golden set."""
    return EvalSummary(
        registry=registry,
        golden=golden_dir,
        capabilities=capabilities,
        covered_shifts=golden.covered_shifts,
        alerts=score_alerts(run, golden, shifts, capabilities),
        news=score_news(run, golden, capabilities),
        noise=count_noise(run),
    )


def exit_code(summary: EvalSummary) -> int:
    """0 when no gated error remains, else 1."""
    return 0 if summary.gating_errors == 0 else 1


def render_table(summary: EvalSummary) -> str:
    """Plain-text table: one row per section and per question, gated and not gated columns."""
    rows: list[tuple[str, str, str]] = [("section", "gated", "not gated")]
    for name, results in (("alerts", summary.alerts), ("news", summary.news)):
        rows.append((name, _line(tally(results, gated=True)), _line(tally(results, gated=False))))
        for question in _questions(results):
            rows.append(
                (
                    f"  {question}",
                    _line(tally(results, gated=True, question=question)),
                    _line(tally(results, gated=False, question=question)),
                )
            )
    rows.append(
        (
            "noise",
            f"repeats {summary.noise.errors}",
            f"duplicate alerts {len(summary.noise.duplicate_alerts)}",
        )
    )
    rows.append(("gating errors", str(summary.gating_errors), ""))
    widths = [max(len(row[column]) for row in rows) for column in range(3)]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip() for row in rows
    ]
    return "\n".join(lines) + "\n"


def write_summary(summary: EvalSummary, directory: Path, at: datetime) -> Path:
    """Write 'eval-<UTC stamp>.json' under 'directory' (created if missing); 'at' must be aware."""
    if at.utcoffset() is None:
        raise ValueError("the summary time must be timezone-aware")
    stamp = at.astimezone(UTC)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / _JSON_NAME.format(stamp=stamp)
    text = json.dumps(summary.to_json(), ensure_ascii=False, indent=_JSON_INDENT) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return path


def _section_json(results: tuple[Result, ...]) -> dict[str, object]:
    """Tallies of one section and the facts behind them."""
    return {
        "gated": tally(results, gated=True),
        "not_gated": tally(results, gated=False),
        "by_question": {question: tally(results, question=question) for question in _questions(results)},
        "results": [
            {
                "label": result.label,
                "case_id": result.case_id,
                "where": result.where,
                "contributions": dict(result.contributions),
                "gated": result.gated,
                "depends_on": list(result.depends_on),
                "ref": result.ref,
            }
            for result in results
        ],
    }


def _questions(results: Sequence[Result]) -> list[str]:
    """Every question named in a result's 'depends_on', sorted."""
    return sorted({question for result in results for question in result.depends_on})


def _line(counts: dict[str, int]) -> str:
    """'key n' pairs in key order, or '-' when empty."""
    return ", ".join(f"{key} {value}" for key, value in sorted(counts.items())) or "-"
