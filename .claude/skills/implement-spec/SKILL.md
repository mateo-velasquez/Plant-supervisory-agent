---
name: implement-spec
description: Implement a Ready spec end to end with TDD by chaining the test-writer, domain-implementer and reviewer subagents. Use when a spec's status is Ready.
argument-hint: "[specs/NNN-feature]"
disable-model-invocation: true
---

Implement the spec at: $ARGUMENTS

1. **Preconditions.** Read only the header of `spec.md` (first ~10 lines) and confirm `Status: Ready`; otherwise stop and say what is missing. Read `tasks.md` whole. Confirm the current branch is not `main` and is named `feat/...`.
2. **Per task in `tasks.md`, in order** (group consecutive tasks that touch the same module):
   1. Delegate to `test-writer`. Brief it with the spec folder, the task IDs and their anchors copied from `tasks.md` (`R`, `E`, `X` ids and plan sections), so it reads only those. Check its report: tests must fail for the right reason, and every test must name the ID it covers.
   2. Delegate to `domain-implementer` with the same anchors: make them pass, tick the tasks.
   3. If either reports a spec ambiguity, stop and ask the user; do not let a subagent decide a domain rule.
   4. **Test size check.** Run `uv run pytest --cov=<new modules> --cov-report=term-missing <new test files>`. If a new module is above ~90% and the report lists tests without a spec ID, send `test-writer` back to remove those extras from the tests it just wrote (never older tests).
3. **Review.**
   1. First round: delegate to `reviewer` for a full review of the branch.
   2. If the verdict is "changes needed", send the findings to `domain-implementer` (or `test-writer` for test issues).
   3. Re-review (at most twice): delegate to `reviewer` in **re-review mode**, passing the previous findings and the files the fix changed (from the fixer's report). It checks only those findings and those files.
   4. After two re-reviews, report the remaining findings to the user.
4. **Close.** Run the `check` skill (whole repo, so it also catches regressions outside the re-reviewed files). If everything passes, set `spec.md` to `Status: Implemented`.
5. **Hand over.** Give the `git add` / `git commit` commands grouped by task, with Conventional Commit messages, for the user to run (never run them), then summarize tasks done, coverage and open questions.
