# 003 · Case registry and lifecycle — Tasks

Ordered, test-first. Each task is small enough for one commit.

- [ ] T1 · `CaseState`, `Case` and `CaseHistoryRow` in `domain/cases.py` with validation tests.
- [ ] T2 · Lifecycle test: a deviation with no active case opens a case in `abierto` → `cases/lifecycle.py`.
- [ ] T3 · Test: the next snapshot with a deviation moves it to `en_seguimiento`.
- [ ] T4 · Test: a second deviation for the same combination never opens a second case.
- [ ] T5 · Test: effective severity = max(minimum, raise in force) and never below the minimum (FR-15).
- [ ] T6 · Test: reaching `critica` sets `escalado`; Q-08 (opens already critical) opens and escalates in the same snapshot.
- [ ] T7 · Test: `escalado` stays when severity drops to `alta`.
- [ ] T8 · Test: resolution after `snapshots_sin_desvio` clean snapshots (read from `umbrales.yaml`); a deviation in between resets the streak.
- [ ] T9 · Test: a raise in force blocks resolution even with clean snapshots.
- [ ] T10 · Test: after resolution, a new deviation opens a new case with a new ID.
- [ ] T11 · Test: max severity since the last report tracks peaks, and `mark_reported` resets it and stores the last reported state and severity.
- [ ] T12 · `Registry` protocol plus `InMemoryRegistry`, with repository contract tests.
- [ ] T13 · `SqliteRegistry` with `schema.sql`, passing the same contract tests on `:memory:`.
- [ ] T14 · Test: `unit_of_work` commits case writes and `mark_processed` together, and rolls both back on failure.
- [ ] T15 · `SqliteRegistry` implements spec 002's `ProcessedStore` (hash included); runner test with the SQLite store.
- [ ] T16 · Released units persisted and deduplicated; feeds `compute_metrics` from spec 001 (test across two snapshots).
- [ ] T17 · Registry path from `Settings` (derived from `output_dir`), with `.env.example` and a settings test if a new variable is needed.
- [ ] T18 · Import-boundary test (`cases` does not import `anthropic` or `mcp`); check the state-machine diagram; update `docs/STRUCTURE.md` and set status to Implemented.
