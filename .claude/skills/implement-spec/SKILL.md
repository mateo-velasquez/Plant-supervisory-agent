---
name: implement-spec
description: Implement a Ready spec end to end with TDD by chaining the test-writer, domain-implementer and reviewer subagents. Use when a spec's status is Ready.
argument-hint: "[specs/NNN-feature]"
disable-model-invocation: true
---

Implement the spec at: $ARGUMENTS

1. **Preconditions.** Read `spec.md` and confirm `Status: Ready`; otherwise stop and say what is missing. Confirm the current branch is not `main` and is named `feat/...`.
2. **Per task in `tasks.md`, in order** (group consecutive tasks that touch the same module):
   1. Delegate to `test-writer`: write the failing tests for those tasks. Check its report: tests must fail for the right reason.
   2. Delegate to `domain-implementer`: make them pass, tick the tasks.
   3. If either reports a spec ambiguity, stop and ask the user; do not let a subagent decide a domain rule.
3. **Review.** Delegate to `reviewer`. If the verdict is "changes needed", send the findings to `domain-implementer` (or `test-writer` for test issues) and review again, at most twice; then report remaining findings to the user.
4. **Close.** Run the `check` skill. If everything passes, set `spec.md` to `Status: Implemented`.
5. **Hand over.** Give the `git add` / `git commit` commands grouped by task, with Conventional Commit messages, for the user to run (never run them), then summarize tasks done, coverage and open questions.
