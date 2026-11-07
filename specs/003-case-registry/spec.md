# 003 · Case registry and lifecycle — Spec

- **Status:** Implemented
- **Requirements:** FR-05 (persisted releases), FR-12, FR-13, FR-14, FR-15, FR-23 (max severity), NFR-04, NFR-10
- **Stories:** US-03
- **Decisions:** ADR-0003 (SQLite registry, single writer), ADR-0008 (unit of work over a `SnapshotCommit`). No new ADR.
- **Week:** W1

## Goal
Keep, outside the model, one case per deviation with its state, severities and history, and apply the threshold-driven lifecycle of `criterio.md` §3 in code, before any agent runs. Persist everything the series runner (spec 002) needs to resume: hashes, anomalies, unit identity and released units, all in one SQLite transaction per snapshot.

## Scope
- **In:**
  - Case types with effective severity as a derived field, and the pure lifecycle: one transition function, clean streak, max severity since the last report.
  - `SqliteRegistry`: implements spec 002's `ProcessedStore` and owns the one unit of work per snapshot. Its table groups are collaborators on the same connection: `registry.cases` (cases and history) and `registry.releases` (released units).
  - `CaseTracker`: applies the lifecycle to one snapshot's metrics, can re-run within the same snapshot when the raises change (Q-27), and marks cases as reported.
  - The registry file path in `Settings`.
  - An integration test: runner + registry + a minimal test pipeline, with a failure and a resume.
- **Out:**
  - Where a raise comes from and its scope (spec 008). This spec receives the combinations with a raise in force as an input.
  - Whether the agent may raise at N a case that `track` resolved at N (Q-29, open, spec 008).
  - Which cases are news, alerts and reports, and which cases get marked as reported (spec 004). The production pipeline `ThresholdPipeline` (spec 004, `runner/pipeline.py`).
  - Causes (spec 008), MCP tools (spec 006), the CLI (spec 012).
  - Q-17 (open, before 004) and Q-24 (open, spec 006).

## Behavior

**Opening (FR-12, §3)**
- A case opens when a combination with no active case has a deviation: minimum severity ≥ `media` (§2).
- Deviation is defined by the minimum severity only (§2, Q-25). A raise in force on a combination with no deviation does not open a case. A raise applies to cases that open while it is in force (§5).
- At most one active case per combination. Active means `abierto`, `en_seguimiento` or `escalado`.
- **Case ID:** `<snapshot_id>-<modelo>-<mercado>` of the opening snapshot, e.g. `S012-Pickup-Brasil`. It is unique because at most one case per combination opens per snapshot. It is stable across runs, resumes and re-runs (NFR-04, Q-27).

**Effective severity (FR-15, §2, §5)**
- Effective severity = max(minimum severity, `critica` if a raise is in force on the combination at this snapshot, else `ninguna`).
- It is never below the minimum. It is computed only in `domain/cases.py`, by `effective_severity(minimum, raised)`.
- `Case.current_severity` and `CaseHistoryRow.effective_severity` are derived from `(minimum_severity, raised)` and are not constructor inputs, so a case or row with an inconsistent severity cannot be built.
- **Current severity (Q-26):** an active case's current severity at a snapshot is that snapshot's effective severity, including `ninguna` on a clean snapshot.

**States (FR-13, §3)**
- In the opening snapshot the state is `abierto`. From the next snapshot it is `en_seguimiento`, with or without a deviation.
- The case becomes `escalado` when its effective severity is `critica`, by threshold or by a raise in force. It stays `escalado` until it resolves, even if the severity drops (§3).
- **Q-08:** a case whose effective severity is `critica` in its opening snapshot opens directly in `escalado`. That includes a raise in force at opening with a minimum of `media` (§5).
- **Clean streak:** the number of consecutive snapshots without deviation, ending at the current one. A snapshot with a deviation resets it to 0. The opening snapshot has a deviation, so the streak starts at 0.
- **Q-25:** clean snapshots count toward the streak even while a raise is in force, because deviation depends only on the minimum severity (§2).
- **Resolution (§3):** resolution is checked at every snapshot. The case becomes `resuelto` when the clean streak ≥ `resolucion.snapshots_sin_desvio` (2, read from `umbrales.yaml`) **and** no raise is in force at that snapshot. This holds from `en_seguimiento` and from `escalado`.
- The opening snapshot always has a deviation, so with `snapshots_sin_desvio = 2` the streak is at most 1 when the case leaves `abierto`. It never resolves straight from `abierto`. This is a consequence of the rule, not a special case in code.
- A resolution snapshot is clean and has no raise, so its effective severity is `ninguna`. It can never also escalate.
- `resuelto` is final. A later deviation on the combination opens a **new** case with a new ID (§3).
- **Transition table:** one pure function, `next_state(current, *, critical, resolvable)`, holds every rule above. `current = None` means opening, where `resolvable` is always False:

