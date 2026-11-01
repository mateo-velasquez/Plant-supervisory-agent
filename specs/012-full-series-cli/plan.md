# 012 · Full-series CLI — Plan

## Modules

| File | Responsibility |
|---|---|
| `runner/cli.py` | Entry point (`plant-monitor run`), options, wiring of every component. |
| `runner/summary.py` | Final summary: arrivals, reports, alerts, tokens, USD, duration. |
| `pyproject.toml` | `[project.scripts]` entry. |

## Types and interfaces
To be fixed when the spec moves to Ready.

## Design notes
- `cli.py` is the composition root: the only place that builds concrete adapters (SQLite, Anthropic, MCP transport, notifiers).
- Standard library `argparse`, so no new dependency.

## Test strategy
CLI tests with `FakeModel` on a synthetic series (threshold-only and agent modes); a resume test; a recorded real run.

## Risks
A long real run that fails late is costly: resume (spec 002/003) makes it restartable.
