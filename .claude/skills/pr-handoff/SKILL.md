---
name: pr-handoff
description: Hand a finished branch over to the user for a PR, giving only the PR title, the PR description in one copyable block and the next branch name. Use when a branch is pushed and ready; Claude never opens or merges PRs.
allowed-tools: Bash(git *) PowerShell(git *)
---

Claude never runs `gh pr create`, `gh pr merge` or `git merge`. This skill only produces text.

1. Gather context: `git branch --show-current`, `git log --oneline main..HEAD`, `git diff --stat main...HEAD` and `git status -sb`. If the branch is not pushed or has uncommitted changes, say so first and give the push command.
2. If the `check` skill has not passed in this session for the current state, run it; report failures instead of handing over.
3. Output exactly three items, in Spanish framing with English content:

   **1. PR title:** a Conventional Commit style title (`type: summary`), max ~70 characters, in its own code block.

   **2. PR description:** in ONE code block fenced with **four backticks** (````markdown … ````) so inner code blocks do not break it. Sections:
   - `## Summary`: one or two sentences.
   - `## Changes`: bullets grouped by area.
   - `## Traceability`: spec, FR/NFR, US and ADR touched, when any.
   - `## How to test`: commands, plus the local check results.
   - `## Notes` (optional): review focus, follow-ups, merge advice.
   - The last line is: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`

   **3. Next branch:** `type/description`, chosen from the plan: the next Ready or Draft spec (`feat/NNN-feature`), or the pending infrastructure step. Add one line on what it will contain.

4. Start the message with one line naming the audience ("Escrito para: quien revise el PR en GitHub.").