| `current` | `resolvable` | `critical` | Next state |
|---|---|---|---|
| `resuelto` | any | any | `ValueError` (final) |
| any active | True | any | `resuelto` |
| `escalado` | False | any | `escalado` (sticky) |
| `None`, `abierto`, `en_seguimiento` | False | True | `escalado` |
| `None` | False | False | `abierto` |
| `abierto`, `en_seguimiento` | False | False | `en_seguimiento` |

**Events (input for spec 004)**
- Every evaluation of a case at a snapshot yields zero or more events, in this order:
  - `opened`: the case opened at this snapshot.
  - `escalated`: the state became `escalado` at this snapshot, either from another state or at opening (Q-08). A case already `escalado` never yields it again (§4: one alert per case).
  - `severity_changed`: the case existed before this snapshot and its current severity differs from its previous current severity. It is never emitted at opening.
  - `resolved`: the state became `resuelto` at this snapshot.
- Moving from `abierto` to `en_seguimiento` yields no event, because §4 treats both as the same state for news.

**Report baseline (FR-14, FR-23, §4, Q-28)**
- **Max severity since last report** = max of the effective severities over the snapshots evaluated after the last report snapshot, up to and including the current one. The last report snapshot itself is excluded: its peak was already reported. §4: the max exists "para que no se pierda un pico que subió y bajó entre dos cierres".
- At opening the max is the opening severity. Before the first report it covers every snapshot since opening.
- `CaseTracker.mark_reported(case_id, snapshot_id)` stores the snapshot as `last_reported_at`, the case's state and current severity as the last reported state and severity, and sets the max severity since the last report to `None` (empty). The next evaluated snapshot sets it to that snapshot's effective severity.
- Every case in a report was evaluated at least once since its previous report (at the closing snapshot, or at its resolution snapshot within the shift), so a report never reads an empty max.
- A case resolved earlier in the shift can be marked at the closing snapshot. Its last reported state is then `resuelto`, and its `last_snapshot_id` stays at its resolution snapshot.
- Before the first report, `last_reported_at`, the last reported state and the last reported severity are `None`.
- Marking writes no history row. Deciding which cases are reported and what is news belongs to spec 004.

**History (FR-14)**
- One history row per active case per snapshot in which it was evaluated, including the opening and the resolution snapshots.
- Each row has: `snapshot_id`, state, minimum severity, raised flag, effective severity (derived), `gap_units`, `gap_pct`, `delay_days`, `bottleneck` and the clean streak.
- `history(case_id)` returns the rows in processing order.

**Unit of work (NFR-10, Q-23, ADR-0003, ADR-0008)**
- `SqliteRegistry.processing(commit)` is the **only** unit of work.
- On entry:
  - It raises `ValueError` naming the snapshot if the snapshot is already marked. Nothing is written.
  - It raises `RuntimeError` if another unit of work is already open.
  - Otherwise it opens a transaction.
- Inside the block:
  - Every case, history, release and report-baseline write for the snapshot (through `registry.cases` and `registry.releases`) uses the same connection and transaction.
  - Each write checks, through the registry's single guard, that its `snapshot_id` is that of the open unit of work, and raises `ValueError` naming both ids if not.
