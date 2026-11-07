# 003 · Case registry and lifecycle — Tasks

Ordered, test-first: each task writes its failing tests, then the implementation. Each task fits one commit and type-checks on its own: it never imports code from a later task. E-numbers refer to the worked examples in `spec.md`.

`next_state` lands in T2 with the whole transition table, so several later lifecycle tests can pass on first run once `step` uses it (for example, the sticky state in T6). Such tests say so in their docstring as characterization tests. They are not red-phase failures.

**Domain types**
- [x] T1 · **Case types and effective severity.** Tests in `tests/unit/domain/test_cases.py`:
  - the exact `CaseState` values (`abierto`, `en_seguimiento`, `escalado`, `resuelto`) and `is_active`;
  - the `CaseEvent` values and their declaration order;
  - `case_id_for(S012, Pickup × Brasil) == "S012-Pickup-Brasil"`, and `S006-Sedán-Local` with the accent kept;
  - E6: `effective_severity` for all 8 inputs (result ≥ minimum), and `Case.current_severity` / `CaseHistoryRow.effective_severity` derived as `critica` from min `media`, raised True;
  - the `Case` validators: max < current, max `None` without `last_reported_at`, `resolved_at` without `resuelto` and the reverse, and partial `last_reported_*` all raise;
  - both models are frozen.
  - → `domain/cases.py`.

**Pure lifecycle** (`tests/unit/cases/test_lifecycle.py` → `cases/lifecycle.py`; thresholds loaded from `tests/fixtures/plant/umbrales.yaml`)
- [x] T2 · **Package, import boundary and transition table.**
  - `tests/unit/test_import_boundaries.py`:
    - add `cases` to the `anthropic`/`mcp` scan;
    - add a module-level check: every module under `plant_monitor/cases/` imports from the project only `plant_monitor.domain[.*]`, `plant_monitor.metrics.thresholds` and `plant_monitor.cases[.*]`. `layer_offenders` works at subpackage level and would accept `metrics.engine`, so this needs a module-level helper.
  - A parametrized `next_state` test over every row of the spec's transition table: `resuelto` raises `ValueError`; resolvable → `resuelto` from each active state; `escalado` stays `escalado`; critical → `escalado` from `None`, `abierto` and `en_seguimiento`; `None` → `abierto`; `abierto` and `en_seguimiento` → `en_seguimiento`.
  - → `cases/__init__.py`, `cases/lifecycle.py` with `next_state`.
- [x] T3 · **Opening in `abierto`.** E1, E2 (a) and (b) (no deviation, no case, with or without a raise) → `Observation`, `Step` and `step` for `case is None`.
- [x] T4 · **`en_seguimiento`, one active case, guards.**
  - E3: `abierto` → `en_seguimiento` with the same severity and no event; a severity change gives `severity_changed`.
  - E4, lifecycle part: stepping an active case with a deviation returns the same `case_id` and never `opened`.
  - E18: stepping the same snapshot twice, or a `resuelto` case, raises `ValueError` naming the case.
  - → `step` for an existing case, through `next_state`.
- [x] T5 · **Escalation.** E7 (threshold `critica` → `escalado`, events `escalated` then `severity_changed`), E8 (Q-08: opens in `escalado`, exactly one `escalated`, none on the next snapshot) and E9 (a raise at opening with min `media` opens `escalado`, effective `critica`).
- [x] T6 · **Sticky `escalado`.** E10: it stays `escalado` when severity drops to `alta` and then `media`, with `severity_changed` and never a second `escalated`.
- [x] T7 · **Resolution streak and reset.** E11 (two clean snapshots → `resuelto`, `resolved_at`, `resolved` event) and E12 (a deviation resets the streak; resolved at S014) → streak and `resolvable` in `step`, reading `resolucion.snapshots_sin_desvio`.
- [x] T8 · **A raise blocks resolution, and Q-25.** E13 (clean with a raise: the streak grows, never resolves) and E14 (resolved at S013 when the raise is lifted on a clean snapshot; the variant with `media` resets the streak).
- [x] T9 · **New case and new ID after resolution (pure part).** E16, lifecycle part: after `S010-Pickup-Brasil` resolves at S012, `step(None, S013 with min media)` opens `S013-Pickup-Brasil`.
- [x] T10 · **Q-26 current severity.** E15: an `escalado` case on a clean snapshot has current `ninguna`, max `critica` and `severity_changed`; the next clean snapshot resolves it from `escalado`.
- [x] T11 · **Max severity since last report (Q-28).** E17 and E32 with the pure `mark_reported(case, snapshot_id)`: the peak is kept between reports, a mark empties the max, the next snapshot sets it, and the last reported fields are `None` before the first report → `mark_reported` in `cases/lifecycle.py`, and the `None`-max branch in `step`.

