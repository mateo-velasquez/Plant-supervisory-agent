---
name: check
description: Run every quality check that CI runs, on the whole repository, and report results. Use before declaring any task done and before handing a branch over.
allowed-tools: Bash(uv *) PowerShell(uv *) Bash(git status*) PowerShell(git status*)
---

Run, in this order, from the repository root, and do not stop at the first failure:

1. `uv lock --check`
2. `uv run ruff check .`
3. `uv run ruff format --check .` (the **whole repo**, not only changed `.py` files; this is what CI runs)
4. `uv run mypy src tests`
5. `uv run pytest --cov`
6. `uv run pre-commit run --all-files`
7. `git status --short`: hooks may have fixed files (line endings, whitespace); list them.

Report a table with these columns: check | result | key output (first error lines, coverage %). If something failed, say whether it is fixable automatically (e.g. `ruff format .`) and propose the fix, but do not apply fixes unless asked.
