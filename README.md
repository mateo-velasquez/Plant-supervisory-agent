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

See [ADR-0002](docs/adr/0002-code-computes-model-judges.md) and the [diagrams](docs/diagrams/README.md).

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
uv run mypy src tests
uv run pre-commit run --all-files
```
CI runs the same checks on Ubuntu and Windows for every PR. CI never calls the model.

## Documentation
| | |
|---|---|
| [Requirements](docs/requirements.md) | Functional and non-functional requirements, open questions |
| [User stories](specs/stories/README.md) | Stories with Gherkin acceptance criteria |
| [Specs](specs/) | Spec Driven Development: one folder per feature |
| [Structure](docs/STRUCTURE.md) | Module layout, dependency rule, design patterns |
| [ADRs](docs/adr/README.md) | Design decisions and their rationale |
| [Diagrams](docs/diagrams/README.md) | Context, components, sequences, state machine |

## License
See [LICENSE](LICENSE).
