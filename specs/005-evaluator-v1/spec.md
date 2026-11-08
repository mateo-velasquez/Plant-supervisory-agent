# 005 · Evaluator v1 — Spec

- **Status:** Implemented
- **Requirements:** FR-39 (notices and noise; the cause metric arrives in spec 008), FR-40, FR-25 (contract read back), FR-17 (verbatim check of golden evidence), NFR-04, NFR-07
- **Stories:** US-12
- **Decisions:** ADR-0004 (data not versioned), ADR-0006 (dev hook vs product guard), ADR-0010 (outbox), ADR-0011 (the evaluator reads the registry outbox and re-derives noise on its own; golden YAML keyed by opening snapshot). Q-14 (context), Q-17, Q-32 (gap-only causes), and Q-33 to Q-40 (decided here).
- **Week:** W1 (grows weekly)

## Goal
Measure whether a change improved or broke the system. A run's alerts and shift reports are compared against hand-verified golden cases, and a noise metric needs no golden data. The golden data encodes the **full** criteria, including §5 agent raises. Items the current system cannot produce are still scored and shown, but they do not gate. Days 8–10 stay out of everything the evaluator and the smoke run load. The spec also closes research items A1, A3 and A4 and the first golden cases (day 1 and the Europe audit).

## Scope
- **In:**
  - `read_deliverables`: a read-only registry reader in `cases/registry/notices.py`. `RunOutput` and its source, which only applies the held-out refusal (Q-33).
  - `HeldOutPolicy` in `domain/calendar.py`. The `check_ids` guard, the streaming arrivals reader and the logbook text loader in `ingestion/`. New `Settings` fields (Q-37).
  - Golden YAML models with `depends_on` (tracking) and `requires` (capabilities). A loader with file checks, cross-file checks and a verbatim check of golden evidence (Q-34, Q-36).
  - Scoring of alerts and news (Q-35) and of noise (Q-33). Gating by capability.
  - The summary, the metrics table, the JSON summary file and the exit code.
  - A case timeline digest for the smoke run.
  - The eval CLI `evals/run_eval.py` and the smoke run `evals/smoke_days_1_7.py` (A3).
  - The incident catalog (A1), research item A4 (done), and golden cases for day 1 (T01–T03) and for the Europe audit (T07–T10).
- **Out:**
  - **Deferred to spec 008:** scoring the causes of a run (FR-39 cause metric). That covers the cause target, the `categoria`/`etapa` comparison, the notice-evidence verbatim check and the `evidence_missing` rule (Q-36). Spec 005 keeps golden cause items, `contains_verbatim` and the golden-evidence check.
  - Model-in-the-loop runs. From spec 007 on they store through the same outbox and reuse this evaluator.
  - Scoring of `sin_aviso` decisions: they stay queryable in the registry.
  - The logbook store and its availability rule (spec 006, Q-01). Running the held-out days (W5 process step). The dashboard (spec 015).

## Behavior

**Registry reader (Q-33, ADR-0011)**
- `read_deliverables(path)` is a module-level function in `cases/registry/notices.py`. It returns every deliverable row (reports and `alerta_inmediata`), delivered or not, as `Notice | ShiftReport`, ordered by `seq`, `idx`.
- It checks `path.is_file()` first (`ValueError` naming the path, and no file is created). Then it opens SQLite with the URI `mode=ro`, never through `SqliteRegistry`, so it never bootstraps a schema.
- It checks that the `notices` table has the columns it reads (`seq`, `idx`, `kind`, `tipo`, `payload`) instead of the whole `user_version`. A missing table or column raises `ValueError` naming the file and what is missing.
- Rows are filtered by the module constant `DELIVERABLE_FILTER` (`kind = 'report' OR tipo = 'alerta_inmediata'`). `pending()` uses the same constant plus `delivered_at IS NULL`, so "deliverable" is defined once. `pending()` behavior is unchanged (004 tests).
- Payloads are parsed with the contract models, so their validators run. A parse error raises `ValueError` naming the file. The file is never modified.

**Run output and its source (Q-33)**
- `RunOutput` is pure: `alerts` (`Notice`, all `alerta_inmediata`) and `reports` (`ShiftReport`), each in processing order.
- Validation (`ValueError`):
  - every alert has `tipo = alerta_inmediata`;
  - alert `notice_id`s are unique;
  - report `turno_id`s are unique.
- It does **not** enforce one alert per case: detecting duplicates is the scorer's job.
- `load_run_output(path, policy)` calls `read_deliverables`, turning its `ValueError` into a `DataLoadError`.
  - Any item whose `snapshot_id` is in `policy.refused_snapshots` raises `DataLoadError` ("held out").
  - It splits the items into `RunOutput`.
  - It has no SQL of its own.
- Mid-snapshot `informe_de_turno` and `sin_aviso` rows are never read. The `FileNotifier` output is never read.

**Held out (FR-40, Q-37)**
- `HeldOutPolicy.from_calendar(shifts, first_shift, is_open)` lives in `domain/calendar.py`:
  - held-out shifts are `first_shift` and every shift whose `inicio` is later;
  - held-out snapshots are their `snapshot_medio` and `snapshot_cierre`;
  - allowed snapshots are those of every other shift;
  - an unknown `first_shift` raises `ValueError`;
  - `refused_shifts` and `refused_snapshots` equal the held-out sets while closed and are empty while open.
  - Specs 006 and 012 reuse it.
- `check_ids(policy, *, shifts, snapshots, where)` lives in `ingestion/held_out.py`. It raises `DataLoadError` naming `where`, the first refused id in sorted order, and "held out".
- `Settings.heldout_open` (env `HELDOUT_OPEN`, default `False`) is the product guard, and `Settings.heldout_first_shift` (env `HELDOUT_FIRST_SHIFT`, default `T22`) sets the first held-out shift. Claude Code's tools are limited separately by `CLAUDE_ALLOW_HELDOUT` in the dev hook. Neither setting sets the other.
- **Golden loader:** while closed, a file naming a refused shift or snapshot raises `DataLoadError` ("held out") naming the file and the id. That covers `covers`, `turno_id`, `snapshot_id`, `abre_en` and `evidencia.bitacora`. The check runs after schema parsing and before every semantic check.
- **Run source:** refuses items of refused snapshots (above).
- **Logbook loader** (`read_logbook_texts(directory, turno_ids, policy)` in `ingestion/logbooks.py`):
  - `check_ids` runs on every requested id before any file is opened;
  - it reads `<turno_id>.txt` as `utf-8-sig` with universal newlines;
  - it raises `DataLoadError` for a missing file;
  - spec 006's logbook store must load through it.