- **Clean exit:** it records the hash, the commit's anomalies and its new units, then commits. Everything written in the block becomes durable together.
- **Any `BaseException`** (including `KeyboardInterrupt`): it rolls back and re-raises. Nothing from the block persists: no case, history, release, hash, anomaly or unit.
- `cases.save_case`, `cases.update_case` and `releases.record_releases` called outside `processing` raise `RuntimeError`.
- `record_anomaly` belongs to the skip path (Q-10). Outside `processing` it commits on its own. Inside `processing` it raises `RuntimeError`, because a processed snapshot's anomalies travel in its `SnapshotCommit`.
- After a rolled-back unit of work, the same snapshot can be processed again on the same instance.

**Case writes**
- `save_case(case, row)` upserts the case and its history row for the open snapshot. It requires `case.last_snapshot_id == row.snapshot_id ==` the open snapshot; otherwise `ValueError`. A second save for the same case and snapshot (a re-run, Q-27) updates both in place.
- Saving a second active case for a combination raises `ValueError` naming the combination (FR-12).
- `update_case(case)` writes only the report baseline (`last_reported_*` and the max). It requires `case.last_reported_at ==` the open snapshot, and raises `ValueError` naming the case if it is unknown.

**Persistence**
- **Anomalies:** stored with their `kind`, `snapshot_id` and `detail`. An anomaly identical in all three is stored once. A rerun that meets the same Q-10 repeat again does not duplicate it. This closes the open note in spec 002. `InMemoryProcessedStore` (spec 002's test fake) dedupes the same way, so both stores honour one contract.
- **Unit identity (Q-20):** `known_units()` returns the first *sighting* of each unit. A later sighting never overwrites it, matching the in-memory store.
- **Released units (FR-05, Q-20):**
  - `releases.record_releases(snapshot)` stores the snapshot's `liberadas` inside its unit of work.
  - `releases.released_so_far()` returns every stored release in release order: snapshot processing order, then list order within a snapshot.
  - It feeds `compute_metrics(snapshot, released_so_far, ctx)`, which counts the first *release* of each unit (spec 002 E21). That is why releases are stored apart from `known_units()`: first sighting and first release can differ.
  - All releases are stored, including repeats. Deduplication stays in `count_progress`, the single place where "first release wins" lives.
- **Schema version:** kept in `PRAGMA user_version`.
  - A new file gets the schema and the current version.
  - Opening a file with another non-zero version raises `ValueError` naming the file, the version found and the version expected. The file is left untouched.
- **Reopen and resume:** a new `SqliteRegistry` on the same file sees everything committed before: hashes, units, anomalies, releases, cases and history. The runner (spec 002) then resumes at the first unmarked snapshot (NFR-10). Case IDs and history are the same as in an uninterrupted run (NFR-04).
- **Registry path:** `Settings.registry_path = output_dir / "registry.sqlite3"`, a derived property with no new environment variable. The caller (spec 012) creates the directory.

**Tracker**
- `CaseTracker(registry.cases, resolution)`.
- `track(snapshot_id, metrics, raises)` applies the lifecycle to every combination in `metrics`, in `all_combinations()` order:
  - It takes the active cases as they were before this snapshot (see re-run below).
  - It advances each active case and opens a case where a combination with no active case has a deviation.
  - It writes each evaluated case and its history row.
  - It returns a `CaseDelta` with the events and the updated cases, including those resolved at this snapshot.
- `raises` holds the combinations with a raise in force at this snapshot. Spec 008 maps a raise's model + stage scope (Q-02) to combinations.
- It must be called inside `processing` for `snapshot_id`. Otherwise it raises `RuntimeError`, even when there is nothing to write.
- An active case whose combination is missing from `metrics` raises `ValueError` naming the case. A case is never left unevaluated without notice.
- **Re-run within a snapshot (Q-27):**
  - `track` may be called again for the same `snapshot_id` inside the same `processing`, with the same `metrics` and different `raises`.
  - The first call for a snapshot reads the active cases and keeps them privately in a memo `(unit, snapshot_id, metrics, active_before, marked)`, stored only after the input checks pass. A later call for that snapshot recomputes from `active_before`, never from what the earlier call wrote. Events are computed against the pre-snapshot state.
  - Each call upserts its rows and returns a full `CaseDelta` that replaces the earlier one.
  - So a raise decided by the agent at N escalates at N, and its alert fires at N (§4). A lift at N can resolve the case at N (Q-25).
  - **Enforced in code:** the memo is keyed by the registry's unit-of-work token (`current_unit()`, a new value on every `processing` entry), so a retry after a rollback starts fresh. A re-run with `metrics` different from the first call raises `ValueError`. A `track` after marking a case that this unit's `track` evaluated raises `RuntimeError`. A resolved case marked before any `track` is not recorded; that is safe while `track` writes only `active_before` cases and new openings (revisit with Q-29).
  - **Contract for specs 004 and 008:** build notices only from the last `CaseDelta`.
- `mark_reported(case_id, snapshot_id)` reads the case, applies the pure `lifecycle.mark_reported` and writes it with `update_case`. Outside `processing` it raises `RuntimeError`; an unknown case raises `ValueError` naming it. An active case not yet tracked at `snapshot_id` (`last_snapshot_id != snapshot_id`) raises `ValueError`; a case resolved earlier keeps its `last_snapshot_id` and can be marked (E24b).
- Every `Case` the lifecycle produces is validated (no `model_copy` without validation), and `save_case` rejects a history row whose `case_id` differs from the case's.

## Worked examples

**Notation**
- PB = Pickup × Brasil, SL = SUV × Local, SeL = Sedán × Local, SeE = Sedán × Europa.
- "min" = minimum severity. "R" = raise in force on the combination at that snapshot. Severities use their data values (`ninguna`, `media`, `alta`, `critica`).
- "streak" = clean streak. "max" = max severity since the last report; "max ∅" = `None`.
- Unless stated otherwise, R is no, and E1–E18 and E32 call `lifecycle.step` with `snapshots_sin_desvio = 2`.
- Synthetic `CombinationMetrics` come from a builder. Only the minimum severity matters unless values are given.
- "The registry" is `SqliteRegistry(":memory:")`; `cases` and `releases` are its collaborators.

| # | Input | Expected |
|---|---|---|
| E1 | US-03 #1. PB has no case. S010: min `media`. | Case `S010-Pickup-Brasil`: `abierto`, `opened_at` S010, current `media`, max `media`, streak 0, raised False. `last_reported_at`, last reported state and last reported severity are `None`. Events `(opened)`. |
| E2 | PB has no case. (a) S010: min `ninguna`. (b) S010: min `ninguna`, R yes. | (a) and (b): no case and no events. A raise alone does not open a case (§2, §3, Q-25). |
| E3 | US-03 #2. E1, then S011: min `media`, then S012: min `alta`. | S011: `en_seguimiento`, current `media`, streak 0, events `()`. S012: `en_seguimiento`, current `alta`, max `alta`, events `(severity_changed)`. |
| E4 | US-03 #3. PB has active case `S010-Pickup-Brasil` (`en_seguimiento`, `media`). S012: min `alta`. | The returned case is still `S010-Pickup-Brasil`; no `opened` event. In the registry, `cases.save_case` with a second active case for PB (`S012-Pickup-Brasil`, `abierto`) raises `ValueError` naming PB. |
| E5 | Two combinations, through `CaseTracker` (no raises). S010: PB `media`, SL `alta`, the rest `ninguna`. S011: PB `ninguna`, SL `alta`. | S010: cases `S010-SUV-Local` (`abierto`, `alta`) and `S010-Pickup-Brasil` (`abierto`, `media`). Events and cases come in `all_combinations()` order, so SL before PB. S011: PB `en_seguimiento`, streak 1, current `ninguna`, events `(severity_changed)`. SL `en_seguimiento`, streak 0, current `alta`, events `()`. |
| E6 | **Changed.** `effective_severity(minimum, raised)` in `domain/cases.py` for the 8 inputs: each of `ninguna`, `media`, `alta`, `critica`, with raised False and True. Plus a `Case` and a `CaseHistoryRow` built with min `media`, raised True. | Not raised: equal to the minimum. Raised: `critica` for all four. The result is ≥ the minimum in all 8 cases (FR-15). The case's `current_severity` and the row's `effective_severity` are `critica`, derived. |
| E7 | Threshold escalation. S010: min `alta`. S011: min `critica`. | S010: `abierto`, events `(opened)`. S011: `escalado`, current `critica`, max `critica`, events `(escalated, severity_changed)`. |
| E8 | Q-08. PB has no case. S010: min `critica`. S011: min `critica`. | S010: case `S010-Pickup-Brasil` opens in `escalado`, current `critica`, events `(opened, escalated)` with exactly one `escalated`. S011: `escalado`, events `()`. |
| E9 | Raise at opening (§5). PB has no case. S010: min `media`, R yes. | Case `S010-Pickup-Brasil` opens in `escalado`: current `critica`, raised True, events `(opened, escalated)`. Its history row has minimum `media` and effective `critica`. |
| E10 | US-03 #4, sticky. E7 (`escalado` at S011, `critica`). S012: min `alta`. S013: min `media`. | S012: `escalado`, current `alta`, max `critica`, events `(severity_changed)`. S013: `escalado`, current `media`, max `critica`, events `(severity_changed)`. Never a second `escalated`. |
| E11 | US-03 #5, resolution. S010: min `media`. S011: min `ninguna`. S012: min `ninguna`. | S011: `en_seguimiento`, streak 1, current `ninguna` (Q-26), events `(severity_changed)`. S012: `resuelto`, streak 2, `resolved_at` S012, current `ninguna`, events `(resolved)`. |
| E12 | Streak broken. S010 `media`, S011 `ninguna`, S012 `media`, S013 `ninguna`, S014 `ninguna`. | Streaks: 0, 1, 0, 1, 2. States: `abierto`, `en_seguimiento`, `en_seguimiento`, `en_seguimiento`, then `resuelto` at S014, not at S012 or S013. |
| E13 | US-03 #6, a raise blocks resolution. S010: min `media`, R yes. S011, S012 and S013: min `ninguna`, R yes. | S010: `escalado`, `critica`. S011: streak 1. S012: streak 2. S013: streak 3. All three stay `escalado`, with current `critica` and events `()`. Never `resuelto`. |
| E14 | Q-25. S010: min `media`, R yes. S011 and S012: min `ninguna`, R yes. S013: min `ninguna`, R no (lifted). Variant: S013 min `media`, R no. | S011 streak 1 and S012 streak 2, both `escalado`, blocked by the raise. S013: `resuelto` at S013, not S014. Streak 3, current `ninguna`, events `(severity_changed, resolved)`. **Variant:** S013 streak 0, `escalado`, current `media`, events `(severity_changed)`. |
| E15 | Q-26 and `escalado` → `resuelto`. E7 (`escalado` at S011, `critica`). S012: min `ninguna`. S013: min `ninguna`. | S012: `escalado`, current `ninguna`, max `critica`, streak 1, events `(severity_changed)`. S013: `resuelto`, events `(resolved)`. |
| E16 | US-03 #7, new case. E11 (`S010-Pickup-Brasil` resolved at S012), then through `CaseTracker`, S013: PB min `media`. | A new case `S013-Pickup-Brasil` opens in `abierto` with events `(opened)`. `cases.get_case("S010-Pickup-Brasil")` is still `resuelto`. `cases.active_cases()` is `(S013-Pickup-Brasil,)`. |
| E17 | **Changed (Q-28).** Max severity between two reports, with the pure `lifecycle.mark_reported`. S010: min `media`, then mark at S010. S011: min `critica`. S012: min `alta`, then mark at S012. S013: min `media`. | S010 before the mark: max `media`, last reported fields `None`. After: `last_reported_at` S010, last reported `abierto` / `media`, max ∅. S011: `escalado`, max `critica`. S012 before the mark: current `alta`, max `critica` (the peak is kept). After: last reported `escalado` / `alta`, max ∅. S013: current `media`, max `media` (S012's `alta` was already reported). |
| E18 | **Changed wording.** Misuse of `step`. (a) A case last evaluated at S011, stepped again with S011. (b) A `resuelto` case, stepped with S013. | (a) `ValueError` naming the case and S011, so a streak is never counted twice. A tracker re-run (E31) never hits this, because it steps from the pre-snapshot state. (b) `ValueError` naming the case. |
| E19 | ProcessedStore contract. `store_factory` parametrized with `InMemoryProcessedStore` and `lambda: SqliteRegistry(":memory:")`. | Every spec 002 E19 contract test passes unchanged for `SqliteRegistry`, and `SqliteRegistry()` type-checks as a `ProcessedStore`. |
| E20 | Anomalies. A = `shift_mismatch` for S001, detail `turno T02, turnos.csv T01`; Q = `repeated_with_different_content` for S034, detail `hash ef, stored hash 01`. (a) Commit S001 with A. (b) `record_anomaly(Q)` twice. (c) On a file: reopen, then `record_anomaly(Q)` again. (d) A commit for S002 carrying B (`shift_mismatch` for S002) whose block raises. | (a) `recorded_anomalies()` is `(A,)`. (b) `(A, Q)`: Q is stored once. (c) Still `(A, Q)`. (d) B is not stored. |
| E21 | Schema version. (a) `SqliteRegistry(tmp_path / "r.sqlite3")` on a new file, closed and reopened. (b) A file whose `user_version` was set to 7. | (a) `PRAGMA user_version` is 1 and the reopen succeeds. (b) `ValueError` naming the file, 7 and 1; the file's `user_version` is still 7. |
| E22 | Case round trip. Inside `processing(S010)`: `cases.save_case` with the E1 case and its history row (gap −4.0, −13.3 %, delay 0.0, bottleneck `montaje`, streak 0). Clean exit. | Inside and after the block: `cases.get_case("S010-Pickup-Brasil")` equals the case (current severity rebuilt from minimum and raised), `cases.active_cases()` is `(case,)`, and `cases.history("S010-Pickup-Brasil")` is `(row,)` with every field equal. `cases.get_case("S999-Pickup-Brasil")` is `None`. |
| E23 | **Changed.** Write guards. (a) `cases.save_case` outside `processing`. (b) `cases.update_case` outside `processing`. (c) `releases.record_releases` outside `processing`. (d) Inside `processing(S010)`, `save_case` with case and row both at S011. (e) `record_anomaly` inside `processing(S010)`. (f) `processing(S011)` entered while `processing(S010)` is open. (g) Inside `processing(S010)`, `update_case` for `S999-Pickup-Brasil` with `last_reported_at` S010. (h) Inside `processing(S010)`, `save_case` with the case at S010 and the row at S009. | (a), (b), (c), (e) and (f): `RuntimeError`, and nothing is written. (d) `ValueError` naming S010 and S011. (g) `ValueError` naming `S999-Pickup-Brasil`. (h) `ValueError` naming S010 and S009. |
| E24 | **Changed (Q-28).** `CaseTracker.mark_reported` persisted. (a) E17's S012 state saved, then `mark_reported("S010-Pickup-Brasil", "S012")` inside `processing(S012)`, clean exit. (b) A case resolved at S011 (mid snapshot), then `mark_reported` for it inside `processing(S012)`. (c) `mark_reported` outside `processing`; and `mark_reported("S999-Pickup-Brasil", "S012")` inside `processing(S012)`. | (a) `get_case` shows `last_reported_at` S012, last reported `escalado` / `alta`, max ∅. `history` has no extra row. (b) Last reported `resuelto` / `ninguna`, `last_reported_at` S012, `last_snapshot_id` still S011, max ∅, no extra row. (c) `RuntimeError`; then `ValueError` naming `S999-Pickup-Brasil`. |
| E25 | Rollback. Inside `processing(S010)`: `releases.record_releases` with U1, then `cases.save_case` (E1 case and row), then `raise RuntimeError("boom")`. Variant: `raise KeyboardInterrupt`. | The error propagates. `get_case` is `None`, `active_cases()` and `history` are `()`, `released_so_far()` is `()`, `get_hash("S010")` is `None` and `known_units()` is `{}`. In both variants, `processing(S010)` then runs again on the same instance and commits. |
| E26 | Reopen and resume. Registry A on `tmp_path / "r.sqlite3"`: S010 (E1 case, release U1, new unit U1), then S011 (min `ninguna`). Close A and open registry B on the same file. | B returns the same `get_hash` for S010 and S011, the same `known_units()`, `active_cases()`, `history` (two rows, S010 then S011), `released_so_far()` and `recorded_anomalies()` as A. `processing(S011)` on B raises `ValueError` naming S011. S012 (min `ninguna`) on B resolves the case with streak 2. |
| E27 | Released units in order. S001 `liberadas`: U1 Sedán × Local 09:10, U2 Sedán × Local 09:40. S002 `liberadas`: U2 SUV × Local 12:00, U3 SUV × Local 13:00. Each recorded in its own unit of work. | `releases.released_so_far()` is `(U1 SeL, U2 SeL, U2 SL, U3 SL)` in that order. Inside `processing(S002)`, before `record_releases`, it is the two S001 releases only. `compute_metrics(S003, released_so_far(), fixture ctx)` with S003 releasing nothing gives SeL progress 2 and SL progress 1: first release wins. A new instance on the same file returns the same tuple. |
| E28 | `Settings(anthropic_api_key="k", output_dir=Path("out")).registry_path` | `Path("out") / "registry.sqlite3"`. No new environment variable and no `.env.example` change. |
| E29 | Tracker. Inside `processing(S010)`, metrics for all 9 combinations: PB min `alta` (gap −6.0, −20.0 %, delay 1.0, bottleneck `montaje`), the rest `ninguna`. (a) Raises `frozenset()`. (b) Raises `{PB}` with PB min `media`. (c) `track("S010", …)` outside `processing`, all `ninguna`. (d) An active PB case, with PB missing from `metrics`. | (a) `CaseDelta`: `snapshot_id` S010, events `((S010-Pickup-Brasil, opened),)`, cases `(case,)`. The stored history row has those values, raised False and streak 0. (b) The case opens in `escalado`, effective `critica`, raised True, events `opened` then `escalated`. (c) `RuntimeError`. (d) `ValueError` naming `S010-Pickup-Brasil`. |
| E30 | **Integration (NFR-04, NFR-10).** Fixture `turnos.csv` (S001–S006, T01–T03) and fixture plan (SeL 12 per shift, SeE 4). No units in plant. `liberadas` empty except S004: 30 SeL units L001–L030. Test pipeline: `releases.released_so_far()` → `compute_metrics` → `releases.record_releases` → `track(…, frozenset())`. **Run U:** uninterrupted, on file U. **Run I1:** on file I, the pipeline raises `RuntimeError` after `track` on S004. **Run I2:** a new `SqliteRegistry` on file I and a healthy pipeline. | **U, SeL:** S001 `abierto` `media` (gap −6, −16.7 %). S002 `en_seguimiento` `alta` (−12, −33.3 %). S003 `escalado` `critica` (−18, −50 %). S004 `escalado` `ninguna`, streak 1 (+6). S005 `resuelto`, streak 2 (gap 0). S006: new case `S006-Sedán-Local`, `abierto` `media` (−6, −16.7 %). **U, SeE:** no case at S001 (−2 units, below `minimo_unidades`). `S002-Sedán-Europa` opens `abierto` `alta` (−4, −33.3 %) and is `escalado` `critica` at S003 (−6, −50 %). **I1:** `RunAborted` at S004. File I holds S001–S003 only, `S001-Sedán-Local` is `escalado` with 3 history rows, and `released_so_far()` is `()`. **I2:** processed `(S004, S005, S006)`, skipped `(S001, S002, S003)`. For every case ID in U, `get_case` and `history` on I equal those on U, and so do `active_cases()` and the set of case IDs. `released_so_far()` has 30 entries, not 60. |
| E31 | **New (Q-27).** Re-run in one snapshot, through `CaseTracker`. S009 committed: PB min `alta` opens `S009-Pickup-Brasil` (`abierto`, `alta`). Inside `processing(S010)`, PB min `alta`, the rest `ninguna`: first `track("S010", m, frozenset())`, then `track("S010", m, {PB})`. Clean exit. | First delta: PB `en_seguimiento`, current `alta`, events `()`. Second delta (replaces the first): PB `escalado`, current `critica`, raised True, events `(escalated, severity_changed)`, computed against S009 (`alta`), with no `ValueError` from the step guard. After commit: `get_case` is `escalado` / `critica`, and `history` has exactly two rows, S009 and S010; the S010 row has state `escalado`, min `alta`, effective `critica`, raised True. |
| E32 | **New (Q-28).** Report at a peak, then lower all next shift. S010: min `critica` (`escalado`), then mark at S010. S011: min `alta`. S012: min `alta`. | S011: current `alta`, max `alta`. S012 before the mark: current `alta`, max `alta`, not `critica`: S010's `critica` was already reported. |

## Edge cases and assumptions
- **Q-08:** a case that opens already critical (by threshold or by a raise in force at opening) opens in `escalado`. Its single `escalated` event is in the opening snapshot (E8, E9).
- **Q-15 (context):** a case cannot open and resolve within one shift. Resolution needs 2 clean snapshots after the opening one, so every case crosses at least one closing snapshot and appears in a report. No special handling.
- **Q-16 (known risk):** a plan-0 shift gives `gap_pct = None` and no gap severity. Two such snapshots can resolve a case that still has a real accumulated shortfall. It does not occur in T01–T21 and is revisited in W5. The lifecycle applies §3 literally.
- **Q-25 (decided):** clean snapshots count toward the streak while a raise is in force. Resolution needs streak ≥ `snapshots_sin_desvio` and no raise at that snapshot (E13, E14).
- **Q-26 (decided):** an active case's current severity is the snapshot's effective severity, even `ninguna`. The drop is a severity change; the max severity since the last report keeps the peak (E11, E15, E17).
- **Q-27 (decided):** `track` can re-run for the same snapshot with different raises; it recomputes from the pre-snapshot state and its last delta replaces earlier ones (E31). A re-run must use the same `metrics`; only `raises` may differ. This is checked in code (`ValueError`), and so is a `track` after marking a case this unit's `track` evaluated (`RuntimeError`).
- **Q-28 (decided):** the max since the last report excludes the report snapshot; it is empty right after a mark and set by the next evaluated snapshot (E17, E24, E32).
- **Q-29 (open, spec 008):** whether the agent may raise at N a case that `track` resolved at N. If spec 008 allows it, the re-run mechanism above keeps the case active, because resolution needs no raise at that snapshot. This spec does not specify or test that outcome.
- Opening and resolving in one transition is impossible: the opening snapshot has a deviation. Escalating and resolving in one snapshot is impossible: resolution needs effective `ninguna`.
- A history row is written only for active cases and their resolution snapshot. A resolved case gets no further rows; marking it as reported writes none either.
- **Q-17 (open, out of scope):** stage of a gap-only `no_declarada` cause. To be decided before spec 004. History stores `bottleneck = None` as computed.
- **Q-24 (open, out of scope):** registry writes from a separate MCP server process cannot join `processing`. To be decided in spec 006.

## Acceptance
- [x] E1–E32 are tests and pass, and every rule above has a passing test.
- [x] `next_state` has a parametrized test over every row of the transition table.
- [x] `store_factory` in `tests/unit/runner/test_store_contract.py` includes `SqliteRegistry(":memory:")`, and the contract tests pass unchanged.
- [x] Import boundaries, checked per module: `cases` imports only `plant_monitor.domain` and `plant_monitor.metrics.thresholds` (and itself). It never imports `runner`, `agents`, `mcp_server`, `anthropic` or `mcp`.
- [x] `docs/diagrams/case-state-machine.md` matches the implementation (Q-08 at opening, the consequence that `abierto` never resolves directly, Q-25, Q-26, Q-28).
- [x] `ruff`, `mypy --strict` and `pytest` pass; `docs/STRUCTURE.md` and the `docs/roadmap.md` row for 003 updated.
