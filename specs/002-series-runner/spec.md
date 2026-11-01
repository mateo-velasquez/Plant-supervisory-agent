# 002 · Series runner — Spec

- **Status:** Implemented
- **Requirements:** FR-01, FR-02, FR-03 (`llegadas.csv`, snapshot bytes), FR-04, FR-05 and FR-08 (amended by Q-20, Q-19), NFR-04, NFR-09, NFR-10
- **Stories:** US-01 (US-02 for the two metric amendments)
- **Decisions:** ADR-0008 (idempotency by content hash, store unit of work, non-fatal data anomalies)
- **Week:** W1

## Goal
Replay the series in the order of `llegadas.csv`, hand each new snapshot to the processing pipeline exactly once, tell the pipeline which shift the snapshot belongs to and whether it closes it, and report data anomalies without stopping an unattended run.

## Scope
- **In:**
  - Loading `llegadas.csv`.
  - Reading each snapshot's bytes once, then hashing and parsing those same bytes.
  - Moving the snapshot → shift lookup to `domain`.
  - The run loop over an injected pipeline and an injected processed-snapshot store, whose unit of work takes a `SnapshotCommit`.
  - Upfront checks, anomaly checks and the run summary.
  - Two small metric amendments: the Q-19 clamp and Q-20 first release wins.
- **Out:**
  - The SQLite store that persists hashes, anomalies and known units (spec 003 implements the port defined here).
  - The pipeline itself (spec 004), the CLI (spec 012) and missing snapshots in the series (FR-42).
  - Q-17.

## Behavior

**Arrivals file (FR-01, FR-03)**
- `llegadas.csv` is read as `utf-8-sig`, which strips the BOM. Its columns are `orden`, `snapshot_id`, `archivo` and `recibido`.
- `orden` is a positive integer and unique in the file. `recibido` must be an ISO 8601 naive datetime; it is validated but informative only.
- `archivo` must be a bare file name, portable across Ubuntu and Windows. It may not be empty, contain `/`, `\`, `:`, `*`, `?`, `"`, `<`, `>` or `|`, end with a dot or a space (Windows drops them, so the same name would resolve differently per OS), or be `.` or `..`.
- `archivo` is resolved against the directory that contains `llegadas.csv`, which by the data layout is the snapshots directory (`data/README.md`).
- A `snapshot_id` may appear in more than one row; that is how `S034` arrives twice.
- Every failure raises `DataLoadError` naming the file, the physical line (header = line 1) and the field, as the 001 loaders do.
- The loader returns `Arrival` records (defined in `ingestion/arrivals.py`) sorted by ascending `orden`.

**Order and shift (FR-01, FR-04)**
- Arrivals are processed in ascending `orden`. `run_series` sorts them itself, whatever order it receives them in. `recibido` never affects order.
- Each snapshot maps to exactly one shift through `turnos.csv`. It is either that shift's `snapshot_medio` (position `mid`) or its `snapshot_cierre` (position `closing`).
- The lookup `snapshot_position` moves from `metrics/plan.py` to `domain/calendar.py`. It returns the `Shift` and a `ShiftPosition`, and still raises `ValueError` naming an unknown snapshot (001 E17).
- The shift and position of every arrival are resolved once, in the upfront pass, and kept for the run.
- The shift and position handed to the pipeline always come from `turnos.csv`, never from the snapshot's own `turno` field.

**Upfront checks (Q-21)**
- Before processing anything, `run_series` checks every arrival. Its file must exist on disk (existence only, no reading or parsing), and its `snapshot_id` must be a mid or closing snapshot in `turnos.csv`.
- Any failure raises one `DataLoadError` that names every missing file and every unknown snapshot. Nothing is processed and the store is not touched.

**Idempotency (FR-02, §4, Q-10, ADR-0008)**
- For each arrival the runner reads the file's bytes once and computes the content hash: SHA-256 of those bytes, **before parsing**.
- The store is looked up by the `snapshot_id` of the `llegadas.csv` row:
  - **No stored hash:** the snapshot is new. The same bytes are parsed and processed, so the stored hash always matches the parsed content.
  - **Same hash:** the arrival is skipped with no side effects. The bytes are not parsed, the pipeline is not called and the store is not written. The run log records INFO `"<id> skipped: already processed"`.
  - **Different hash:** the first processed version wins. The arrival is neither parsed nor reprocessed. The runner builds a `repeated_with_different_content` anomaly, passes it to `store.record_anomaly`, adds it to the summary, and logs a WARNING starting `"<id> repeated with different content (hash "` that contains both the new and the stored hash.
