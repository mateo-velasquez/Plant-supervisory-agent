# Repository structure

Target layout. Modules are created when their spec is implemented; this file is updated in the same PR.

```
.
├── CLAUDE.md                 # rules for Claude Code
├── README.md                 # what it solves, how to run, design decisions (why)
├── pyproject.toml / uv.lock  # dependencies and tool config
├── .env.example              # configuration template
├── src/plant_monitor/
│   ├── config.py             # Settings (pydantic-settings)
│   ├── domain/               # pure types: Unit, Snapshot, Combination, Severity, CaseState, Cause, Notice, Report
│   ├── ingestion/            # loaders (CSV with BOM, JSON), schema validation, arrival order + dedupe
│   ├── metrics/              # progress, cumulative plan, gap, projected arrival, delay, bottleneck, min severity
│   ├── cases/                # lifecycle state machine, novelty rules, registry (repository over SQLite)
│   ├── logbooks/             # logbook store, availability by shift, verbatim citation check
│   ├── mcp_server/           # own MCP server: read tools, write tools, criteria prompt
│   ├── agents/               # agentic loop, agent roles + tool allowlists, factory, system prompts
│   ├── hooks/                # pre-tool, post-tool and on-stop guards
│   ├── notify/               # notifier port + adapters (console, file per shift)
│   ├── telemetry/            # token/cost accounting, trace log
│   └── runner/               # series runner and CLI entry point
├── tests/
│   ├── unit/                 # one module per domain rule; no I/O, no LLM
│   ├── integration/          # runner + registry + MCP with a fake model
│   └── fixtures/             # small synthetic dataset (versioned)
├── evals/
│   ├── golden/               # hand-verified expected notices per day (days 1–7)
│   └── run_eval.py           # notices, cause and noise metrics
├── specs/
│   ├── stories/              # user stories with Gherkin acceptance criteria
│   ├── _template/            # spec / plan / tasks templates
│   └── NNN-feature/          # one folder per feature (spec.md, plan.md, tasks.md)
├── docs/
│   ├── requirements.md       # FR / NFR with IDs
│   ├── STRUCTURE.md          # this file
│   ├── adr/                  # architecture decision records
│   └── diagrams/             # Mermaid diagrams
├── data/                     # real data, NOT versioned (only README)
└── z_helps/                  # local support material, NOT versioned
```

## Dependency rule
Dependencies point inward:

```
runner → agents → mcp_server → cases / metrics / logbooks → domain
                ↘ hooks ↗
notify, telemetry, ingestion → domain
```

- `domain` imports nothing from the project.
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
