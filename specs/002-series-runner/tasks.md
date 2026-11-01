# 002 · Series runner — Tasks

Ordered, test-first: each task writes its failing tests, then the implementation. Each task fits one commit. E-numbers refer to the worked examples in `spec.md`.

**Characterization tests** pin behaviour that today's code already has. They pass on first run, and their names or docstrings say so. They are not red-phase failures.

- [ ] T1 · **Move `snapshot_position` to `domain/calendar.py`.** Add `ShiftPosition` to `domain/enums.py`. Move the position tests from `tests/unit/metrics/test_plan.py` to `tests/unit/domain/test_calendar.py`, now expecting `(Shift, ShiftPosition)`; this is E20, including 001 E17 (S999 raises naming it). Move the function with no re-export, and update `metrics/engine.py` to the new import and return type. The full suite stays green, and `test_engine.py` is unchanged.
- [ ] T2 · **Q-19 clamp.**
  - New failing test in `test_delay.py`: E16 metrics part (future `ingreso_etapa` → projected 03-03 05:00, delay 0).
  - Characterization tests: E16b (equal timestamp → remaining 180), and in `test_bottleneck.py` a future entry that is not delayed and a repainting unit with a future entry that is still delayed.
  - Then clamp elapsed at 0 in `metrics/delay.py::projected_yard_arrival` and update its docstring.
- [ ] T3 · **Q-20 first release wins.**
  - New failing tests: E17b in `test_progress.py` and the E17 metrics part in `test_engine.py`. With `released_so_far` = U1 and U2 as Sedán × Local, and S002 releasing U2 and U3 as SUV × Local, the result is Sedán × Local 2, SUV × Local 1 and `gap_units` −7.
  - Characterization test: the E21 metrics part (U9 counted under SUV × Local only).
  - Then make `metrics/progress.py::count_progress` count each `unidad_id` once, in the combination of its first occurrence, and state the order dependence in its docstring.
- [ ] T4 · **Domain types.** Add `AnomalyKind` (4 exact values), `Anomaly` (frozen) and `SnapshotCommit` (frozen dataclass), with tests → `domain/enums.py`, `domain/models.py`.
- [ ] T5 · **Bytes-based snapshot parser.** E6b: `parse_snapshot` equals `load_snapshot` on valid bytes, and invalid JSON or non-UTF-8 bytes name the source → `ingestion/snapshot.py`, with `load_snapshot` delegating to it. The existing loader tests stay green.
- [ ] T6 · **Content hash.** E6: the known SHA-256 of `abc`, one byte changed, BOM-prefixed bytes, and stability on rehash → `ingestion/hashing.py::content_hash(data: bytes)`.
- [ ] T7 · **Arrivals loader.** A synthetic `llegadas.csv` written with a BOM in `tmp_path`. Covers the E2 loader part, E3, E4 (a–h, the same result on both OSes) and E5, plus `Arrival` validation (positive `orden`, naive `recibido`, frozen) → `Arrival` and `load_arrivals` in `ingestion/arrivals.py`.
- [ ] T8 · **Ports and in-memory store.**
  - E19 as a contract test parametrized over a `store_factory` fixture: a fresh store, an exception that records nothing, a clean exit that records the hash and units, and re-entry raising `ValueError`.
  - In-memory-specific tests: `recorded_anomalies()` after a commit and after `record_anomaly`; nothing recorded after an exception; the `hashes` seed.
  - A mypy-checked assignment of `InMemoryProcessedStore()` to a `ProcessedStore` variable.
  - → `runner/__init__.py`, `runner/ports.py` (including the connection and after-commit contract docstrings), `runner/memory_store.py`.
- [ ] T9 · **Anomaly checks.** Pure tests with in-memory `Snapshot` builders → `runner/checks.py`:
  - `check_shift`: E15.
  - `check_stage_entries`: E16 and E16b (a future entry is an anomaly, an equal one is not, one anomaly per unit).
  - `check_unit_identity`: E17, E18 and E21. The first sighting wins, with `unidades` scanned before `liberadas`. At most one anomaly per unit per snapshot. It returns only the new sightings and never mutates the input map.