- Both repeat cases are listed in `RunSummary.skipped`, so a run that completes has `len(processed) + len(skipped) == len(arrivals)`.
- A repeat within the same run behaves like a repeat across runs, because the store is consulted for every arrival.

**Parsing a new snapshot (FR-03, Q-22)**
- The snapshot is validated from the bytes already read, with `parse_snapshot(data, source)`. `load_snapshot(path)` stays and delegates to it.
- Bytes that are not UTF-8, invalid JSON or a schema error raise `DataLoadError` naming the file and the field, exactly as `load_snapshot` does today.
- If the `snapshot_id` inside the JSON differs from the `llegadas.csv` row, that is a `DataLoadError` naming the file and both ids.
- Either failure is treated like a pipeline failure (next block): the run stops, and the snapshot stays unprocessed so the next run resumes there.

**Unit of work and failure (NFR-10, Q-23, ADR-0008)**
- For each new snapshot the runner builds a `SnapshotCommit` with the `snapshot_id`, the content hash, the snapshot's anomalies and its `new_units`: units first seen in this snapshot, each with its combination.
- The pipeline is called inside `store.processing(commit)`. Only when that block exits cleanly does the store record the hash, the anomalies and the new units, atomically. If it exits with an exception (including `KeyboardInterrupt`), the store records nothing.
- Every registry write for the snapshot goes through the same store connection inside that block. The composition root (spec 012) passes the same instance to the runner and to the pipeline.
- **Pipeline contract:** side effects outside the database, such as notifier delivery, happen only after the commit. Otherwise a resume would resend an `alerta_inmediata`. Spec 004 may return outgoing notices from `process` or use an outbox table. No signature change in 002.
- Any `Exception` raised while handling an arrival after the upfront checks stops the run. That covers reading, hashing, parsing, the id check, the pipeline and the unit of work. The runner then raises `RunAborted` carrying:
  - the arrival's `snapshot_id`;
  - the original exception as `cause`, also chained as `__cause__`;
  - the partial `RunSummary`.
- `str(RunAborted)` includes the snapshot id and the cause's message.
- At abort, `len(summary.processed) + len(summary.skipped)` equals the 0-based index of the failed arrival in `orden` order.
- `KeyboardInterrupt` and other non-`Exception` errors are not wrapped: they propagate as they are, and the unit of work still records nothing.
- The next run with the same store skips every snapshot already marked and resumes at the failed one.
- The in-memory store honours the same semantics. Entering `processing` for a `snapshot_id` already marked raises `ValueError`.

**Anomalies (Q-18, Q-19, Q-20, ADR-0008)**
- Anomalies never stop the run.
- Each anomaly is added to `RunSummary.anomalies` with `kind`, `snapshot_id` and `detail`, and is logged once as a WARNING `"<id> <kind>: <detail>"`. The Q-10 anomaly uses the message above instead.
- Anomalies of a processed snapshot are stored through its `SnapshotCommit`, so only on success. The Q-10 anomaly is stored through `record_anomaly`, because there is no commit on the skip path.
- The checks run on every parsed snapshot before the pipeline is called. A snapshot whose pipeline then fails still contributes its anomalies to the partial summary, but they are not stored. The resumed run detects them again.

| Kind | Trigger | Detail names | Effect |
|---|---|---|---|
| `repeated_with_different_content` | Same `snapshot_id` as a processed snapshot, different hash (Q-10) | both hashes | Not reprocessed. |
| `shift_mismatch` | Snapshot `turno` differs from the `turno_id` that `turnos.csv` gives it (Q-18) | both shift ids | `turnos.csv` wins; the pipeline gets the shift from `turnos.csv`. |
| `stage_entry_after_snapshot` | A unit in `unidades` whose `ingreso_etapa` is later than the snapshot `timestamp` (Q-19). Equal is not an anomaly. One anomaly per such unit. | unit id, `ingreso_etapa`, `timestamp` | Metrics clamp the elapsed time at 0 (below). |
| `unit_combination_changed` | A `unidad_id` appears with a `modelo`/`mercado` different from its first sighting (Q-20). At most one anomaly per unit per snapshot. | unit id, first and new combination | None on metrics: progress follows the first *release* (below), independently. |

