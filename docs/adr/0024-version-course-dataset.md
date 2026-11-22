# 0024 · Version the course dataset in `data/`

- **Status:** Accepted
- **Date:** 2026-11-22
- **Requirements:** NFR-07, FR-40
- **Supersedes:** [ADR-0004](0004-data-not-versioned.md)

## Context
ADR-0004 kept `data/` out of git because the dataset was third-party course material. Taligent has since allowed it to be published. Without the data, nobody who clones the repository can run the series, the dashboard or the evals; the project can only be shown through recordings. The dataset is small (98 text files: JSON snapshots, CSV plans, logbooks and the rules).

## Decision
`data/` is versioned in full. Tests and CI keep using only the synthetic fixtures in `tests/fixtures/`, and `DATA_DIR` still points elsewhere when needed. Days 8–10 stay held out by the same two guards as before: the product guard (`HELDOUT_OPEN`, default `false`) and the Claude Code guard hook (`CLAUDE_ALLOW_HELDOUT`).

The files are stored byte for byte (`-text` in `.gitattributes`, excluded from the pre-commit fixers). Snapshot idempotency hashes the raw bytes, and logbook quotes are matched verbatim, so normalizing CRLF to LF would change both.

## Alternatives considered
- **Keep ADR-0004:** the repository stays unrunnable for anyone outside the course.
- **Publish the data as a GitHub Release asset or a separate download:** one more setup step for a 98-file dataset, with no gain in size or safety.
- **Version only days 1–7:** the full series and the held-out run could not be reproduced.

## Consequences
- Positive: one clone and `uv sync` are enough to run every command in the README; the evals and the demo are reproducible.
- Negative / risks: days 8–10 are now readable by anyone with the repository. The held-out discipline relies on the two guards and on not tuning after the held-out run, not on the files being absent.
- Unchanged: CI never reads `data/`; fixtures stay the test source, so a data change cannot break CI.