- **Arrivals reader** (`load_arrivals_until(path, policy)` in `ingestion/arrivals.py`) streams `llegadas.csv` row by row (BOM handled). It stops right after the row that completes `policy.allowed_snapshots`, and it never parses a later row.
  - Errors (`DataLoadError` with the physical line, header = 1):
    - row k (1-based) does not have `orden == k`;
    - a row names a held-out snapshot (`held_out_snapshots`, checked even when the policy is open: the smoke run reads days 1–7 only);
    - the file ends before the set is complete (naming the missing snapshots);
    - a schema error in a row read.
  - Empty `allowed_snapshots` raises `ValueError`.
  - **Limitation:** a repeat of an allowed snapshot that arrives after the last first-time arrival is not read. This does not happen in days 1–7: the set completes at row 43 (`S042`), and the `S034` repeat is row 35.

**Golden cases (Q-34, Q-36)**
- Golden files are `evals/golden/*.yaml`, loaded in name order. Other files, such as `incidents.md`, are ignored. A directory with no `.yaml` file is an error.
- A file has:
  - `covers`: the shifts it covers, non-empty and unique;
  - optional `alerts`, `news` and `causes` lists;
  - an optional free-text `notes`.
- **Every item** has:
  - `justification` (required): after stripping, non-empty and containing `criterio` followed by a space and a number (case-insensitive), e.g. `criterio 4`; golden analyses (`notes`, `justification`, `incidents.md`) are written in Spanish and never use the section sign;
  - optional `id`: lowercase letters, digits, `_` and `-`, unique across the set;
  - optional `depends_on`: unique `Q-xx` ids, for **tracking only**;
  - optional `requires`: unique values of the closed enum `Capability`, which has the single value `agent` for now. It marks behavior only the agent can produce: §5 raises and their effects, and declared causes with citations.
- Item fields:
  - **Case key:** `case: {modelo, mercado, abre_en}`. Its `case_id` is `case_id_for(abre_en, combination)`, e.g. `S001-Sedán-Local`.
  - **Expected alert:** `case`, `snapshot_id`, optional `motivo` (list).
  - **Expected news:** `turno_id`, `case`, `estado`, `severidad`, `severidad_maxima`.
  - **Expected cause:** `case`, `notice` (`alerta_inmediata` or `informe_de_turno`), `turno_id` (required for `informe_de_turno`, forbidden for `alerta_inmediata`), `categoria`, `etapa` (required, nullable), and `evidencia: {bitacora, fragmento}`. `evidencia` is required when `categoria` is not `no_declarada` (FR-17, §6 "se cita el fragmento") and forbidden for `no_declarada` (§6: no logbook names it).
- **Types:**
  - Models are `frozen` with `extra = forbid`, but not strict at model level.
  - Ids and text are strict strings with a shape pattern (`S\d{3}`, `T\d{2}`, `Q-\d{2,}`). So `abre_en: 1` is an error.
  - Enums and lists are lax: YAML strings map to the contract enums, and YAML lists become tuples. A bare string where a list is expected (`covers: T01`) is still an error.
  - A duplicate key in a YAML mapping is an error, not a silent overwrite.
- **Shape vs calendar:** the regex checks only shape, at parse time. Membership in the calendar is checked only by the semantic checks (held out, coverage, snapshot order). Neither repeats the other.
- **Checks within a file:**
  - news and cause `turno_id`s are in `covers`;
  - an alert's `snapshot_id` is a mid or closing snapshot of a covered shift;
  - `abre_en` is a calendar snapshot no later than the alert's snapshot, or than the news shift's closing snapshot;
  - (`turno_id`, `case_id`) is unique among news items;
  - news `severidad_maxima ≥ severidad`;
  - news `estado = resuelto` implies `severidad = ninguna` (§3, Q-26);
  - an `informe_de_turno` cause has a news item for the same (`turno_id`, `case_id`) in the same file.
- **Checks across files:**
  - no shift is covered by two files;
  - an alert `case_id` appears at most once in the set (§4: one per case);
  - an `alerta_inmediata` cause has an alert item for its case in the set;
  - (`case_id`, `notice`, `turno_id`) is unique among causes;
  - item `id`s are unique.
- **Golden evidence (Q-36):** `load_golden` takes an injected `logbooks` callable (`frozenset[str] → Mapping[str, str]`). After every other check, it calls the callable once with the set of cited `bitacora`s, and not at all when nothing is cited. Every golden fragment must satisfy `contains_verbatim(text, fragmento)`; otherwise it raises `DataLoadError` naming the item label and the logbook. Held-out logbooks are refused before that, by the held-out check, and again by `read_logbook_texts`.
- **Verbatim:** `contains_verbatim(text, fragment)` is true when the fragment, normalized, is a substring of the text, normalized. Normalizing collapses every run of Unicode whitespace (including line breaks) to one space and strips the ends. The check is case-sensitive, with no accent folding. An empty fragment is never found. Spec 008 reuses it for notice evidence.
- Every load error is a `DataLoadError` naming the file and the field path (e.g. `day_01.yaml: news[2].turno_id: T05 is not in covers`).
- **Labels:** `<file>#<id>` when the item has an `id`, else `<file>#<section>[<index>]` (e.g. `day_01.yaml#news[1]`). Every result uses them.
- **Authoring:** justifications are quoted in YAML, because `criterio 4: …` has a colon. The header of `incidents.md` says so.

**Alerts (FR-39, §4, Q-35)**
- **Scope:** the snapshots of covered shifts (mid and closing).
- For each expected alert (case c, snapshot s), let A be every run alert with `case_id == c`, at any snapshot:
  - `hit`: |A| = 1 and its snapshot is s;
  - `missing`: |A| = 0;
  - `wrong_snapshot`: |A| ≥ 1 and none at s. One error.
  - `duplicate`: one at s and |A| ≥ 2. It contributes `duplicates = |A| − 1`.
- A run alert whose `case_id` matches no expected alert is `extra` when its snapshot is in scope, else `unscored`.
- A case opened at another snapshot has another `case_id`, so it gives one `missing` plus one `extra` when in scope.
- **Attribute:** for a hit, when the golden gives `motivo`, a different list contributes one `motivo_mismatch`. That is not an error.
- Error keys: `missing`, `wrong_snapshot`, `duplicates`, `extra`.