- **Unit identity (Q-20):**
  - At the start of the run, the runner seeds its identity map from `store.known_units()`. A fresh in-memory store gives `{}`.
  - Within a snapshot, sightings are scanned in `unidades` list order and then in `liberadas` list order; earlier snapshots come first.
  - The first sighting of a unit is never overwritten.
  - `check_unit_identity` returns the anomalies and the snapshot's new sightings, which become `SnapshotCommit.new_units`. The runner merges them into its map after the commit succeeds.
- The checks are pure and deterministic: no I/O and no wall clock.

**Time reference (NFR-04)**
- The only time reference is the snapshot `timestamp`, never the wall clock. That includes the `stage_entry_after_snapshot` check and everything the pipeline receives.

**Metric amendments to spec 001**
- **Q-19 · Clamped elapsed (FR-08)**
  - Rule: in `projected_yard_arrival`, `elapsed = max(0, timestamp − ingreso_etapa)`. So `remaining_current = max(0, standard − elapsed)` never exceeds the stage standard (§1: "lo que le falta del tiempo estándar de la etapa (cero si ya lo superó)").
  - `bottleneck.is_delayed` already treats a negative elapsed as not delayed, which is the same as 0 elapsed, so it stays unchanged.
  - A repainting unit stays delayed regardless of its elapsed time.
- **Q-20 · First release wins (FR-05)**
  - Rule: `count_progress` counts each `unidad_id` once across all combinations, in the combination of its first occurrence in the input. Its input is releases only (§1: "una unidad que aparece dos veces se cuenta una").
  - Callers pass releases in release order: earlier snapshots first, then list order within a snapshot. `compute_metrics` already chains `released_so_far` before the current `liberadas`.
  - Progress never reads the identity map, whose content depends on where a run resumed. So the same data always gives the same progress (NFR-04).
  - The identity anomaly and progress are two independent rules: one reports that the data changed, the other counts releases.

**Logging (NFR-09)**
- Logger `plant_monitor.runner.series`.
- INFO `"<id> processed: <turno_id> <position>"` for each processed snapshot, and INFO for each identical-hash skip. A different-hash repeat logs only its WARNING (Q-10).
- WARNING for each anomaly.
- The runner logs nothing extra on abort: it raises, and the caller (spec 012) logs.

## Worked examples

**Fixtures used below**
- The fixture `turnos.csv` has:
  - T01: S001 mid at 10:00, S002 closing at 14:00.
  - T02: S003 and S004.
  - T03: S005 mid at 2026-03-03T02:00, then S006.
- Examples with S034 use a synthetic `turnos.csv` row `T17,…,2026-03-07T14:00,2026-03-07T22:00,S033,S034`.
- Standards and shipments are the fixture files:
  - SUV `calidad` standard: 180 min.
  - BRA-0303: cut-off 03-03 06:00, departure 03-03 08:00.
  - BRA-0304: cut-off 03-04 06:00, departure 03-04 08:00.
- The fake pipeline records `(snapshot_id, turno_id, position)` for each call.

**Characterization examples:** E16b, the bottleneck parts of E16, and the metrics part of E21 already pass with today's code. They are kept as characterization tests that pin the existing behaviour.

