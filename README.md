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
Copy-Item .env.example .env      # then set ANTHROPIC_API_KEY (agent mode only)
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

## How to run
One command runs the series ([ADR-0018](docs/adr/0018-full-series-cli-resume-by-output-dir-run-summary.md)):

```powershell
uv run plant-monitor run                                 # agent mode (needs ANTHROPIC_API_KEY)
uv run plant-monitor run --thresholds-only               # code only, no model, no key
uv run plant-monitor run --until S020                    # stop after the first arrival of S020
uv run plant-monitor run --speed 5                       # pause 5 s after each committed snapshot (live demo)
```

- **One directory, one run.** `OUTPUT_DIR` (default `outputs`) holds the registry, the traces, the notices and the summaries. Running again with the same directory resumes at the first snapshot not yet committed. For a fresh run, use a new `OUTPUT_DIR`.
- **Do not mix modes in one directory.** A threshold-only run followed by an agent run in the same directory skips every snapshot already processed, and the summary shows 0 processed. The opposite order is refused: a directory that holds agent traces must resume in agent mode, because threshold-only mode would drop the agent's severity raises in force.
- **Held-out days** are read only with `HELDOUT_OPEN=true`. While it is closed, the run stops at the last allowed snapshot (S042), and `--until` cannot reach past it.
- **Summary.** The summary is printed and written to `OUTPUT_DIR/runs/run-<timestamp>.json`. It has two scopes:
  - *run*: this invocation's arrivals, duration, tokens (input, output, cache), USD, and the steps that hit the prompt budget;
  - *series*: every trace in the directory, aborted attempts included, plus the shift reports and alerts in the registry.
- **Exit codes:** `0` the run finished; `2` settings, data or option error, or a run aborted at a snapshot (rerun to resume); `130` interrupted with Ctrl-C.

## How to trace a notice
Any per-case notice (alert, news item or `sin_aviso`) can be traced back to its evidence ([ADR-0019](docs/adr/0019-read-only-notice-trace-registry-mode-ro-json-lines.md)):

```powershell
uv run plant-monitor trace S015-alerta_inmediata-S015-SUV-Europa
```

- **What it shows:** the metrics at the notice's snapshot (gap, delay, minimum and effective severity, bottleneck), the state transition, `motivo` and `origen`, the cause and its logbook quotes, the severity raise and the proposal that opened it, the agents' tool calls and hook blocks, and the snapshot's stored tokens and USD. Aborted attempts of a resumed run are listed. A threshold-only run says that no agent was involved.
- **Read-only:** it reads `OUTPUT_DIR`'s registry (`mode=ro`) and trace files. It never calls the model, needs no API key and writes nothing.
- **Logbook text is data:** quotes are printed verbatim, with control characters escaped.
- **Held-out days:** with `HELDOUT_OPEN=false`, a notice of a held-out snapshot is refused.
- **Exit codes:** `0` shown; `1` unknown `notice_id` (a report id lists its news ids); `2` settings error, missing or unreadable registry, held-out refusal, or unreadable or duplicated trace lines.

## How to render the HTML reports
The stored shift reports and alerts can be rendered as static pages after a run ([ADR-0021](docs/adr/0021-post-run-read-only-html-reports.md)):

```powershell
uv run plant-monitor html
```

- **Output:** `OUTPUT_DIR/html/` with `index.html` (a timeline of reports and alerts in registry order), one `<turno_id>-informe.html` per shift report and one `<notice_id>.html` per alert. Open `index.html` in a browser.
- **Each report page** shows the news first (severity, peak, cause, logbook quotes, the `plant-monitor trace` command), then the active-cases table. A shift with no news says "Sin novedades en este turno".
- **Read-only:** it reads the registry (`mode=ro`), never calls the model and needs no API key. Every page is rendered before the first one is written, so an error writes nothing. Pages are overwritten on each render; stale pages are never deleted.
- **Logbook text is data:** every value is escaped; pages carry a Content-Security-Policy, embedded CSS, no JavaScript and no network access.
- **Held-out days:** with `HELDOUT_OPEN=false`, items of held-out shifts or snapshots are left out, and stderr says `html: <k> held-out or unverifiable items omitted (HELDOUT_OPEN=false)`.
- **Exit codes:** `0` rendered (an empty registry gives only the index); `2` settings error, missing or unreadable registry, or an id outside its pattern.

## How to run evals
Evals run on demand over the real data of days 1–7 ([ADR-0011](docs/adr/0011-evaluator-reads-outbox-independent-noise.md)). The threshold-only smoke run needs no `ANTHROPIC_API_KEY`; the paid agent run of days 1–7 does.

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