**News (FR-39, §4, Q-35)**
- For each covered shift T, take the run report with `turno_id == T`:
  - **No report:** a `missing_report` result for T, and each expected news item of T is `missing`.
  - **Otherwise:** expected set E (golden `case_id`s of T) and actual set N (`novedades` `case_id`s). E ∩ N are hits, E − N are `missing`, and each case in N − E is an `extra` result.
- For a hit, compare `estado`, `severidad` and `severidad_maxima` exactly. Each difference contributes one `estado_mismatch`, `severidad_mismatch` or `maxima_mismatch`. These are not errors.
- Reports of uncovered shifts are `unscored_report` results.
- Error keys: `missing`, `extra`, `missing_report`. A missing report also counts its expected items as missing, so a covered shift is never silently clean.
- Alerts and news are scored independently: a case that escalates at a closing snapshot is expected both as an alert and as a news item of that report (Q-14).

**Noise (FR-39, §4 "Sin aviso", Q-33)**
- No golden data. Reports in `RunOutput` order; the first report is never counted.
- For k ≥ 2, a news item n for case c in R_k is a **repeat** when all of these hold:
  - c has a row r in R_{k−1}'s `casos_activos`;
  - `norm(r.estado) == norm(n.estado)`, where `norm` maps `abierto` and `en_seguimiento` to one value;
  - `r.severidad == n.severidad`;
  - `n.severidad_maxima == n.severidad`;
  - `n.estado != resuelto`.
- **Duplicate alerts:** for each `case_id` with m ≥ 2 alerts, one entry `(case_id, m)`. These are reported only: against the golden they are already counted as `duplicates`, so they never add to the gate.
- Noise errors = the number of repeats.
- `evaluation/` never imports `cases.novelty`. The definition is written out again over the contract.

**Results, tallies and gating (Q-34, Q-35)**
- Scoring returns **results**, never counts.
  - Each result has its section (`alerts` or `news`), a golden label (or `None`), `case_id`, its snapshot or shift, its contributions (e.g. `{hit: 1, motivo_mismatch: 1}` or `{duplicates: 2}`), the item's `depends_on`, and `gated`.
  - Extra, unscored, missing-report and unscored-report results have no label.
- `tally(results, *, gated=None, question=None)` sums contributions over the results that match the filters. The table, the JSON and `gating_errors` are all built from tallies.
- **Gating (Q-35):** a golden result is `gated` when its item's `requires` ⊆ the run's capabilities (`--capabilities`, default none). An extra result is not gated when the same `case_id` has any golden item whose `requires` is unmet (E39). Every other result is gated.
- `depends_on` never affects gating: it only feeds the per-question tallies (`question="Q-26"`).
- `gating_errors` = gated alert errors + gated news errors + noise repeats.
- `exit_code(summary)` is 0 when `gating_errors == 0`, else 1. Attribute mismatches and duplicate alerts in noise never gate. The CLI returns 2 on a load error.
- `render_table(summary)` gives one plain-text table with sections `alerts`, `news` and `noise`. Alerts and news have `gated` and `not gated` columns, followed by one line per question in `depends_on`.
- `write_summary(summary, directory, at)` writes `<directory>/eval-<YYYYMMDDTHHMMSSZ>.json`:
  - UTF-8, `ensure_ascii=False`, indent 2, LF, one trailing newline;
  - `at` must be timezone-aware, converted to UTC;
  - the directory is created if missing.

**Case timeline (smoke digest)**
- `case_timeline(run)` returns, per `case_id`:
  - `first_reported_in`: the first report that lists the case in `novedades` or `casos_activos`;
  - `alerted_at`: the snapshots of its alerts, in order;
  - `resolved_in`: the report whose news gives it `estado = resuelto`, or `None`.
- Ordered by first appearance (an alert or a report entry, in processing order), then `case_id`.

**Eval CLI (`evals/run_eval.py`)**
- `--registry <path> --golden <dir> [--capabilities agent[,…]]`. It is a thin wrapper: it reads `get_settings()` and calls `evaluation.cli.run_eval(...)` with keyword-only arguments taken from settings:
  - `plant_dir/turnos.csv`;
  - `logbooks_dir`;
  - `heldout_first_shift` and `heldout_open`;
  - `evals_dir` as the output directory.
- `run_eval`:
  1. loads the calendar and builds the policy;
  2. loads the run output;
  3. loads the golden set, with `logbooks = lambda ids: read_logbook_texts(logbooks_dir, ids, policy)`;
  4. scores, prints the table, writes the summary and returns the exit code.
- A `DataLoadError`, or the policy's `ValueError`, prints one line to stderr, writes no summary and returns 2.

**Smoke run A3 (`evals/smoke_days_1_7.py`)**
- On demand, never in CI (NFR-07). The **user** runs it: `get_settings()` reads `.env`.
- Steps:
  1. Load the plant files in full and the thresholds.
  2. Build the policy.
  3. Read arrivals with `load_arrivals_until(snapshots_dir/llegadas.csv, policy)`.
  4. `out = evals_dir/smoke-<UTC timestamp>`, then `out.mkdir(parents=True)` (it fails if `out` exists).
  5. Open `SqliteRegistry(out/registry.sqlite3)` and run `run_series(..., ThresholdPipeline.from_registry(...), post_commit=OutboxDispatcher(registry.notices, FileNotifier(out/notices)))`. Read `pending()` before closing.
  6. After the registry is closed, print processed, skipped (the second `S034` arrival is expected here) and anomalies, then the `case_timeline` of `load_run_output(out/registry.sqlite3, policy)`.
  7. Exit 1 if `pending` is not empty (printing the ids); exit 2 with one printed line on `RunAborted` or `DataLoadError`; else 0.
- Its output is a starting point for golden cases, never their source: golden cases built from the system's own output would be circular.

## Worked examples