| # | Input | Expected |
|---|---|---|
| E1 | Arrivals S001 (orden 1), S002 (2), S003 (3); valid files; empty store; S001 has U1 (Sedán × Local) in `unidades` | Pipeline calls `(S001, T01, mid)`, `(S002, T01, closing)`, `(S003, T02, mid)`. Summary: processed `(S001, S002, S003)`, skipped `()`, anomalies `()`. The store holds the three hashes, and `known_units()` contains `U1 → Sedán/Local`. |
| E2 | (a) `llegadas.csv` lines in file order with `orden` 3, 1, 2 (S003, S001, S002). (b) `run_series` given arrivals in the order orden 2, 3, 1. | (a) The loader returns orden 1, 2, 3. (b) `run_series` calls the pipeline S001, S002, S003. |
| E3 | `llegadas.csv` written with a UTF-8 BOM | The first column is `orden`, with no `﻿` prefix. |
| E4 | `llegadas.csv` rows with: (a) `orden` `2` repeated on line 4, first seen on line 3; (b) `orden` `x` on line 3; (c) `recibido` `3/2/2026 10:05` on line 2; (d) `archivo` `../S001.json` on line 2; (e) `orden` `0` on line 2; (f) `archivo` `sub\S001.json` on line 2; (g) `archivo` `C:S001.json` on line 2; (h) `archivo` `..` on line 2 | `DataLoadError` naming `llegadas.csv`, the line and the field: (a) `row 4`, `orden`, and it cites row 3; (b) `row 3`, `orden`; (c) `row 2`, `recibido`; (d), (f), (g), (h) `row 2`, `archivo`; (e) `row 2`, `orden`. The same result on Ubuntu and Windows. |
| E5 | `tmp/snaps/llegadas.csv` with the row `1,S001,S001.json,2026-03-02T10:05` | `Arrival(orden=1, snapshot_id="S001", archivo=tmp/snaps/S001.json, recibido=2026-03-02T10:05)`. |
| E6 | `content_hash(b"abc")`, `content_hash(b"abd")`, `content_hash(b"\xef\xbb\xbfabc")` | The first is `ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad` (lowercase hex). The other two differ from it and from each other. The same bytes hashed twice give the same value. |
| E6b | `parse_snapshot(data, source)`: (a) the bytes of a valid S001 file; (b) `{"snapshot_id": "S002", "unidades": [` with source `S002.json`; (c) `b"\xff\xfe"` with source `S002.json` | (a) Equal to `load_snapshot` of the same file. (b) and (c) `DataLoadError` naming `S002.json`. The existing `load_snapshot` tests stay green. |
| E7 | Arrivals S034 (orden 1) and S034 (orden 2), both with `archivo` `S034.json` (T17 closing) | The pipeline is called once, with `(S034, T17, closing)`. Summary: processed `(S034,)`, skipped `(S034,)`. INFO log `"S034 skipped: already processed"`. `processing` is entered once and `record_anomaly` is never called. |
| E8 | Arrivals S034 → `S034.json` (orden 1) and S034 → `S034_bis.json` (orden 2, valid JSON with one unit more) | The pipeline is called once, with the first version, and the store keeps the first hash. Summary: skipped `(S034,)` and one `repeated_with_different_content` anomaly for S034 whose detail contains both hashes. `record_anomaly` is called once, with that anomaly. The WARNING log starts with `"S034 repeated with different content (hash "` and contains both hashes. |
| E9 | The store is seeded with `S034` → `content_hash(b"not json")`. (a) Arrival S034 → a file with bytes `not json`. (b) Arrival S034 → a file with bytes `{broken`. | (a) Skipped, with no `DataLoadError` and no pipeline call: the bytes are never parsed. (b) A `repeated_with_different_content` anomaly, with no `DataLoadError` and no pipeline call. |
| E10 | Arrivals S001, S002, S003. The fake pipeline raises `RuntimeError("boom")` on S003. Then a second run with the same store and a healthy pipeline. | **Run 1** raises `RunAborted`: `snapshot_id` `S003`, `cause` the `RuntimeError` (also its `__cause__`), and `str(exc)` contains `S003` and `boom`. `summary.processed` is `(S001, S002)`, and processed + skipped = 2, the index of S003. The store holds S001 and S002 only. **Run 2:** pipeline calls `[S003]`, skipped `(S001, S002)`, processed `(S003,)`. |
| E10b | Same arrivals; the fake pipeline raises `KeyboardInterrupt` on S002 | `KeyboardInterrupt` propagates; it is not a `RunAborted`. `get_hash("S002")` is `None`, and S001 stays marked. |
| E11 | Arrivals S001, S002, S003; `S002.json` is absent | `DataLoadError` whose message contains `S002.json`. The pipeline is never called and the store is empty: S001 is not processed either. |
| E12 | Arrivals S001 and S999 (file present). S999 is in neither column of `turnos.csv`. Also a variant with S999 plus a missing `S002.json`. | `DataLoadError` naming `S999`, and nothing is processed. In the variant, one error names both `S999` and `S002.json`. |
| E13 | Arrivals S001, S002, S003; `S002.json` contains `{"snapshot_id": "S002", "unidades": [`. Then the file is fixed and the series is rerun. | **Run 1:** `RunAborted` at `S002` whose `cause` is a `DataLoadError` naming `S002.json`. S001 is processed and marked, S002 is not marked, and S003 is never read. **Run 2:** S001 is skipped, then S002 and S003 are processed. |
| E14 | Arrival S002 → `S002.json`, whose JSON `snapshot_id` is `S003` | `RunAborted` at `S002` whose `cause` is a `DataLoadError` naming `S002.json`, `S002` and `S003`. S002 is not marked and the pipeline is not called for it. |
| E15 | `S003.json` has `turno` `T01`; `turnos.csv` maps S003 to T02 mid | One `shift_mismatch` anomaly for S003, with a detail naming `T01` and `T02`, and a WARNING. The pipeline is called with `(S003, T02, mid)`. S003 is processed and its commit carries the anomaly. |
| E16 | `S005.json` (T03 mid, `timestamp` 2026-03-03T02:00) has unit U00051: SUV × Brasil, `calidad`, `ingreso_etapa` 2026-03-03T03:00, `retrabajos` 0, assigned BRA-0303 | **Runner:** one `stage_entry_after_snapshot` anomaly for S005 naming U00051; the run continues and S005 is processed. **Metrics (Q-19):** elapsed is clamped to 0, so the remaining `calidad` time is 180 and the projection is 03-03 05:00. That is before the 06:00 cut-off, so the reachable shipment is BRA-0303: delay 0, no delay severity. Without the clamp, the remaining time would be 180 + 60 = 240, giving 06:00. That misses the cut-off, so the reachable shipment would be BRA-0304: 1 day, `alta`. **Bottleneck:** `is_delayed` is False (characterization). |
| E16b | (a) The same unit with `ingreso_etapa` 2026-03-03T02:00, equal to `timestamp`. (b) An SUV × Brasil unit in `pintura` with `retrabajos` 1 and `ingreso_etapa` 03:00. | (a) No anomaly; remaining time 180. (b) One anomaly; `is_delayed` is True because the unit is repainting. Characterization for the metrics parts. |
| E17 | S001 `liberadas`: U1 and U2 as Sedán × Local. S002 `liberadas`: U2 and U3 as SUV × Local. | **Runner:** one `unit_combination_changed` anomaly for S002, with a detail naming U2, `Sedán/Local` and `SUV/Local`. Both snapshots are processed. **Metrics (Q-20)** at S002, from `compute_metrics` with `released_so_far` = the S001 releases: Sedán × Local progress 2; SUV × Local progress 1 (U3 only; the old rule gave 2). With the fixture plan of SUV × Local T01 = 8 at closing, `gap_units` is −7 (the old rule gave −6). |
| E17b | `count_progress([U7 Sedán × Local, U7 SUV × Local])` | Sedán × Local 1, SUV × Local 0, total across combinations 1. |
| E18 | U2 is first seen in S001 `liberadas` as Sedán × Local. In S002 it is in `unidades` (`patio`) and in `liberadas`, both as SUV × Local. In S003 it is in `unidades` as SUV × Local. | One `unit_combination_changed` anomaly in S002 (not two) and one in S003. `check_unit_identity` returns no new sightings for U2. |
| E19 | Store contract, parametrized over `store_factory`: (a) a fresh store; (b) `with store.processing(commit_s001): raise RuntimeError`; (c) a clean exit with `commit_s001` (hash `h`, one anomaly, `new_units` `{U1: Sedán/Local}`); (d) entering `processing` again for S001 after (c) | (a) `get_hash` returns `None` and `known_units()` is `{}`. (b) The error propagates; `get_hash("S001")` is `None`, `known_units()` is `{}`, and no anomaly is recorded. (c) `get_hash("S001") == h` and `known_units()` is `{U1: Sedán/Local}`. (d) `ValueError` naming S001. **In-memory specific:** `recorded_anomalies()` holds the commit's anomaly only after (c), plus any passed to `record_anomaly`. |
| E20 | `snapshot_position(shifts, …)` with the fixture `turnos.csv`, imported from `plant_monitor.domain.calendar` | S001 → (T01, `mid`); S002 → (T01, `closing`); S003 → (T02, `mid`); S999 → `ValueError` naming S999. |
| E21 | U9: in S001 `unidades` as Sedán × Local (`calidad`); in S002 `liberadas` as SUV × Local, its only release | **Runner:** one `unit_combination_changed` anomaly in S002 (Sedán/Local → SUV/Local). **Metrics (Q-20):** U9 counts under SUV × Local only, so progress is SUV × Local 1 and Sedán × Local 0. Progress follows the first release, not the first sighting (characterization). |
| E22 | S001 `liberadas`: U2 as Sedán × Local. S002 `liberadas`: U2 and U3 as SUV × Local. Run 1: the pipeline fails on S002. Run 2: same store, healthy pipeline. | **Run 1:** the partial summary has the U2 anomaly for S002. The store's `known_units()` is `{U2: Sedán/Local}`: U3 is absent because S002's commit was not recorded. **Run 2:** the identity map is seeded from `known_units()`, so S002 again gives the U2 anomaly. After success, `known_units()` contains U2 → Sedán/Local and U3 → SUV/Local. |

