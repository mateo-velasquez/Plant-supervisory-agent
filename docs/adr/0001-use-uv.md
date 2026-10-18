# 0001 · Use uv for environment and dependencies

- **Status:** Accepted
- **Date:** 2026-10-18
- **Requirements:** NFR-05, NFR-11

## Context
We need a reproducible environment on Windows (development) and Linux (CI), with a lockfile, dev-only dependencies and one-command runs usable from hooks and agents.

## Decision
Use **uv** with standard `pyproject.toml` (PEP 621), dependency groups (PEP 735), a versioned `uv.lock`, Python pinned to `3.14` in `.python-version`, and `required-version` for uv itself.

## Alternatives considered
- **venv + pip:** no real lockfile or dev groups; reproducibility is manual.
- **pipenv:** slow, declining adoption, does not use `pyproject.toml` as source.
- **Poetry:** solid, but slower, does not manage Python versions, and lagged on PEP 751 lockfile export.
- **conda:** oversized for a project without heavy native libraries; complicates CI.

## Consequences
- Positive: fast installs, `uv sync --frozen` in CI, `uv run` without activating environments.
- Risk: Astral was acquired by OpenAI (March 2026) without formal governance guarantees. Mitigated because we only use standard formats (PEP 621/735, exportable to PEP 751), so migrating to PDM is cheap.
- Follow-up: pin uv in CI with `astral-sh/setup-uv`.