**Notation**
- Fixture calendar (`tests/fixtures/plant/turnos.csv`): T01 = (S001 mid, S002 closing), T02 = (S003, S004), T03 = (S005, S006).
- Combinations: SeL = Sedán × Local, SL = SUV × Local, SE = SUV × Europa, PL = Pickup × Local, PB = Pickup × Brasil.
- `X@Sn` is the case of combination X opened at Sn. Its `case_id` is `case_id_for("Sn", X)`, e.g. SeL@S001 = `S001-Sedán-Local`.
- **Run items** are contract-valid objects built with test builders:
  - `alert(X@Sn, Sm)` is an `alerta_inmediata` at Sm (`escalado` / `critica`, `motivo [gap]`, cause `{no_declarada, null}`) unless stated;
  - `news(X@Sn, estado/sev/max)` is an `informe_de_turno` in its report, with a valid `motivo`;
  - `row(X@Sn, estado/sev)` is an `ActiveCaseRow`;
  - `R(T, S; novedades; casos_activos)` is a `ShiftReport`.
- **Golden items:** `A(X@Sn, Sm)` is an expected alert, `N(T, X@Sn, estado/sev/max)` an expected news item, and `C(...)` an expected cause. Each has a valid `justification` and no `requires` unless stated.
- "Policy T03" is `HeldOutPolicy.from_calendar(fixture shifts, "T03", is_open=False)`, and "open policy" is the same with `is_open=True`.
- "No logbooks" is a `logbooks` callable that fails the test if called.
- Unless stated, golden covers T01–T03, capabilities are none, and "errors" means gated errors.