## Edge cases and assumptions
- **Q-10:** the first processed version of a snapshot wins. The hash is computed from the raw bytes before parsing, and the same bytes are parsed.
- **Q-17 (open, out of scope):** a gap-only deviation has bottleneck `None`. It is to be decided before spec 004.
- **Q-18:** a snapshot `turno` that disagrees with `turnos.csv` is an anomaly, not a data error. The field holds a shift id like `T01` (confirmed against the data model).
- **Q-19:** a future `ingreso_etapa` is clamped to 0 elapsed for the projection.
- **Q-20:**
  - Identity follows the store: the runner seeds it from `known_units()`, and units are stored with each successful commit. With the in-memory store, hashes and units live and die together, so a new process reprocesses everything consistently.
  - In 002 there is no persistent store yet. A store that kept hashes but not units would make the set of `unit_combination_changed` anomalies depend on where a run resumed. Spec 003 must persist `new_units` in the same transaction as the hash. This matters for spec 005 evals, which compare anomaly sets.
  - `count_progress` depends on input order, so spec 003 must return released units in release order.
- **Q-21:** the upfront checks cover file existence and calendar membership only. Content is validated when each snapshot is parsed (Q-22).
- **Q-22:** a snapshot that fails to load stops the run; it is never skipped.
- **Q-23:** a failure inside the unit of work records nothing.
- A rerun that meets a different-hash repeat again calls `record_anomaly` again. Deduplicating stored anomalies is up to spec 003.
- **Explicitly out of scope, with no rule:** a `liberadas[].hora` later than the snapshot `timestamp`, and a snapshot `timestamp` that does not match its shift's mid or closing time. Neither changes any metric. Neither was observed in days 1–7. And `turnos.csv` has no per-snapshot time to compare against.
- A snapshot in `turnos.csv` that never arrives is not detected here (FR-42, out of scope).
- The runner has no knowledge of metrics or cases. Progress accumulation across snapshots belongs to the pipeline and the registry (specs 003 and 004).

## Acceptance
- [ ] E1–E22 (including E6b, E10b, E16b and E17b) are tests and pass, and every rule above has a passing test.
- [ ] `llegadas.csv` loading is tested on a synthetic CSV with a BOM and on malformed rows.
- [ ] The store contract test is parametrized over `store_factory`.
- [ ] `ingestion` and the whole `runner` package import neither `anthropic` nor `mcp`. The layer checks pass: `domain` imports nothing from the project, `ingestion` imports only `domain`, and `runner/checks.py` imports only `domain`.
- [ ] `ruff`, `mypy --strict` and `pytest` pass.
- [ ] `docs/STRUCTURE.md` updated, and spec 001 notes the Q-19 and Q-20 amendments.
