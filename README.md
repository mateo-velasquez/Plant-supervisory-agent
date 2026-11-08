# Plant supervisory agent

[![CI](https://github.com/mateo-velasquez/Plant-supervisory-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/mateo-velasquez/Plant-supervisory-agent/actions/workflows/ci.yml)
[![Secret scan](https://github.com/mateo-velasquez/Plant-supervisory-agent/actions/workflows/secrets.yml/badge.svg)](https://github.com/mateo-velasquez/Plant-supervisory-agent/actions/workflows/secrets.yml)

Agent-based production monitor for the (fictional) Las Acacias automotive plant, built as the final project of Taligent's Spring AI Camp.

It follows a 10-day series of plant snapshots and computes model × market deviations against the plan. Each deviation is tracked as a case, and the system decides what to notify and when:
- an **immediate alert** when a case becomes critical;
- an **end-of-shift report** with only what changed, each cause cited from the supervisors' logbooks.

The hard part is not spotting the delay. It is not repeating the same warning ten times, and not staying silent when things get worse.

## How it works
- **Code computes and enforces.** Gap, delay, bottleneck, minimum severity, case lifecycle and novelty rules are deterministic Python.
- **The model judges and writes.** Claude Haiku 5.5 reads logbooks, extracts the cause with a verbatim quote, decides when a logbook justifies escalation, and writes the notices.
- **Hooks keep them in agreement.** Any agent action that contradicts the code's computation is blocked and returned to the model as an error.
- **Each snapshot counts once.** A repeated arrival is skipped by content hash, a failed run resumes where it stopped, and data quirks are reported without stopping the series.

See [ADR-0002](docs/adr/0002-code-computes-model-judges.md) and the [diagrams](docs/diagrams/README.md).

## Design decisions
One line per decision and why; the full reasoning is in each record. Smaller rule interpretations are the Q rows in [requirements](docs/requirements.md#5-assumptions-and-open-questions).

| Decision | Why | Record |
|---|---|---|
| uv with a versioned lockfile | Reproducible on Windows and Linux with one-command runs | [ADR-0001](docs/adr/0001-use-uv.md) |
| Code computes and enforces; the model judges and writes | Thresholds must be deterministic; only the logbooks need judgment | [ADR-0002](docs/adr/0002-code-computes-model-judges.md) |
| Case registry in SQLite with a single writer | Registry outside the model, atomic per snapshot, resumable | [ADR-0003](docs/adr/0003-single-writer-sqlite-registry.md) |
| Real data not versioned; synthetic fixtures for tests | Course material stays out of git, and held-out days cannot leak into tuning | [ADR-0004](docs/adr/0004-data-not-versioned.md) |
| English code; Spanish data-contract values | Idiomatic code with output that matches the brief exactly | [ADR-0005](docs/adr/0005-english-code-spanish-data-contract.md) |
| Claude Code workflow with scoped subagents and guard hooks | Costly rules (held-out data, secrets, merges) enforced in code, not prose | [ADR-0006](docs/adr/0006-claude-code-dev-workflow.md) |
| Own agent loop on the Anthropic SDK with our MCP server (proposed) | Full control over hooks, allowlists and cost; testable with a fake model | [ADR-0007](docs/adr/0007-own-agent-loop-with-mcp-client.md) |
| Content-hash idempotency, unit of work, non-fatal anomalies | The series runs unattended and the held-out days run once, so a quirk must not stop it | [ADR-0008](docs/adr/0008-series-runner-resilience.md) |
| Coordinator loop: template fallback, notice draft, budget guard, `anyio.run` bridge | A model failure never loses notices or stops the unattended series, and no request crosses the 5× price line | [ADR-0014](docs/adr/0014-coordinator-loop-contract.md) |
| Lean spec workflow: anchored reading, size budget, delta re-review, test budget | Cold subagents re-read large specs and tests outgrew the code (98.7% coverage) | [ADR-0012](docs/adr/0012-lean-spec-workflow.md) |

## Getting started
Requirements: [uv](https://docs.astral.sh/uv/) ≥ 0.13. Python 3.14 is selected automatically from `.python-version`.

```powershell
uv sync                          # create the environment
uv run pre-commit install        # enable git hooks
Copy-Item .env.example .env      # then set ANTHROPIC_API_KEY
```
Place the course dataset in `data/` (see [data/README.md](data/README.md)).

## Development
```powershell
uv run pytest --cov              # tests + coverage (min 80%)
uv run ruff check . ; uv run ruff format .
uv run mypy src tests evals
uv run pre-commit run --all-files
```
CI runs the same checks on Ubuntu and Windows for every PR. CI never calls the model.

## How to run evals
Evals run on demand over the real data of days 1–7 ([ADR-0011](docs/adr/0011-evaluator-reads-outbox-independent-noise.md)). Both scripts read `Settings`, so `ANTHROPIC_API_KEY` must be set (any value works while the run is threshold-only).

```powershell
# 1. Threshold-only run of days 1–7: writes outputs/evals/smoke-<timestamp>/registry.sqlite3
uv run python evals/smoke_days_1_7.py

# 2. Score a run's registry against the golden cases in evals/golden/
uv run python evals/run_eval.py --registry outputs/evals/smoke-<timestamp>/registry.sqlite3 --golden evals/golden
uv run python evals/run_eval.py --registry <run>/registry.sqlite3 --golden evals/golden --capabilities agent
```

- `--capabilities` (repeatable or comma-separated, default none) names what the run can do. Golden items marked `requires: [agent]` are always scored, but they only decide the result when the run has that capability.
- The eval prints a table (alerts, news, noise, gated errors per section and per open question) and writes `outputs/evals/eval-<timestamp>.json`.
- Exit codes: `0` no gated errors, `1` gated errors (the smoke run also exits `1` if notices are left pending), `2` load or settings error.
- Held-out days: `HELDOUT_OPEN` (default `false`) and `HELDOUT_FIRST_SHIFT` (default `T22`) are the product guard; the evaluator and the smoke run refuse T22–T30 and S043–S060 while it is closed. `CLAUDE_ALLOW_HELDOUT=1` is a different switch: it only opens the Claude Code guard hook. Both stay closed until the held-out run (week 5).

## Documentation
| | |
|---|---|
| [Requirements](docs/requirements.md) | Functional and non-functional requirements, open questions |
| [Roadmap](docs/roadmap.md) | Specs in order, priorities, dates and known data findings |
| [User stories](specs/stories/README.md) | Stories with Gherkin acceptance criteria |
| [Specs](specs/) | Spec Driven Development: one folder per feature |
| [Structure](docs/STRUCTURE.md) | Module layout, dependency rule, design patterns |
| [ADRs](docs/adr/README.md) | Design decisions and their rationale |
| [Diagrams](docs/diagrams/README.md) | Context, components, sequences, state machine |

## License
See [LICENSE](LICENSE).