| # | Input | Expected |
|---|---|---|
| E1 | **Golden load.** Directory with `incidents.md` and `day_01.yaml`: `covers: [T01, T02]`. `alerts`: one item, `id: sel-escalates`, case `{modelo: Sedán, mercado: Local, abre_en: S001}`, `snapshot_id: S003`, `motivo: [gap]`, `justification: "criterio 2 y 4: escala en S003, gap -18 u (-50 %) llega a critica (35 %)"`. `news`: `{turno_id: T01, case: SeL@S001, estado: en_seguimiento, severidad: alta, severidad_maxima: alta, justification: "criterio 4: caso nuevo; criterio 2: gap -12 u (-33 %) es alta"}` and `{turno_id: T02, case: SeL@S001, estado: escalado, severidad: critica, severidad_maxima: critica, justification: "criterio 3 y 4: cambian estado y severidad"}`. `causes`: `{case: SeL@S001, notice: alerta_inmediata, categoria: no_declarada, etapa: null, justification: "criterio 6: ninguna bitácora nombra la causa; solo gap, sin cuello", depends_on: [Q-17]}`. Fixture shifts, open policy, no logbooks. | `GoldenSet` with covered shifts `(T01, T02)`; one alert, `case_id` `S001-Sedán-Local`, label `day_01.yaml#sel-escalates`, `motivo (gap,)`, `requires ()`; two news items labeled `day_01.yaml#news[0]` and `[1]`; one cause with `etapa None` and `depends_on ("Q-17",)`. `incidents.md` is ignored, and the logbook callable is never called. |
| E2 | **Golden schema and file checks.** One file each, otherwise as E1: (a) an alert with an extra key `severity: alta`; (b) a news item without `justification`; with `justification: "   "`; with `justification: "caso nuevo"` (no `criterio N`); with `justification: "criterio: caso nuevo"` (no number); (c) news `turno_id: T03` while `covers: [T01, T02]`; (d) an alert at S005 while `covers: [T01, T02]`; (e) two alerts for SeL@S001; (f) news `severidad: alta`, `severidad_maxima: media`; (g) news `estado: resuelto`, `severidad: media`; (h) `depends_on: [Q17]`; `depends_on: [Q-17, Q-17]`; `requires: [model]`; `requires: [agent, agent]`; (i) the YAML key `snapshot_id` written twice in one alert; (j) `abre_en: 1`; `covers: T01`; `modelo: Camión`; (k) a cause without `etapa`; (l) an `informe_de_turno` cause without `turno_id`; an `alerta_inmediata` cause with `turno_id: T02`; (m) an `informe_de_turno` cause for (T02, SeL@S001) with no such news item; (n) an alert SeL@S004 at S003 (opened after the alert); (o) an empty file; a file whose top level is a list; (p) a directory with only `incidents.md`; (q) a `retencion_de_calidad` cause without `evidencia`; a `no_declarada` cause with `evidencia`; (r) `id: "Sel Escalates"`. | Each raises `DataLoadError` naming the file (for (p), the directory) and the field path, e.g. (c) `day_01.yaml: news[0].turno_id: T03 is not in covers`; (i) names the duplicate key `snapshot_id`. |
| E3 | **Cross-file checks.** (a) `day_01.yaml` covers `[T01, T02]`, `day_02.yaml` covers `[T02, T03]`. (b) Both files have an alert for SeL@S001 (one at S003, one at S005; the files cover T02 and T03 respectively). (c) `day_02.yaml` has an `alerta_inmediata` cause for PL@S001 and no file has an alert for PL@S001. (d) Two identical `alerta_inmediata` causes for SeL@S001 in two files. (e) The same `id` in two files. | (a) `DataLoadError` naming T02 and both files. (b) `DataLoadError` naming `S001-Sedán-Local` and both files. (c) `DataLoadError` naming `day_02.yaml#causes[0]` and `S001-Pickup-Local`. (d), (e) `DataLoadError` naming both labels. |
| E4 | **Held-out policy (`domain/calendar.py`).** Fixture shifts given in the order T03, T01, T02. (a) First shift T03, closed. (b) First shift T02, closed. (c) First shift T03, open. (d) First shift `T09`. | (a) `held_out_shifts {T03}`, `held_out_snapshots {S005, S006}`, `allowed_snapshots {S001, S002, S003, S004}`, `refused_shifts {T03}`, `refused_snapshots {S005, S006}`, `known_shifts {T01, T02, T03}`. (b) `held_out_shifts {T02, T03}`, `held_out_snapshots {S003, S004, S005, S006}`, `allowed_snapshots {S001, S002}`. (c) The same held-out and allowed sets as (a); `refused_shifts` and `refused_snapshots` are empty. (d) `ValueError` naming `T09`. |
| E5 | **Held-out refusal: `check_ids` and the golden loader.** Policy T03. (a) `check_ids(policy, shifts=[T02, T03], snapshots=[], where="x.yaml")`. (b) A file with `covers: [T02, T03]` and valid items. (c) A file covering `[T02]` with an alert at S005. (d) A file covering `[T02]` with a valid T02 news item and a `retencion_de_calidad` cause on it with `evidencia: {bitacora: T03, fragmento: "x"}`. (e) (b) with the open policy. (f) (a) with the open policy. | (a) `DataLoadError` naming `x.yaml`, `T03` and "held out". (b) `DataLoadError` naming the file, `T03` and "held out". (c) `DataLoadError` naming `S005` and "held out" (the held-out check runs before the coverage check). (d) `DataLoadError` naming `T03` and "held out"; the logbook callable is never called. (e) Loads. (f) Returns `None`. |
| E6 | **Arrivals reader, happy path.** `llegadas.csv` written as UTF-8 **with BOM**: header `orden,snapshot_id,archivo,recibido`; rows `1,S001,S001.json,2026-03-02T10:02`, `2,S002,S002.json,2026-03-02T14:01`, `3,S003,S003.json,2026-03-02T18:03`, `4,S003,S003.json,2026-03-02T18:30`, `5,S004,S004.json,2026-03-02T22:02`, `6,S005,S005.json,not-a-date`. `load_arrivals_until(path, policy T03)` (allowed S001–S004). | Five `Arrival`s with `orden` 1–5; `snapshot_id`s are S001, S002, S003, S003, S004 (the repeat comes before the set completes), and `archivo` is `<dir>/S00x.json`. Row 6 is never parsed (its bad date raises nothing). The file handle is closed on return: the file can be deleted right after the call (Windows). The same result with the open policy. |
| E7 | **Arrivals reader, errors and limitation.** E6's file with changes, policy T03 unless stated: (a) rows in the order orden 1, 3, 2, 4, 5. (b) Row 4 is `4,S005,S005.json,2026-03-02T18:30`. (b2) The same with the open policy. (c) Only rows 1–4. (d) The first row has `orden` 2. (e) Row 2 has `recibido` `yesterday`. (f) A policy whose first held-out shift is T01 (`allowed_snapshots` empty). (g) Rows `1,S001`, `2,S002`, `3,S003`, `4,S004`, `5,S003` (a late repeat), then `6,S005,…,not-a-date`. | (a) `DataLoadError`: line 3, `orden` 3, expected 2. (b), (b2) `DataLoadError`: line 5, `S005` is held out. (c) `DataLoadError`: the file ends before the set is complete, naming `S004`. (d) `DataLoadError`: line 2, `orden` 2, expected 1. (e) `DataLoadError`: line 3, field `recibido`. (f) `ValueError`. (g) Four arrivals (S001–S004); row 5 is not read: the documented limitation. |
| E8 | **Logbook texts.** Directory with `T01.txt` = bytes `EF BB BF` + `Línea 1\r\nLínea 2\r\n`. (a) `read_logbook_texts(dir, [T01], open policy)`. (b) `[T02]` (no file). (c) `[T01, T03]` with policy T03, where `T03.txt` does not exist. (d) `["./T03"]` and `["t03"]` (non-canonical ids). | (a) `{"T01": "Línea 1\nLínea 2\n"}`: no BOM, LF only. (b) `DataLoadError` naming `T02.txt`. (c) `DataLoadError` naming `T03` and "held out", not "not found": the refusal comes before any file is opened. (d) `DataLoadError` naming the id: only exact calendar shifts (`known_shifts`) are read, checked before the held-out refusal and before any file access. |
| E9 | **Run source.** E40's registry. (a) `load_run_output(path, open policy)`. (b) Policy whose refused snapshots contain S004 (`HeldOutPolicy.from_calendar(fixture shifts, "T02", False)`). (c) A missing path. (d) A SQLite file with no `notices` table. | (a) `alerts = (S003-alerta_inmediata-S001-Sedán-Local,)` and `reports = (T01, T02)`, each equal to what was saved. (b) `DataLoadError` naming a refused snapshot (`S003`, the first item of a refused snapshot) and "held out". (c) `DataLoadError` naming the path; the path still does not exist. (d) `DataLoadError` naming the file and `notices`. |
| E10 | **`RunOutput` validation.** (a) `alerts` holds an `informe_de_turno` notice. (b) Two reports with `turno_id` T01. (c) The same alert twice. (d) Alerts for SeL@S001 at S003 and at S005. | (a), (b), (c): `ValueError`. (d) Builds: duplicates are scored, not rejected. |
| E11 | **US-12 #1, alert hit.** Golden `A(SeL@S001, S003)`. Run alerts `(alert(SeL@S001, S003),)`. | Result `hit`; alerts `tally(gated=True)` is `{hit: 1}`; errors 0. |
| E12 | **Missing alert.** E11's golden; run alerts `()`. | Result `missing`; errors 1. |
| E13 | **Wrong snapshot.** E11's golden; run `(alert(SeL@S001, S004),)`. | Result `wrong_snapshot`; no `missing`, `extra` or `hit`; errors 1. |
| E14 | **Duplicate.** E11's golden. (a) Run `(alert(SeL@S001, S003), alert(SeL@S001, S005))`. (b) Alerts at S003, S004 and S005. | (a) Result `duplicate` with `duplicates 1`, no `hit`; errors 1. (b) `duplicates 2`; errors 2. |
| E15 | **Extra and unscored.** (a) E11's golden; run `(alert(SeL@S001, S003), alert(SL@S002, S004))`. (b) Golden covers T01–T02 only; run `(alert(SeL@S001, S003), alert(SL@S002, S005))`. | (a) `hit 1`, one `extra` result for `S004-alerta_inmediata-S002-SUV-Local`; errors 1. (b) `hit 1`, one `unscored` result; errors 0. |
| E16 | **Opened at another snapshot.** E11's golden; run `(alert(SeL@S002, S003),)`. | `missing` (`S001-Sedán-Local`) and an `extra` (`S003-alerta_inmediata-S002-Sedán-Local`); errors 2. |
| E17 | **Alert `motivo` attribute.** (a) Golden `A(SeL@S001, S003)` with `motivo: [gap]`; the run alert has `motivo [gap, retraso]`. (b) The same golden without `motivo`. | (a) `{hit: 1, motivo_mismatch: 1}`; errors 0. (b) No `motivo_mismatch`. |
| E18 | **Escalation at a closing snapshot (Q-14).** Golden covers T02: `A(SeL@S001, S004)` and `N(T02, SeL@S001, escalado/critica/critica)`. (a) Run: `alert(SeL@S001, S004)` and `R(T02, S004; [news(SeL@S001, escalado/critica/critica)]; [row(SeL@S001, escalado/critica)])`. (b) The alert, with `R(T02, S004; []; [row(SeL@S001, escalado/critica)])`. (c) The (a) report, no alert. | (a) Alert `hit`, news `hit`; no errors. (b) Alert `hit`; news `missing`. (c) Alert `missing`; news `hit`. Scored independently. |
| E19 | **US-12 #2, missing and extra news.** Golden covers T01: `N(T01, SeL@S001, en_seguimiento/alta/alta)` and `N(T01, PL@S001, en_seguimiento/media/media)`. Run `R(T01, S002; [news(SeL@S001, en_seguimiento/alta/alta), news(SL@S002, abierto/alta/alta)]; …)`. | `hit 1`, `missing 1` (`S001-Pickup-Local`), `extra 1` (`S002-SUV-Local`); errors 2. |
| E20 | **Attribute mismatch.** Golden `N(T01, SeL@S001, en_seguimiento/alta/alta)`. Run news `SeL@S001 abierto/media/alta`. | `{hit: 1, estado_mismatch: 1, severidad_mismatch: 1}` (exact comparison: `abierto` ≠ `en_seguimiento` here); errors 0. |
| E21 | **Two news items of one combination.** PB@S001 resolves at S003 (clean at S002 and S003, §3), and a new deviation opens PB@S004 at S004. Golden covers T02: `N(T02, PB@S001, resuelto/ninguna/ninguna)` and `N(T02, PB@S004, abierto/media/media)`. Run `R(T02, S004; novedades; …)` with: (a) both; (b) only `S004-Pickup-Brasil`; (c) `S001-Pickup-Brasil` and `S003-Pickup-Brasil` (`abierto/media/media`). | (a) `hit 2`, errors 0. (b) `hit 1`, `missing 1` (`S001-Pickup-Brasil`), no `extra`. (c) `hit 1`, `missing 1` (`S004-Pickup-Brasil`), `extra 1` (`S003-Pickup-Brasil`). `abre_en` tells the cases apart. |
| E22 | **Covered shifts.** Golden covers T01 and T02, with news items only for T01 (`N(T01, SeL@S001, en_seguimiento/alta/alta)`); T02 expects no news. (a) Run has the matching T01 report and no T02 report. (b) Run adds `R(T02, S004; []; …)`. (c) Run adds `R(T02, S004; [news(SL@S002, en_seguimiento/alta/alta)]; …)`. (d) Run has no report at all. | (a) `missing_report 1` (T02); errors 1. (b) Errors 0. (c) `extra 1`; errors 1. (d) `missing_report 2` (T01, T02), `missing 1`; errors 3. |
| E23 | **Uncovered shift.** Golden covers T01 only, with E22's T01 item and no alert. Run: the matching T01 report, `R(T02, S004; [three news items]; …)` and `alert(SeL@S001, S003)`. | News errors 0, `unscored_report 1` (T02). Alerts: no `extra`, `unscored 1`. Noise still runs over both reports (E24). |
| E24 | **US-12 #4, noise repeat.** `R1 = R(T01, S002; …; [row(SL@S002, abierto/alta)])`. `R2 = R(T02, S004; [news(SL@S002, en_seguimiento/alta/alta)]; [row(SL@S002, en_seguimiento/alta)])`. No golden. | `repeats ((T02, S002-SUV-Local, previous T01),)`; noise errors 1: `abierto` ≡ `en_seguimiento`, same severity, no peak. |
| E25 | **Noise non-repeats.** R1 at T01 with rows `SeL@S001 en_seguimiento/alta`, `PL@S001 en_seguimiento/media`, `PB@S001 en_seguimiento/ninguna`. R2 at T02, each news item in its own variant: (a) `news(SeL@S001, escalado/critica/critica)`; (b) `news(PL@S001, en_seguimiento/alta/alta)`; (c) `news(PL@S001, en_seguimiento/media/alta)`; (d) `news(SL@S003, abierto/media/media)` (not in R1); (e) `news(PB@S001, resuelto/ninguna/ninguna)`. (f) R1 alone, with news repeating its own rows. (g) Three reports: R1 row `SL@S002 en_seguimiento/alta`, R2 row `SL@S002 en_seguimiento/media` with news `SL media/media`, and R3 news `news(SL@S002, en_seguimiento/alta/alta)`. | (a) State change. (b) Severity change. (c) Peak. (d) New case. (e) Resolved. (f) The first report is never compared. (g) R3 is compared with R2 (`media` → `alta`), not with R1, and R2's news against R1 (`alta` → `media`) is a severity change. Repeats are 0 in every variant. |
| E26 | **Duplicate alerts, no golden.** Alerts `(alert(SeL@S001, S003), alert(SeL@S001, S005), alert(PL@S001, S004))`, no golden alert items, golden covers T01 only. | `duplicate_alerts ((S001-Sedán-Local, 2),)`; noise errors 0; `gating_errors` 0 (both SeL alerts are `unscored` here, outside T01). |
| E27 | *Moved to spec 008* (cause hit against a run notice). | — |
| E28 | *Moved to spec 008* (`categoria` miss). | — |
| E29 | *Moved to spec 008* (notice-evidence failures). | — |
| E30 | **Verbatim check and golden evidence (Q-36).** `contains_verbatim` with `text = "Producción: 40 de 45.\nAuditoría de homologación: retuvo en calidad\nlas SUV de exportación hasta nuevo aviso.\n"` (synthetic): (a) `"retuvo en calidad las SUV de exportación"`; (b) `"retuvo  en calidad\tlas SUV"`; (c) `"Retuvo en calidad"`; (d) `"retuvo las SUV en calidad"`; (e) `""` and `"   "`. Golden file `day_02.yaml` covering T02 with `N(T02, SE@S003, abierto/alta/alta, requires [agent])` and a cause on it: `informe_de_turno`, T02, `retencion_de_calidad`, `calidad`, `requires: [agent]`, `evidencia {T02, fragmento}`; the logbook callable returns `{"T02": text}`: (f) fragment (a); (g) fragment `"retuvo en calidad las SUV para Europa"`. | (a) True: the line break is normalized. (b) True. (c) False: case-sensitive. (d) False. (e) False. (f) Loads; the callable was called once, with `frozenset({"T02"})`. (g) `DataLoadError` naming `day_02.yaml#causes[0]` and `T02`. |
| E31 | *Moved to spec 008* (gap-only `no_declarada` scored against a run alert). Golden items for it are valid now (E1). | — |
| E32 | **`depends_on` is tracking only.** Golden: `A(SeL@S001, S003)` and `N(T01, PB@S001, en_seguimiento/ninguna/media)` with `depends_on: [Q-26]`. Run: the alert and `R(T01, S002; []; …)`. Variant: the news item has `depends_on: [Q-17, Q-26]`. | Alert `hit`. News `missing 1`, gated. `tally(news, question="Q-26")` is `{missing: 1}`. `gating_errors` 1, so `exit_code` 1. Variant: the gated tally still counts `missing 1` once, and both `Q-17` and `Q-26` tallies have `missing 1`. |
| E33 | **Gating.** Summaries with: (a) no errors anywhere; (b) only attribute mismatches and a noise `duplicate_alerts` entry; (c) one gated extra news item; (d) one noise repeat; (e) one gated alert duplicate; (f) only errors on items with `requires: [agent]` and capabilities none. | `exit_code`: (a) 0, (b) 0, (c) 1, (d) 1, (e) 1, (f) 0. |
| E34 | **Summary file and table.** E32's summary. (a) `write_summary(summary, tmp/evals, at=2026-11-07T09:00:00-03:00)`. (b) `at` naive. (c) `render_table(summary)`. | (a) Writes `tmp/evals/eval-20261107T120000Z.json` (directory created). The parsed JSON has keys `registry`, `golden`, `capabilities`, `covered_shifts`, `alerts`, `news`, `noise`, `gating_errors`, `exit_code`; `news.gated.missing` is 1 and `news.by_question["Q-26"].missing` is 1; each section lists its results with labels. The bytes have no `\r` and end with exactly one `\n`; non-ASCII is literal. (b) `ValueError`. (c) Contains `alerts`, `news`, `noise`, `gated`, `not gated` and `Q-26`. |
| E35 | **Case timeline.** Run: `R(T01, S002; [news(SeL@S001, en_seguimiento/alta/alta), news(PB@S001, en_seguimiento/ninguna/media)]; rows SeL, PB)`, then `alert(SeL@S001, S003)`, then `R(T02, S004; [news(SeL@S001, escalado/critica/critica), news(PB@S001, resuelto/ninguna/ninguna)]; [row SeL])`. | `(S001-Sedán-Local: first_reported_in T01, alerted_at (S003,), resolved_in None)`, then `(S001-Pickup-Brasil: T01, (), T02)`. |
| E36 | **Settings.** (a) `Settings(anthropic_api_key="k")`. (b) Env `HELDOUT_OPEN=true`, `HELDOUT_FIRST_SHIFT=T20`. (c) `HELDOUT_FIRST_SHIFT=""`. (d) `Settings(anthropic_api_key="k", data_dir=Path("d"), output_dir=Path("o"))`. (e) `.env.example`. | (a) `heldout_open False`, `heldout_first_shift "T22"`; there is no cutoff field. (b) `True`, `"T20"`. (c) `ValidationError`. (d) `plant_dir d/planta`, `snapshots_dir d/snapshots`, `logbooks_dir d/bitacoras`, `rules_dir d/reglas`, `evals_dir o/evals`, none in `model_fields`. (e) It has a line for every `Settings` field's env name, including `HELDOUT_OPEN` and `HELDOUT_FIRST_SHIFT`. |
| E37 | **CLI.** E40's registry; a golden directory whose `day_01.yaml` covers T01–T02 and matches it exactly (`A(SeL@S001, S003)`; T01 news SeL, PL; T02 news SeL, with their attributes); fixture `turnos.csv`; an empty logbook directory; first held-out shift T03, closed; fixed `now`; capabilities none. (a) As is. (b) The golden adds `N(T02, PL@S001, en_seguimiento/media/media)`. (c) (b) with that item marked `requires: [agent]`. (d) (c) with `capabilities={agent}`. (e) The golden covers `[T01, T02, T03]`. (f) The registry path does not exist. (g) Loading the golden raises `OSError`. | (a) Returns 0; stdout has the table; one `eval-*.json` is written. (b) Returns 1 (gated `missing 1`). (c) Returns 0; the summary has `news.not_gated.missing` 1 and no gated `missing`. (g) Returns 2; no summary written. (d) Returns 1. (e) Returns 2; stderr names `T03` and "held out"; no summary written. (f) Returns 2; no summary written. No logbook is read in any case: none is cited. |
| E38 | **Import boundaries.** | Every `evaluation` module imports only `plant_monitor.domain`, `plant_monitor.ingestion` and `plant_monitor.evaluation`. `evaluation/sources.py` may also import exactly `plant_monitor.cases.registry.notices.read_deliverables`, and nothing else from `cases`. No `evaluation` module imports `plant_monitor.cases.novelty`, `runner`, `agents`, `mcp_server`, `config`, `anthropic` or `mcp`, and none contains SQL or imports `sqlite3`. Importing `plant_monitor.evaluation.scoring` in a fresh interpreter loads no `plant_monitor.cases` module and no `sqlite3`. `ingestion` still imports only `domain`; `domain/calendar.py` imports only `domain`. |
| E39 | **`requires` gating (Q-35).** Golden covers T02 and T03. `A(SE@S003, S003, requires [agent])`: a §5 raise in force at opening, so the case opens already escalated (Q-08). `N(T02, SE@S003, escalado/critica/critica, requires [agent])`. No SE item in T03 (the full system has no change there). Threshold-only run: `alert(SE@S003, S005)`; `R(T02, S004; [news(SE@S003, en_seguimiento/alta/alta)]; [row SE])`; `R(T03, S006; [news(SE@S003, escalado/critica/critica), news(SL@S005, abierto/media/media)]; [rows SE, SL])`. (a) Capabilities none. (b) Capabilities `{agent}`. | (a) Alert `wrong_snapshot`, not gated. News T02 `hit` with `estado_mismatch`, `severidad_mismatch` and `maxima_mismatch`, not gated. T03: the SE `extra` is not gated (its case has an item with unmet `requires`), and the SL `extra` is gated. `gating_errors` 1 (the SL extra), and all results are shown. (b) Every result is gated: `wrong_snapshot` 1 + SE `extra` 1 + SL `extra` 1, so `gating_errors` 3. |
| E40 | **`read_deliverables` (`cases/registry/notices.py`).** A `tmp_path` registry written through `SqliteRegistry`, `processing` and `notices.save`, on the fixture calendar. S001 (mid): `informe_de_turno` SeL@S001 and PL@S001. S002: `informe_de_turno` SeL and PL, plus report T01 (news SeL `en_seguimiento/alta/alta` and PL `en_seguimiento/media/media`; rows SeL `en_seguimiento/alta`, PL `en_seguimiento/media`). S003: `alerta_inmediata` SeL@S001 and `sin_aviso` PL. S004: `informe_de_turno` SeL and `sin_aviso` PL, plus report T02 (news SeL `escalado/critica/critica`; rows SeL `escalado/critica`, PL `en_seguimiento/media`). `T01-informe` is marked delivered; the rest is pending. The registry is closed. This run has no noise. (a) `read_deliverables(path)`. (b) The file's bytes after (a). (c) A missing path. (d) A SQLite file whose `notices` table lacks `payload`. (e) A fresh registry with no notices. (f) `pending()` on the reopened registry. (g) A row with a corrupt `payload`. (h) A file that is not SQLite. | (a) `(T01 report, S003 alert, T02 report)`, in processing order, delivered and pending alike; no per-case row. (b) Identical to the bytes before the call, and the directory listing is unchanged (no `-journal`, `-wal` or `-shm`). (c) `ValueError` naming the path; the path still does not exist. (d) `ValueError` naming the file and `payload`. (e) `()`. (f) `(S003 alert, T02 report)`: the 004 behavior, through the shared `DELIVERABLE_FILTER`. (g), (h) `ValueError` naming the file. |