**SQLite registry** (`tests/unit/cases/test_registry.py` unless stated → `cases/registry.py`)
- [x] T12 · **Schema, session, ProcessedStore contract, anomalies, registry path.**
  - E19: add `lambda: SqliteRegistry(":memory:")` (id `sqlite_memory`) to `store_factory` in `tests/unit/runner/test_store_contract.py`. The existing contract tests pass unchanged. Add a mypy-checked `store: ProcessedStore = SqliteRegistry(":memory:")`.
  - E20: anomalies are persisted in insertion order, deduped on `(kind, snapshot_id, detail)`, and absent after a failed commit.
  - E21: `user_version` is 1 on a new file; another version raises naming the file and both versions.
  - E23 (e) and (f): `record_anomaly` inside `processing`, and a nested `processing`, raise `RuntimeError`.
  - E28 in `tests/test_config.py` → the `Settings.registry_path` property. No new variable, so `.env.example` does not change.
  - → `SCHEMA_VERSION`, the full `_SCHEMA` constant, `_Session` with `require_open`, `SqliteRegistry.__init__`, `close`, the context manager, `get_hash`, `known_units`, `record_anomaly`, `recorded_anomalies`, `processing` (algorithm in `plan.md`) and `current_snapshot`.
- [x] T13 · **Case repository.**
  - E22: round trip of a case and its history row; reads rebuild the derived severities.
  - E4, registry part: a second active case for a combination raises `ValueError` naming it.
  - E23 (a), (b), (d), (g) and (h): write guards on `save_case` and `update_case`, and the `last_snapshot_id`/`snapshot_id` consistency check.
  - A second `save_case` for the same case and snapshot updates both rows in place: one `cases` row and one `case_history` row for that snapshot.
  - A mypy-checked `repo: CaseRepository = registry.cases`.
  - → `CaseRepository`, `SqliteCaseRepository` (`current_snapshot`, `save_case` with `ON CONFLICT … DO UPDATE`, `update_case`, `get_case`, `active_cases` sorted in Python by `all_combinations()` index, `history`), wired as `registry.cases`.
- [x] T14 · **Atomicity, reopen and resume.**
  - E25, without the `record_releases` call and its assertion: a `RuntimeError` or a `KeyboardInterrupt` in the block leaves no case, history, hash or unit, and the same snapshot then commits on the same instance.
  - E26, without the release parts: a new instance on the same `tmp_path` file sees everything, rejects reprocessing S011, and S012 (stepped with `lifecycle.step`) resolves with streak 2.
- [x] T15 · **Released units.**
  - E27: release order across two snapshots; the reads inside `processing` before `record_releases`; `compute_metrics` with the fixture context gives first release wins; the same tuple after a reopen.
  - E23 (c): `record_releases` outside `processing` raises.
  - The release assertions of E25 (none after a rollback) and E26 (the same releases after a reopen).
  - → `SqliteReleaseStore` (`record_releases`, `released_so_far`), wired as `registry.releases`.

**Tracker and integration**
- [x] T16 · **`CaseTracker.track`, with re-run.** `tests/unit/cases/test_tracker.py`:
  - E5 (two independent combinations, `all_combinations()` order), E16 tracker part (`active_cases()` holds only the new case; the old one stays `resuelto`) and E29 (a)–(d).
  - E31: a second `track` for S010 inside the same `processing` with `{PB}` escalates at S010, events computed against S009, one S010 history row.
  - In `tests/unit/test_import_boundaries.py`, add `plant_monitor.cases.tracker` to the runtime probe that checks no model SDK is loaded.
  - → `cases/tracker.py`: `TrackedEvent`, `CaseDelta`, `CaseTracker.track` with the private memo `(unit, snapshot_id, metrics, active_before, marked)` keyed by `current_unit()` (amended after review).
- [x] T17 · **`CaseTracker.mark_reported`.** E24 (a) persisted with max `None` and no history row, (b) a case resolved at S011 marked at S012 keeps `last_snapshot_id` S011, (c) `RuntimeError` outside `processing` and `ValueError` for an unknown case → `CaseTracker.mark_reported` (`get_case` → `lifecycle.mark_reported` → `update_case`).
- [x] T18 · **Runner integration with failure and resume.** `tests/integration/test_registry_runner.py`: E30, with `run_series`, the fixture plant files, snapshots written with `tests/builders.py`, and a `TrackingPipeline` that can raise after `track` on a given snapshot. Run U and run I use separate `tmp_path` files. No production code expected; a failure here is fixed in the module at fault.

**Docs**
- [x] T19 · **Docs and status.**
  - `docs/diagrams/case-state-machine.md`:
    - add `[*] --> escalado` (opens at `critica`, by threshold or a raise in force; Q-08, §5);
    - replace the "whether `abierto` can resolve directly … we assume it cannot" line with the consequence: the opening snapshot always has a deviation, so the streak cannot reach 2 while `abierto`;
    - add Q-25 (clean snapshots count while a raise is in force; resolution needs no raise at that snapshot), Q-26 (current severity can drop to `ninguna`; max since report keeps the peak) and Q-28 (the max excludes the report snapshot).
  - `docs/STRUCTURE.md`:
    - rows for `domain/cases.py`, `cases/lifecycle.py`, `cases/registry.py` (with `SqliteCaseRepository` and `SqliteReleaseStore`), `cases/tracker.py`;
    - the `config.py` `registry_path`;
    - the dependency rule: `cases` imports only `domain` and `metrics.thresholds`; and `runner` may import `cases` (spec 004's `runner/pipeline.py` needs it);
    - the patterns table: the State row becomes "State machine (pure transition function)" in `cases/lifecycle.py`; the Repository row says tests use SQLite `:memory:`, not an in-memory registry.
  - `docs/roadmap.md` row 003: Open items `Q-25–Q-28`; Status `Implemented`.
  - This spec's status to Implemented.
