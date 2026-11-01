# Repository structure

Target layout. Modules are created when their spec is implemented; this file is updated in the same PR.

```
.
├── CLAUDE.md                 # rules for Claude Code
├── README.md                 # what it solves, how to run, design decisions (why)
├── pyproject.toml / uv.lock  # dependencies and tool config
├── .env.example              # configuration template
├── .pre-commit-config.yaml   # local hooks: ruff, mypy, gitleaks, uv lock, .env guard
├── .gitattributes            # LF line endings on every OS
├── .claude/                  # Claude Code config (ADR-0006)
│   ├── agents/               # spec-writer, test-writer, domain-implementer, reviewer, design-reviewer, eval-curator
│   ├── skills/               # new-spec, implement-spec, verify-criteria, new-adr, check, pr-handoff
│   ├── hooks/guard.py        # pre: guard rules · post: format edited .py
│   └── settings.json         # hook wiring + permission rules (settings.local.json is personal, ignored)
├── .github/
│   ├── workflows/ci.yml      # lint, format, types, tests + coverage (Ubuntu, Windows)
│   ├── workflows/secrets.yml # gitleaks over full history
│   ├── dependabot.yml        # weekly uv + GitHub Actions updates
│   └── pull_request_template.md
├── src/plant_monitor/
│   ├── config.py             # Settings (pydantic-settings)
│   ├── domain/               # pure types: Unit, Snapshot, Combination, Severity, CaseState, Cause, Notice, Report
│   ├── ingestion/            # loaders (CSV with BOM, JSON), schema validation, arrivals, content hash
│   ├── metrics/              # thresholds, lookup tables, progress, cumulative plan, gap, delay, bottleneck, min severity
│   ├── cases/                # lifecycle state machine, novelty rules, registry (repository over SQLite)
│   ├── logbooks/             # logbook store, availability by shift, verbatim citation check
│   ├── mcp_server/           # own MCP server: read tools, write tools, criteria prompt
│   ├── agents/               # agentic loop, agent roles + tool allowlists, factory, system prompts
│   ├── hooks/                # pre-tool, post-tool and on-stop guards
│   ├── notify/               # notifier port + adapters (console, file per shift)
│   ├── telemetry/            # token/cost accounting, trace log
│   └── runner/               # series runner (order, dedupe, anomaly checks, unit of work) and CLI entry point
├── tests/
│   ├── unit/                 # one module per domain rule; no I/O, no LLM
│   ├── integration/          # runner + registry + MCP with a fake model
│   ├── dev_hooks/            # tests for .claude/hooks/guard.py
│   ├── fixtures/             # small synthetic dataset (versioned)
│   └── builders.py           # shared snapshot builders (`from builders import ...`)
├── evals/
│   ├── golden/               # hand-verified expected notices per day (days 1–7)
│   └── run_eval.py           # notices, cause and noise metrics
├── specs/
│   ├── stories/              # user stories with Gherkin acceptance criteria
│   ├── _template/            # spec / plan / tasks templates
│   └── NNN-feature/          # one folder per feature (spec.md, plan.md, tasks.md)
├── docs/
│   ├── requirements.md       # FR / NFR with IDs
│   ├── roadmap.md            # specs in order, priorities, dates
│   ├── STRUCTURE.md          # this file
│   ├── adr/                  # architecture decision records
│   └── diagrams/             # Mermaid diagrams
├── data/                     # real data, NOT versioned (only README)
└── z_helps/                  # local support material, NOT versioned
```

## Implemented modules

| Module | Spec | Contents |
|---|---|---|
| `domain/enums.py` | 001, 002 | `Severity` (ordered), `Stage` (downstream `rank`), `Market`, `Model`, `PRODUCTION_STAGES`, `ShiftPosition`, `AnomalyKind` |
| `domain/models.py` | 001, 002 | Frozen input models, `Combination`, `CombinationMetrics`, `all_combinations()`, `Anomaly`, `SnapshotCommit` |
| `domain/calendar.py` | 002 | `snapshot_position` (shift row and `ShiftPosition`) |
| `ingestion/errors.py` | 001 | `DataLoadError` and validation-message formatting |
| `ingestion/plant.py` | 001 | `load_plan`, `load_standards`, `load_shipments`, `load_shifts` (BOM, row checks, plan completeness) |
| `ingestion/rows.py` | 002 | `read_rows`: shared CSV row reader (BOM, physical-line errors) |
| `ingestion/snapshot.py` | 001, 002 | `load_snapshot`, `parse_snapshot` (bytes, no filesystem) |
| `ingestion/hashing.py` | 002 | `content_hash`: lowercase hex SHA-256 of raw bytes |
| `ingestion/arrivals.py` | 002 | `Arrival`, `load_arrivals` (`llegadas.csv`, sorted by `orden`) |
| `runner/ports.py` | 002 | `ProcessedStore` (unit of work over a `SnapshotCommit`) and `SnapshotPipeline` protocols |
| `runner/memory_store.py` | 002 | `InMemoryProcessedStore` |
| `runner/checks.py` | 002 | Pure anomaly checks: shift mismatch, future stage entry, unit identity |
| `runner/series.py` | 002 | `RunSummary`, `RunAborted`, `run_series` (order, dedupe, checks, delegate) |
| `metrics/thresholds.py` | 001 | `Thresholds` and `load_thresholds` for `umbrales.yaml` |
| `metrics/tables.py` | 001 | `StandardsTable`, `ShipmentsTable` (bisect over cut-offs) |
| `metrics/progress.py` | 001, 002 | Distinct released units per combination; first release wins (Q-20) |
| `metrics/plan.py` | 001 | `cumulative_plan`, `gap_pct` |
| `metrics/delay.py` | 001, 002 | Projected yard arrival (elapsed clamped at 0, Q-19), reachable shipment, delay in days |
| `metrics/bottleneck.py` | 001 | Delayed units and bottleneck stage |
| `metrics/severity.py` | 001 | Gap, delay and minimum severity |
| `metrics/engine.py` | 001 | `PlantContext` and `compute_metrics` for one snapshot |

## Dependency rule
Dependencies point inward:

```
runner → agents → mcp_server → cases / metrics / logbooks → domain
                ↘ hooks ↗
notify, telemetry, ingestion → domain
```

- `domain` imports nothing from the project.
- `ingestion` imports only `domain`. `runner` may import `ingestion` and `metrics`; `runner/checks.py` imports only `domain`.
- `metrics` and `cases` never import `agents`, `mcp_server` or `anthropic`. The deterministic core is testable without the model.
- Only `agents` imports `anthropic`, and only `mcp_server` imports `mcp`.

## Design patterns

| Pattern | Where | Why |
|---|---|---|
| State | `cases/lifecycle.py` | Case transitions are explicit and testable per state. |
| Strategy | `metrics/severity.py` | Delay thresholds differ per market (Local has `media`; Brazil and Europe do not). |
| Repository | `cases/registry.py` | The registry is behind an interface, so SQLite can be swapped for in-memory in tests. |
| Pipeline | `runner/` | ingest → metrics → lifecycle → agent → notify, each step pure where possible. |
| Chain of Responsibility | `hooks/` | Guards run in order, and the first to block returns its reason. |
| Factory | `agents/factory.py` | Builds each agent with its prompt and its tool allowlist. |
| Ports and Adapters | `notify/` | The output channel is pluggable without touching the core. |

## Tests vs evals
- **Tests** (`tests/`) check code against rules and run in CI with no network.
- **Evals** (`evals/`) check system behavior, including the model, against golden cases. They run on demand and cost money.
