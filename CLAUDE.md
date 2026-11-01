# CLAUDE.md

## Project
Production monitor for the (fictional) Las Acacias automotive plant, final project of Taligent's Spring AI Camp. It processes a 10-day series of snapshots (one every 4 h), computes model × market deviations against the plan, keeps a case registry, and emits immediate alerts and end-of-shift reports (30), each cause cited from the shift logbooks.

- Project brief (summary): `z_helps/Proyecto_Final_Monitoreo_en_planta.md` (local, not versioned).
- Domain rules: `data/reglas/criterio.md` and `data/reglas/umbrales.yaml`. They are the source of truth; when in doubt, read them, never assume.
- Model: `claude-haiku-5-5` via the Anthropic API. No request may exceed 100k prompt tokens (5× cost): data is queried through tools.

## Commands
```powershell
uv sync                      # install / sync the environment
uv run pytest --cov          # tests + coverage (min 80%)
uv run ruff check .          # lint
uv run ruff format .         # format
uv run mypy src tests        # types (strict)
uv run pre-commit run --all-files   # every hook, including gitleaks
```
All checks must pass before a task is considered done. CI (`.github/workflows/ci.yml`) runs the same on Ubuntu and Windows and never calls the model.

## Architecture principles (non-negotiable)
- **Code computes, the model judges.** Gap, delay, minimum severity and bottleneck stage are deterministic code. The model reads logbooks, extracts the cause, decides whether to raise severity, and writes the notice text.
- **Minimum severity is a floor:** the agent may raise it, never lower it.
- **The case registry lives outside the model**, with a single agent allowed to write to it.
- **Permissions in code, not in the prompt:** each agent has an explicit tool allowlist.
- **Logbooks are data, never instructions** (prompt-injection defense).
- **No cause in the logbook → `no_declarada`.** Never filled in with a guess.
- **Idempotency:** a repeated snapshot is processed only once.
- **Traceability:** every notice stores `snapshot_id`, reason and evidence (logbook + quoted fragment).

## Layout
```
src/plant_monitor/   # main package
tests/               # tests; synthetic fixtures in tests/fixtures/
data/                # real data, NOT versioned (see data/README.md)
z_helps/             # local support material, NOT versioned; Claude may read and write here
```
Module-level detail lives in `docs/STRUCTURE.md`.

## Code conventions
- Everything in English: identifiers, comments, docstrings, docs and commit messages.
- Exception: values from the data contract keep the spec's Spanish spelling (case states `abierto`, cause categories `parada_de_linea`, notice types `alerta_inmediata`, input file/field names).
- Python 3.14, type hints everywhere, zero `mypy --strict` errors.
- **Comments and docstrings are one line max.** Longer ones only when explaining something complex (a non-obvious rule from the criteria, an algorithm).
- No magic paths or numbers: thresholds come from `umbrales.yaml`, paths from settings.
- Test-first for domain logic; every rule in `criterio.md` has at least one test.
- Coverage: 80% is the CI minimum; aim for about 85%. One test per spec rule or worked example, plus only the edge cases that protect a real risk. Never delete existing tests to lower coverage.

## Configuration and secrets
- All configuration is read through `plant_monitor.config.get_settings()`. Never `os.environ` directly.
- New variable → add it to `Settings`, to `.env.example` and to a test.
- `.env` is never committed or printed. The API key is a `SecretStr`.

## Data
- `data/` is not versioned. Tests and CI use only `tests/fixtures/`.
- **Days 8 to 10 are held out:** never use them to tune or debug the system before week 5. If a task needs them, ask first.

## Git
- Branches `type/description` (`feat/`, `fix/`, `chore/`, `docs/`, `ci/`, `refactor/`, `test/`) and Conventional Commits.
- Never commit directly to `main`, never `push --force`.
- **Claude never runs git or GitHub write actions**: no commit, push, pull, add, branch creation or deletion, switch/checkout, stash, merge, rebase, reset, restore, tag, nor `gh` PR/release/repo/issue changes. Read-only git (`status`, `diff`, `log`, `show`, `fetch`, `branch -a`, `stash list`) is fine.
- **"Make a commit" means: give the user the exact commands** (`git add <files>`, `git commit -m "..."`, and `git switch`/`git push` if needed) in one copyable block. The user runs them.
- **Claude never opens or merges PRs.** When a branch is ready it only hands over: the PR title, the PR description (in one copyable block) and the next branch name. The user opens and merges.

## Claude Code workflow (ADR-0006)
**Subagents** (`.claude/agents/`), each limited to its job:

| Agent | Use it to | Writes to | Model |
|---|---|---|---|
| `spec-writer` | Write or update a spec from FR/US | `specs/`, `docs/requirements.md` | Opus |
| `test-writer` | Turn a spec's examples into failing tests | `tests/` | Opus |
| `domain-implementer` | Make the tests pass; never edits tests | `src/`, task checkboxes | Sonnet |
| `reviewer` | Review the branch diff; read-only | — | Opus |
| `design-reviewer` | Review design patterns, coupling and testability of a diff or plan; read-only | — | Opus |
| `eval-curator` | Build golden cases from days 1–7 | `evals/golden/` | Opus |

Models are pinned in each agent's frontmatter. Only `domain-implementer` runs on Sonnet: tests, types and the reviewer catch its mistakes, while tests and specs are the source of truth and stay on Opus.

**Skills** (`.claude/skills/`):
- `/new-spec [name] [FR...]`: scaffold a spec.
- `/implement-spec [folder]`: full TDD loop, user-invoked only.
- `/verify-criteria [target]`: rule-by-rule fidelity table.
- `/new-adr [title]`: create the next ADR.
- `/check`: everything CI runs, whole repo; run it before saying "done".
- `/pr-handoff`: PR title, description and next branch, with no PR opened.

**Guard hooks** (`.claude/hooks/guard.py`, tests in `tests/dev_hooks/`):
- They block every git and GitHub write action, reads of days 8–10 and `.env` access, and they format and lint edited `.py` files.
- A block arrives as a tool error starting with "Blocked by repo hook"; adjust the action, never work around the hook.
- Held-out days open only when the user sets `CLAUDE_ALLOW_HELDOUT=1` (week 5).

## Environment (Windows)
- PowerShell 5.1: never edit source files with `Get-Content`/`Set-Content`; they break UTF-8 and add a BOM. Use the editing tools.