## Edge cases and assumptions
- **Q-14 (context):** an escalation at a closing snapshot expects both an alert and a news item; each metric misses independently (E18).
- **Q-15 (context):** every case appears in at least one report, so a golden set covering a whole case lifetime always has a news item for its opening.
- **Q-17, Q-32:** gap-only `no_declarada` with `etapa = null` is a valid golden value (E1). Scoring it against a run moves to spec 008.
- **Q-33:** only alerts and report rows are scored. A mid-snapshot `informe_de_turno` decision is never expected news (004 risk "mid `informe_de_turno` vs the report").
- **Q-34:** a whole covered shift with no report is an error (E22d), and an uncovered shift is reported as unscored, never as clean (E23).
- **Q-35:** attribute mismatches are reported but never gate. Values compare exactly, because they are contract values (E20). An item with unmet `requires` is always scored and shown (E39).
- **Q-35, extra exclusion:** an extra result is ungated only when its own case has an item with unmet `requires`. An extra caused by an unmet raise on a *different* case would still gate. A §5 raise acts on cases (Q-02), so a golden file that expects one lists items for every case it touches.
- **Q-36:** run causes are not scored in 005. The golden already records the true causes with `requires: [agent]`, so spec 008 starts from a baseline.
- **Q-37:** the arrivals reader stops at completion of the allowed set, so no held-out row is read from a sorted file (E6). A late repeat of an allowed snapshot is not read (E7g, documented limitation).
- **Q-38:** a case's cause stays the one that produced it, with its original citation, until the case resolves. The T10 golden for the Europe audit keeps `retencion_de_calidad` / `calidad` with the T07 citation even though T10 reports the audit finished.
- **Q-39:** §5 applies to the Europe audit: raise readable at S014, SUV × Europa opens already escalated at S015, the raise is lifted at S020.
- **Q-40:** a gap-only case is linked by model when the data trace its shortfall to the units a logbook names. The T10 golden for SUV × Brasil carries `retrabajo` / `pintura` with the T09 fragment.
- **Stage of a cited cause (note for spec 008):** §6 sets the stage from the data only for `no_declarada`. For a cited cause the golden uses the stage the logbook names (`calidad` for the audit), and spec 008 settles it.
- **Citation from a logbook not yet available (note for spec 006, Q-01):** golden evidence is not checked for availability at the target notice's snapshot in 005. Spec 006 settles Q-01, and spec 008 applies it to golden and notice evidence.
- **S034** arrives twice with the same file. The smoke run lists it as skipped (FR-02), and the arrivals reader returns both rows (E6 has the same shape at orden 3–4).
- Noise compares consecutive reports in `RunOutput` order. A run that stopped early yields fewer reports, and noise is computed over what exists. The missing reports show up in news scoring for covered shifts.
- An expected alert counts alerts of its case at **any** snapshot, so a late or early alert is `wrong_snapshot`, never `missing` plus `extra`. A case opened at another snapshot is a different case (E16).
- A golden item's `depends_on` names questions by pattern only; the loader does not read `requirements.md`.
- A golden `justification` written in prose is documentation in Spanish, citing rules as `criterio N` and never with the section sign; logbook quotes stay verbatim (Q-34).
- **Assumption:** logbooks are UTF-8 (BOM tolerated). The verbatim check normalizes whitespace only, matching the draft of spec 006 (Q-12). If spec 006 settles a different rule, spec 008 compares the two on the golden fragments.