- [ ] T10 · **Runner happy path.**
  - First, move `snapshot_payload`, `unit_payload`, `released_payload` and `write_snapshot` from `test_snapshot_loader.py` to `tests/builders.py`, and update that module's imports.
  - Then E1 and the E2 runner part: sorted by `orden`; shift and position resolved upfront from `turnos.csv`; INFO `"<id> processed: …"`; `RunSummary` fields; `known_units()` after the run.
  - → `runner/series.py` with `RunSummary` and `run_series`: read once, hash, parse, then commit with `new_units` from `check_unit_identity`, with the identity map seeded from `known_units()`.
- [ ] T11 · **Idempotency.** → `runner/series.py`.
  - E7: an identical repeat is skipped, logged at INFO, `processing` is entered once and `record_anomaly` is never called.
  - E8: a different hash gives an anomaly, a WARNING with both hashes, and one `record_anomaly` call; the first version is kept.
  - E9: with a seeded store, byte-identical and corrupt repeats are never parsed.
- [ ] T12 · **Failure and resume.** → `RunAborted` in `runner/series.py`.
  - E10: a pipeline failure raises `RunAborted` with `snapshot_id`, `cause`, `__cause__`, a `str()` containing the id and the cause, and the partial summary. The abort invariant (processed + skipped = index of the failed arrival) holds, and the next run resumes there.
  - E10b: `KeyboardInterrupt` is not wrapped and nothing is recorded.
  - E13: invalid JSON mid-series raises `RunAborted` with a `DataLoadError` cause, and the run resumes after the file is fixed.
  - E14: an id mismatch raises `RunAborted` with a `DataLoadError` naming the file and both ids.
- [ ] T13 · **Upfront errors.** E11 (a missing file: `DataLoadError` naming it, the pipeline never called, the store empty) and E12 (an unknown snapshot; both problems reported in a single error) → error collection in the upfront pass of `run_series`.
- [ ] T14 · **Anomalies in the run.** Runner-level E15 (the pipeline gets T02 mid; WARNING; the anomaly is in the summary and in the commit), the runner part of E16 (the run continues), the runner parts of E17 and E21 (identity carried across the snapshots of one run), and E22 (identity seeded from `known_units()` across a resume, with a failed commit storing no units). Also a test that anomalies found before a pipeline failure are in `RunAborted.summary` but are not recorded in the store → wire every check's anomalies into the summary, the WARNING log and `SnapshotCommit.anomalies` in `run_series`.
- [ ] T15 · **Import boundaries and layers.** In `tests/unit/test_import_boundaries.py`:
  - Extend the `anthropic`/`mcp` scan to the `ingestion` package and the whole `runner` package.
  - Add a runtime probe that imports `plant_monitor.runner.series`.
  - Extend the AST scanner to report `plant_monitor.<subpackage>` imports, and add layer checks: `domain` imports nothing from the project, `ingestion` imports only `domain` (and itself), and `runner/checks.py` imports only `domain`.
- [ ] T16 · **Docs.**
  - `docs/STRUCTURE.md`:
    - new modules: `domain/calendar.py`, `ingestion/arrivals.py`, `ingestion/hashing.py`, `runner/*`;
    - the `ingestion/snapshot.py` row with `parse_snapshot`;
    - the `metrics/plan.py` row without `snapshot_position`;
    - the dependency rule: `runner` may import `ingestion` and `metrics`, and `ingestion` imports only `domain`.
  - Spec 001 Behavior: a one-line note under FR-05 and under FR-08, pointing to the Q-20 and Q-19 amendments.
  - This spec's status to Implemented.
  - The `docs/roadmap.md` Status column for 002.
