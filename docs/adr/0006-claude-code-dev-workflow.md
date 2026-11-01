# 0006 · Claude Code development workflow: scoped subagents, skills and guard hooks

- **Status:** Accepted
- **Date:** 2026-10-18
- **Requirements:** FR-40, NFR-06, NFR-07, NFR-08

## Context
Most of the code will be written with Claude Code. Rules that live only in prose (`CLAUDE.md`, agent prompts) are followed most of the time, but nothing enforces them. Some rules are costly to break:
- reading held-out days 8–10 invalidates the week-5 generalization test;
- reading `.env` leaks a paid API key;
- merging or opening PRs takes the user's decision away.

We also want Spec Driven Development to be repeatable, not improvised per session.

## Decision
- **Subagents** (`.claude/agents/`) with one job each and the minimum tools for it:
  - `spec-writer` has no shell;
  - `test-writer` writes tests only;
  - `domain-implementer` never edits tests to make them pass;
  - `reviewer` is read-only;
  - `eval-curator` builds golden cases from days 1–7 only.
  None can spawn other agents; the main conversation orchestrates.
- **Skills** (`.claude/skills/`) encode the workflow: `new-spec`, `implement-spec` (user-invoked only), `verify-criteria`, `new-adr`, `check` and `pr-handoff`.
- **Guard hooks** (`.claude/hooks/guard.py`, wired in `.claude/settings.json`) enforce the costly rules in code:
  - `pre` blocks every git and GitHub write action (commit, push, branch, switch, stash, merge, PRs…), held-out data and `.env` access; the user runs those commands;
  - `post` formats and lints edited Python files.
  Native permission rules deny `.env` as a second layer.

## Alternatives considered
- **Prose rules only:** cheapest, but a single slip on held-out data is irreversible.
- **One general agent for everything:** simpler, but nothing stops it from weakening a test to make code pass, and reviews would not be independent.
- **Shell-script hooks:** fewer files, but Bash and PowerShell differ on Windows; a stdlib Python script is portable and unit-tested.

## Consequences
- Positive: the costly rules are enforced and tested (`tests/dev_hooks/`), the TDD flow is repeatable with `/implement-spec`, and this is a working rehearsal for the product hooks of W4 (FR-31).
- Negative: occasional false positives. For example, a commit message containing "git merge" is blocked; the fix is to rephrase.
- The guard fails open (exit 1) so a broken hook cannot freeze a session; `.env` stays covered by permissions.
- Held-out days are opened in W5 only by setting `CLAUDE_ALLOW_HELDOUT=1` explicitly.
- Hooks constrain Claude only. Running the system itself (the future series runner) reads the full series, which is intended: running is not tuning.