## Acceptance
- [x] E1–E26, E30 and E32–E40 are tests and pass; every rule above has a passing test. E27–E29 and E31 are listed in spec 008.
- [x] Spec 001–004 tests pass unchanged (`pending()` included, now on `DELIVERABLE_FILTER`); `read_rows` keeps its behavior on top of the streaming reader; no test is deleted.
- [x] Import boundaries (E38) are in `tests/unit/test_import_boundaries.py`; `evaluation` is added to the model-SDK scan.
- [x] `HELDOUT_OPEN` and `HELDOUT_FIRST_SHIFT` are in `Settings`, `.env.example` and the settings tests; `tests/test_config.py` isolates them.
- [x] `evals/` is type-checked: `mypy src tests evals` in CI, pre-commit, `/check` and `CLAUDE.md`.
- [x] A3 smoke run executed by the user over days 1–7; output read and summarized in the roadmap (cases that open, escalate, resolve; S034 skipped; outbox empty).
- [x] A1 catalog in `evals/golden/incidents.md`, with the authoring notes (quoted justifications, `requires` vs `depends_on`). A4 is done (roadmap).
- [x] Golden cases for day 1 (`day_01.yaml`, T01–T03) and the Europe audit (T07–T10) exist, load with their evidence verified, and are verified by hand against `criterio.md`.
- [x] `evals/run_eval.py` prints the table, writes the summary under `output_dir/evals/` and exits as specified.
- [x] `docs/STRUCTURE.md` (the `evaluation` module, `HeldOutPolicy` in `domain`, `check_ids`/loaders in `ingestion`, `read_deliverables` in `cases/registry`, the dependency rule, `evals/` scripts) and the README section "How to run evals" match the implementation.
- [x] `ruff`, `mypy --strict` and `pytest --cov` pass.
