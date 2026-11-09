# 008 · Cited cause and logbook escalation — Spec

- **Status:** Implemented
- **Requirements:** FR-15, FR-16, FR-17, FR-18, FR-19, FR-38 (citation in the trace), FR-39 (cause metric)
- **Stories:** US-06, US-07
- **Decisions:** ADR-0002, ADR-0003, ADR-0010, ADR-0011, ADR-0013, ADR-0014, ADR-0015 (closing-snapshot trigger, active-cause entity, runner-side judgment adapter; created by the main session with `/new-adr` before Ready). Q-01, Q-12, Q-17, Q-25, Q-27, Q-31, Q-32, Q-35, Q-36 (reused); Q-02, Q-11, Q-29, Q-30, Q-47, Q-48, Q-49 (decided here); Q-38, Q-39, Q-40 (confirmed); Q-01, Q-41, Q-46 (amended).
- **Week:** W2

## Goal
Let the coordinator attach a cause to each case, quoted verbatim from a readable logbook, and raise cases to `critica` when a logbook says their cause is ongoing with no resolution date. Code verifies every citation, computes which cases a raise reaches, keeps the raise in force until a later logbook reports the resolution, and feeds it to the lifecycle. The evaluator gains the FR-39 cause metric.

## Scope
- **In:** cited causes and the `set_cause` tool; the active cause (raise) entity, its scope and links; `raise_severity` and `lift_severity_raise`; raises in the lifecycle and re-decide within a snapshot (Q-27); causes on notices; draft rebase; the closing-snapshot trigger; brief and prompt v2; registry schema v3; Q-01 for golden evidence; `score_causes`; synthetic incident fixtures; a user-run eval over days 1–7; goldens for the Pickup stop (gated on permission).
- **Out:** analysts and multi-agent (009); hooks, code allowlists, the criteria MCP prompt (010); structured output and caching (011).

## Decisions
- **D1 · Trigger (Q-41 amended):** every closing snapshot calls the model, plus any snapshot with a deliverable text. "Bottleneck without cause" is not a trigger.
- **D2 · Scope (Q-02, Q-49):** `modelo` + `etapa`, plus `mercado` only when the logbook names it; code matches at the raise and re-checks unlinked cases at every snapshot while the raise is in force; links are sticky.
- **D3 · A raise attaches its cause (Q-48):** to every linked case without a cited cause; a case with a different cited cause (another `categoria` or `etapa`) is never linked.
- **D4 · Lift (Q-11):** a dedicated tool; strictly later, readable logbook; effective at the current snapshot; lifts one active cause.
- **D5 · Q-29:** literal §3: a raise at N keeps active a case the first `track` would resolve.
- **D6 · Q-30:** raise and lift in one snapshot are allowed; a lift undoes only the severity effect, attached causes stay (Q-38); a duplicate raise is refused.
- **D7 · Stage of a cited cause (Q-47):** the stage the logbook names; never checked against the bottleneck.
- **D8 · Q-39, Q-40 confirmed:** the Europe audit raise at S014 with no case; gap-only cases link by model.
- **D9 · Q-01 applied:** to golden evidence at load, and to run evidence in `score_causes`.
- **D10 · Q-38 stands:** a case keeps its original cause and citation until it resolves.
- **D11 · Interface choices (ADR-0015):** schema v3 with an additive v2 migration; judgment writers carried by the snapshot frame; a runner-side adapter (`SnapshotJudgment`) that re-decides, rebases the draft and turns an internal failure into an abort; deterministic active-cause ids; judgment results that list changed notices (plan).

## Behavior

### R1 · Cited cause (FR-16, FR-17, FR-18, §6, Q-38)
- A case has at most one **cited cause**: a `categoria` from the §6 catalog other than `no_declarada`, a non-null `etapa`, one evidence `{bitacora, fragmento}` verified when written, the snapshot it was set at, and the active cause that attached it, if any (R8).
- A case with no cited cause keeps spec 004's default on every notice: `no_declarada`, stage from Q-17/Q-32, `evidencia []`. Code never stores `no_declarada` and never guesses a cause (§6).
- A cited cause set at an earlier snapshot never changes until the case resolves, even after a later logbook reports the cause resolved (Q-38).

### R2 · Stage of a cited cause (Q-47)
The stage the logbook names, chosen by the model. Code never compares it with the bottleneck: SUV × Brasil, with no bottleneck, takes `retrabajo` / `pintura` (Q-40).

### R3 · `set_cause(case_id, categoria, etapa, bitacora, fragmento)` (FR-17, Q-12, Q-01, Q-38, Q-40)
Checks in order; the first failure is a refusal (006 R13):
1. `categoria` is not `no_declarada`, else `no_declarada cannot be set: it is the default when no logbook names a cause`;
2. `LogbookStore.verify_citation(bitacora, fragmento, <frame snapshot>)` passes (006 R5 messages, e.g. `fragment not found in T02`, `logbook T03 is not available at S004: it closes at S006`);
3. the case exists, else `unknown case <id>`;
4. it was evaluated at this snapshot (a case of the last delta: active, opened or resolved here), else `<id> is not evaluated at <snapshot>`;
5. it has no cited cause set at an earlier snapshot, else `cause of <id> was set at <s>; it stays until the case resolves`;
6. its cause was not attached by an active cause at this snapshot, else `cause of <id> comes from active cause <ac>`;
7. if it is linked to an active cause in force, the new pair (`categoria`, `etapa`) equals that cause's, else `<id> is linked to active cause <ac> (<categoria> in <etapa>); its cause cannot change while the raise is in force` (Q-48: a linked case has that cause; added after review).

Effect: the cause is stored (fragment with its ends stripped); a second call for the case in the same snapshot replaces the first. Then R10 re-decides and R13 rebases. Success returns `{"caso", "causa", "avisos", "pendientes"}` (R15).

### R4 · Active cause (FR-19, §5, Q-02)
- A raise is recorded as an **active cause**: id `<snapshot_id>-causa-<n>` (n = 1 + causes already opened at that snapshot), `categoria` (not `no_declarada`), scope `{modelo, etapa, mercado | null}`, opened by `{bitacora, fragmento}` at a snapshot and, once lifted, lifted by `{bitacora, fragmento}` at a snapshot.
- `mercado` is set only when the logbook names the market (model judgment).
- It is **in force** at N while not lifted; a cause lifted at N is not in force at N.
- It lives in the registry and is written only inside the snapshot's unit of work, so a rolled-back snapshot leaves none (NFR-10).

### R5 · `raise_severity(categoria, etapa, modelo, mercado, bitacora, fragmento)` (FR-19, §5, Q-30, Q-39)
Checks in order:
1. `categoria` is not `no_declarada`, else `no_declarada cannot be raised: a raise needs a cause a logbook names`;
2. the citation (R3 check 2);
3. no active cause in force has the same scope, else `active cause <id> already covers <modelo> in <etapa>, <mercado | any market>`.

Effect: records the active cause, links the matching cases (R6), attaches its cause (R8) and re-decides (R10). Zero matching cases is valid: a raise alone never opens a case (Q-25, Q-39). Returns `{"causa_activa", "casos", "avisos", "pendientes"}`.

### R6 · Which cases a raise reaches (Q-02, Q-40, Q-48)
- **Candidates:** the cases evaluated at N (the last delta's cases), never a case resolved at an earlier snapshot. The model never names cases. Code builds them with their stage when it decides the snapshot.
- **Match:** same `modelo`; same `mercado` when the scope has one; and the case's stage equals the scope's `etapa`. A case's stage is its Q-32 bottleneck: the bottleneck of its last history row with a deviation (this snapshot's for a case with a deviation now). A case whose stage is `null` (Q-17) matches by model, and by market when the scope has one.
- A candidate whose cited cause has another `categoria` or another `etapa` is never linked: it does not have that cause (Q-48). One with the same pair is linked.
- SUV × Brasil (gap-only) is not in the Europe audit's scope `{SUV, calidad, Europa}`.

### R7 · Re-checks and sticky links while in force (Q-02, §5, Q-08, Q-49)
- While an active cause is in force, code re-checks at every snapshot N the candidates not yet linked to it (R6, with their stage at N). A case that matches is linked from N: a case that opens at N, and an active case whose bottleneck (or, with no bottleneck, its model and market) enters the scope. No model is involved.
- A linked case is raised from N: a case that opens at N opens `escalado` with its alert at N (Q-08). Pickup × Europa opens at S035 with bottleneck `montaje`: alert at S035, not S036.
- A link lasts until its active cause is lifted, even if the case's bottleneck moves out of the scope.
- A case with a different cited cause is never linked (R6, Q-48).
- When several causes in force match one case, they are checked in their opening order, so R8 attaches the oldest; a later cause with another `(categoria, etapa)` does not link it.

### R8 · A raise attaches its cause (Q-48)
Each linked case with no cited cause gets the raise's `categoria`, `etapa` and opening citation as its cited cause, set at the link snapshot and marked as attached by that active cause. A linked case that already has the same `categoria` and `etapa` keeps its own citation. So the S015 SUV × Europa alert carries `retencion_de_calidad` / `calidad` with the T07 citation without any `set_cause`.

### R9 · `lift_severity_raise(active_cause_id, bitacora, fragmento)` (Q-11, §5)
Checks in order (the citation first, as in every judgment tool):
1. the citation (R3 check 2), so it is readable at N (Q-01);
2. the active cause exists, else `unknown active cause <id>`;
3. it is in force, else `active cause <id> was lifted at <s>`;
4. `bitacora` is strictly later in calendar order than the logbook that opened the cause, else `<bitacora> is not later than <opening>, which opened active cause <id>`.

Effect: lifted at N with that citation, then R10. It undoes only the severity effect of that active cause: others linking the same case stay in force, and the causes it attached stay with their citation (Q-38). A clean case can resolve at N (Q-25). Returns `{"causa_activa", "levantada_en", "avisos", "pendientes"}`. Whether a logbook reports a resolution is judgment: a return date is not one (S016, measured by evals).

### R10 · Raises enter the lifecycle (FR-13, FR-15, Q-25, Q-27, Q-29)
- `raises` for a `track` of N = the combinations of the cases linked to a cause in force at N.
- **Decide N:** `track` → candidates (R6) → the R7 re-check links → if any link was added, `track` again (Q-27, from the pre-snapshot state) → the closing glue and the notices. One re-run suffices: raises change neither openings nor Q-32 stages. A case opened at N and linked there gets `(opened, escalated)`.
- **Re-decide N:** each successful judgment write runs the same steps again with the current links. Notices come only from the last (re-)decide and are saved once (`finish`).
- **Q-29:** a case active before N that the first `track` resolves stays active if a raise at N links it, because the re-run finds a raise in force. Its R6 stage is its Q-32 bottleneck, from an earlier snapshot.
- Severity is only raised (FR-15); `effective_severity` is unchanged.
- **Internal failure:** an exception inside a judgment write that is not a refusal (ledger, re-decide or rebase, e.g. `sqlite3.IntegrityError`) is stored by the adapter and re-raised to the tool server. From then on every write of the snapshot that reaches the writer, `emit_*` included, is refused with `writes are closed at <snapshot> after an internal error` (a call refused earlier by its own tool checks, such as `no_declarada` or a bad citation, keeps that refusal; the run aborts either way). Right after the loop and before `finish`, the pipeline raises the stored exception: the run stops with `RunAborted`, the unit rolls back, and the snapshot is resumable (NFR-10). Half-written rows are never committed.

### R11 · Raise and lift in one snapshot (Q-30)
Both are allowed (R9 check 4 still applies). The lift undoes only the severity effect: the last delta has no raise from that cause, so no alert from it. The causes it attached, at N included, stay with their citation (Q-38). A duplicate raise is refused (R5 check 3).

### R12 · Notices carry the cited cause (FR-25, Q-31, Q-32)
- `causa`/`evidencia` are the case's cited cause and its evidence when it has one at build time, else the 004 default with `[]`. That holds for alerts, news (a case resolved earlier in the shift included) and `sin_aviso`.
- `motivo`/`origen` keep Q-31: `bitacora` iff a raise is in force on the case and its minimum is below `critica`; `origen = agente` iff `bitacora`.
- Template sentence for a cited cause: `Causa: <categoría>, etapa <etapa> (bitácora <bitacora>).`, with `parada de línea`, `faltante de piezas`, `retrabajo`, `retención de calidad`, `ausentismo`. The 004 `no_declarada` sentences are unchanged.
- Notices are rebuilt through the validators, never with `model_copy(update=...)`.

### R13 · Draft rebase (ADR-0014, 007 R10)
After each re-decide the draft moves to the new notices:
- A written alert text survives when the new notices have an alert for the same `case_id` whose contract JSON, `texto` aside, equals the old one; otherwise it is dropped.
- The report's texts are one unit: they survive when the new `novedades` have the same `case_id`s in the same order and each item, `texto` aside, is unchanged; otherwise all are dropped.
- New notices start with their template text; a notice that disappears takes its text with it; required ids are recomputed (alerts, then news).
- Dropped required texts are pending again and listed in `pendientes`. Judgment tools are never blocked after an `emit_*`; `emit_*` refuses only texts still written (007 R8, R9).

### R14 · When the model is called, and the loop (Q-41 amended, Q-43, Q-44)
- **Call** at a snapshot with a required text (`text_needed`) and at **every closing snapshot** (`closing_review` when it has none). A mid snapshot with no required text is skipped (`no_text_needed`).
- **Stop rule:** after a `tool_use` turn the loop ends `done` only when some text is required and none is missing. With nothing required it runs until `end_turn` (`done`, no reminder). A judgment write that creates required texts keeps it going until they are written or a 007 fallback hits.
- On a fallback, judgment writes already made stay (they are in the unit of work); missing texts keep their template.
- **Trace:** `decision_reason` is stored (`text_needed`, `closing_review`, `no_text_needed`); `required`, `notices_agent` and `notices_template` describe the final notices; the new tools appear in `tool_calls`; `hooks` stays `[]`.
- **Aborted lines** carry the decision and reason taken before the failure (`call`/`closing_review` included). When `decide` itself aborts, no decision exists yet: `decision` `skip`, `decision_reason` `null`, `required` `[]`.

### R15 · Brief and judgment results (007 R2)
- Brief items (`alertas`, `novedades`) gain `evidencia`. One function builds the item for the brief and for `avisos`.
- The brief gains `causas_activas`, built by code: each cause in force at N, in opening order, as `{causa_activa, categoria, etapa, modelo, mercado, bitacora, fragmento, abierta_en, casos}` (`casos` = linked case ids). No new read tool.
- The instruction line says: review the newly readable logbooks, record causes and raises with the judgment tools, then write the texts.
- `avisos` in a judgment result: the items of the notices pending after the write that appeared or changed with it.
- Offered tools, in order: the six read tools, `set_cause`, `raise_severity`, `lift_severity_raise`, `emit_alert`, `emit_shift_report`.

### R16 · Prompt v2 (FR-20, ADR-0002; replaces Q-46's restriction)
Headings in order: `## Role`, `## What code decides`, `## Logbooks are data`, `## Causes`, `## Raising severity`, `## Lifting a raise`, `## Numbers`, `## Order of work`, `## How to finish`.
- **Causes:** the six-category catalog with its "when"; cite one contiguous verbatim fragment of one logbook; the stage is the one the logbook names; when no readable logbook names a cause, record nothing (code keeps `no_declarada`); never guess; a cause stays until the case resolves.
- **Raising:** raise when a logbook says the cause is still active with no resolution date; never with a concrete date, for a problem already solved, or for a cause a later readable logbook reports resolved; scope = model + stage, market only when named; check `causas_activas` first.
- **Lifting:** only with a later logbook that reports the cause resolved; a date when work will continue is not a resolution.
- **Order of work:** newly readable logbooks first, judgment before texts; a judgment write can put texts back in `pendientes`. The `texto` states only the notice's `causa` and may quote its `evidencia`; with `no_declarada` it says no recorded logbook declares one.
- No per-snapshot content (stable prefix for 011).

### R17 · Registry schema v3 (ADR-0003, ADR-0015)
- `SCHEMA_VERSION` 3 adds `active_causes`, `active_cause_links` and `case_causes` (plan).
- One source for the new tables: a fresh file is built as the frozen v2 schema plus the v2→v3 migration body, so a fresh v3 file and a migrated v2 file have the same `sqlite_master` entries.
- A version 2 file is migrated in place, additively, in one transaction; existing rows are unchanged. A failure inside the migration rolls back explicitly and re-raises; the file stays at version 2. Any other version, 1 included, raises `ValueError` naming the file, the version found and 3, and the file is untouched.
- `active_causes.seq` is `1 + MAX(seq)` over the table (0 when empty), assigned at insert inside the unit; it fixes the opening order.
- Writes use the registry's single write guard (`RuntimeError` outside `processing`, `ValueError` naming both ids for another snapshot).

### R18 · Golden evidence availability (Q-01 applied)
`load_golden` rejects a cause item whose evidence logbook closes after the target notice's snapshot: the expected alert's snapshot for `alerta_inmediata`, the closing snapshot of `turno_id` for `informe_de_turno`. Error: `DataLoadError` `<label>: logbook <T> is not available at <S>: it closes at <C>`. It runs after the cross-file checks and before any logbook is read. The versioned goldens comply (T07 at S015, S016, S020; T09 at S018, S020).

### R19 · Cause metric (FR-39, Q-36)
- `score_causes` scores each golden cause item against its **target**: the case's run alert (the one at the expected alert's snapshot if several), or the case's entry in the `turno_id` report's `novedades`.
- No target: `target_missing`. Otherwise: `categoria_mismatch` and `etapa_mismatch` (exact; `null` ≠ `montaje`); `evidence_missing` for a declared run cause with `evidencia []`; per run evidence item, the first of `evidence_not_loaded`, `evidence_not_available` (closes after the target's snapshot, Q-01) and `evidence_not_verbatim` (`contains_verbatim`). `hit` when none applies.
- Every key but `hit` is an error, gated as Q-35 (`requires` ⊆ capabilities). There are no extras.
- `run_eval` loads the logbooks cited by target notices once, known and not held-out ids only. `--capabilities agent` gates `requires: [agent]` items. The summary gains a `causes` section (table and JSON), and its errors join `gating_errors`. `evaluation` never imports `cases.novelty`.

### R20 · Per-case release of extras under Q-02 (005 Q-35)
A raise acts only on the cases it links (R6, R7), so spec 005's rule holds: an unmet `requires` item releases only its own case's extras. A golden file that expects a raise lists items, with `requires: [agent]`, for every case the raise touches; an extra of a case with no such item still gates.

### R21 · Import boundaries
- `cases/causes.py`, `cases/ledger.py` and `cases/registry/causes_repo.py` follow the `cases` rule (only `domain`, `metrics.thresholds`, `cases`).
- `mcp_server` declares the writer protocols and knows only them: never `runner`, `cases.draft`, `cases.ledger` or `cases.registry.causes_repo`.
- `runner/judgment.py` may import `domain`, `cases`, `runner` (for `SnapshotDecision`) and `mcp_server.context`.
- `evaluation/causes.py` imports only `domain` and `evaluation`. `agents` keeps its 007 allow-list.

### R22 · Real run over days 1–7 (user-run)
`evals/agent_days_1_7.py`, like 007 R18 with a pinned, closed held-out policy (first held-out shift T22, never opened by `heldout_open`): S001–S042 with `AnthropicModel` into a fresh run directory; it prints the trace path, run totals and duration. The user runs it with permission, then `evals/run_eval.py --capabilities agent`; results and cost go to the roadmap.

## Worked examples

**Notation.**
- **IF**, the incident fixture (`tests/fixtures/incidents/`, synthetic): `planta/turnos.csv` T01–T06 = (S001, S002) … (S011, S012), 8 h shifts from 2026-03-02T06:00; `planta/plan_produccion.csv` 10 units per shift for every combination (daily 30: `media` from −3 u, `alta` from −6 u, `critica` from −11 u); standards, shipments and thresholds from `tests/fixtures/plant/`. Logbooks `bitacoras/T01.txt`–`T06.txt` (UTF-8, LF, lines separated by ` / ` here):
  - T01 `Turno mañana T01.` / `A las 9:20 se paró la línea de montaje de Sedán por una falla en la atornilladora de la estación 14.` / `Mantenimiento la cambió y la línea volvió a las 10:30.`
  - T02 `Turno tarde T02.` / `A las 19:00 llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación.` / `El auditor pidió revisar cada unidad antes de liberarlas.`
  - T03 `Turno noche T03.` / `La auditoría de homologación sigue revisando las SUV para Europa.` / `El auditor vuelve mañana a primera hora para terminar la revisión.`
  - T04 `Turno mañana T04.` / `La auditoría de homologación terminó a las 8:30 y se liberaron las SUV para Europa que estaban retenidas.`
  - T05 `Turno tarde T05.` / `A las 15:00 se paró la línea de montaje de Pickup por la rotura del transportador aéreo de la estación 3.` / `Mantenimiento espera el repuesto y por ahora no hay fecha confirmada de vuelta.`
  - T06 `Turno noche T06.` / `El repuesto llegó a las 3:00 y la línea de montaje de Pickup volvió a las 4:00.`
- **Fragments:** F2 `llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación`; F3 `El auditor vuelve mañana a primera hora`; F4 `La auditoría de homologación terminó a las 8:30`; F5 `se paró la línea de montaje de Pickup por la rotura del transportador aéreo de la estación 3. Mantenimiento espera el repuesto y por ahora no hay fecha confirmada de vuelta` (spans a line break); F6 `la línea de montaje de Pickup volvió a las 4:00`.
- **IF gaps** (units; 0 elsewhere): SeL −2 at S001; SE (SUV × Europa) −1 at S004, −4 at S005–S006; PL and PB −2 at S009, −4 at S010, −7 at S011, −11 at S012; PE −2 at S010, −6 at S011, −11 at S012. One delayed unit per bottleneck: SE `calidad` at S005–S006 (in `calidad` since 03-02 20:00, EUR-0305); PL, PB `montaje` at S010–S011 (since 03-03 08:00, LOC-0304, BRA-0304); PE `montaje` at S011 (since 03-03 14:00, EUR-0305). Delay 0.0 everywhere; no other bottleneck.
- **Ids:** SE@S005 = `S005-SUV-Europa`, PL@S010, PB@S010, PE@S011 likewise; SB = SUV × Brasil. AC1 = `S004-causa-1` {`retencion_de_calidad`; SUV, `calidad`, Europa; T02, F2}; AC2 = `S010-causa-1` {`parada_de_linea`; Pickup, `montaje`, null; T05, F5}.
- "Ledger" = `CauseLedger` on `SqliteRegistry(":memory:")` with cases from the 003 builders, inside `processing(N)`; "stage" = the Q-32 bottleneck. `ERR(t, m)`, `tool`, `end` and agent texts `Agente: <notice_id>` as in 007. Default settings.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | Domain (R1, R4): (a) `CitedCause` with `no_declarada`; with `etapa` null. (b) `ActiveCause` lifted at S008 with no `lifted_by`. (c) AC1; AC1 lifted at S008 by (T04, F4); scope `{SUV, calidad, null}` | (a), (b) `ValueError`. (c) `in_force` True, then False; the null-market scope is valid. |
| E2 | Schema v3 (R17): (a) new `tmp_path` file, closed and reopened; (b) a version 2 file written with the frozen v2 schema holding one case, its history row and one notice; (c) `user_version` 1; (d) 7; (e) `sqlite_master` of (a) and of (b) after migration; (f) (b) with the migration's second statement patched to fail | (a) `user_version` 3, the three tables exist. (b) Opens; `user_version` 3; case, history and notice unchanged; the new tables exist and are empty; reopen succeeds. (c) `ValueError` naming the file, 1 and 3; still 1. (d) The same with 7. (e) Equal `(type, name, sql)` sets. (f) The error propagates; `user_version` still 2 and no new table. |
| E3 | Cause store (R4, R17): in `processing(S010)` open AC2, link PL@S010, set PL's cited cause; clean exit; new registry on the file. (a) Any write outside `processing`; (b) in `processing(S010)` a write stamped S011; (c) the same writes, then `RuntimeError` | Reopened: AC2 in force with scope and opening evidence; link (AC2, PL@S010, S010); PL's cause with `set_at` S010 and AC2. (a) `RuntimeError`. (b) `ValueError` naming S010 and S011. (c) Nothing stored. |
| E4 | `matches` (R6, Q-40): scope {Pickup, montaje, null} with PL `montaje`, PB `null`, PL `pintura`, SeL `montaje`; scope {SUV, calidad, Europa} with SE `calidad`, SE `null`, SB `null`, SE `pintura` | True, True, False, False; True, True, False (market), False. |
| E5 | `set_cause` through `ToolClient`, IF logbooks, frame S004 with a recording fake `CauseWriter` (R3): (a) `no_declarada`; (b) T02, `se detuvo la auditoría`; (c) T03, F3; (d) `T09`; (e) `retencion_de_calidad`, `calidad`, T02, F2 with its first space doubled; (f) a frame with no cause writer | (a) `ERR(set_cause, "no_declarada cannot be set: it is the default when no logbook names a cause")`. (b) `… "fragment not found in T02"`. (c) `… "logbook T03 is not available at S004: it closes at S006"`. (d) `… "unknown logbook T09"`. No writer call in (a)–(d). (e) One call with that cause and evidence (T02, the fragment as sent); the result is the fake's `JudgmentResult` as JSON. (f) `… "no judgment is being recorded at this snapshot"`. |
| E6 | Ledger `set_cause` at S010 (R2, R3, Q-38, Q-40); delta: SE@S005 active, SB@S007 active (stage null), PL@S010 opened; SeL@S001 resolved at S004: (a) `S999-SUV-Local`; (b) SeL@S001; (c) SE `retencion_de_calidad`/`calidad`, then `retrabajo`/`calidad`, both at S010; (d) SE with a cause set at S005; (e) PL with its cause attached by AC2 at S010; (f) SB `retrabajo`/`pintura` | (a) `unknown case S999-SUV-Local`. (b) `S001-Sedán-Local is not evaluated at S010`. (c) The second replaces the first. (d) `cause of S005-SUV-Europa was set at S005; it stays until the case resolves`. (e) `cause of S010-Pickup-Local comes from active cause S010-causa-1`. (f) Stored; the stage is not compared with the null bottleneck. |
| E7 | Tools with a recording fake `RaiseWriter` (R5, R9): (a) frame S010, raise `no_declarada`; (b) frame S010, raise citing T05 `se detuvo la línea`; (c) frame S011, lift AC2 citing T06, F6; (d) frame S010, raise `parada_de_linea`, `montaje`, Pickup, no `mercado`, T05, F5 | (a) `ERR(raise_severity, "no_declarada cannot be raised: a raise needs a cause a logbook names")`. (b) `… "fragment not found in T05"`. (c) `ERR(lift_severity_raise, "logbook T06 is not available at S011: it closes at S012")`. No writer call in (a)–(c). (d) One call, scope `mercado` None. |
| E8 | Ledger raise (R5, Q-39), AC2 in force at S011: (a) {Pickup, montaje, null}; (b) {Pickup, montaje, Local}; (c) at S004 with no case, AC1's raise; (d) {Pickup, montaje, null} at S013, AC2 lifted at S012 | (a) `active cause S010-causa-1 already covers Pickup in montaje, any market`. (b) Opens `S011-causa-1`. (c) Opens `S004-causa-1`, `casos` `()`. (d) Opens `S013-causa-1`. |
| E9 | Ledger lift (R9), AC1 opened at S004 by T02: (a) `S099-causa-1`; (b) AC1 lifted at S008, lifted again at S010; (c) at S006 citing T02, then T01; (d) at S006 citing T03, F3 | (a) `unknown active cause S099-causa-1`. (b) `active cause S004-causa-1 was lifted at S008`. (c) `T02 is not later than T02, which opened active cause S004-causa-1`; the same with `T01`. (d) Lifted at S006: code accepts it; T03 reporting no resolution is judgment (E21 scripts no lift there). |
| E10 | Raise links and attaches (R6, R8, Q-48), ledger at S010, raise AC2; candidates PL@S010 (`montaje`), PB@S010 (null), SeL@S008 (`montaje`), PE@S007 (`montaje`, cited `faltante_de_piezas`/`montaje` at S008). Variant: PE's cited cause is `parada_de_linea`/`montaje` from T04 | `casos` (PL, PB). Both get `parada_de_linea`/`montaje`, evidence (T05, F5), `set_at` S010, AC2. PE (another cause) and SeL (model) are not linked. Variant: PE is linked and keeps its T04 citation. |
| E11 | Sticky links and openings (R7, R10, Q-08, Q-49), `ThresholdPipeline` on IF S011 with AC2 linking PL, PB since S010: PL's bottleneck at S011 is `calidad`; PE opens (stage `montaje`); a Sedán × Local case opens in `montaje`. Variant: AC {SUV, pintura, null} opened at S010 while SL@S009 (no cited cause) had stage `calidad`; SL's stage is `pintura` at S011 and `calidad` again at S012 | PL and PB `escalado`/`critica`. PE: the first `track` opens it `abierto`; after the link and the re-run it opens `escalado`, events `(opened, escalated)`, one alert, `motivo [bitacora]`, `origen agente`, `causa {parada_de_linea, montaje}`, `evidencia [{T05, F5}]`; link (AC2, PE@S011, S011). The Sedán case is not linked. Variant: SL is not linked at S010; at S011 it is linked, raised (`escalado`, alert at S011, the AC's cause attached); at S012 it stays raised (sticky). |
| E12 | Q-29 (R10), synthetic: PB@S006 opened `media` (stage `montaje`), clean at S007; in `processing(S008)` PB clean: first `track`, then raise {Pickup, montaje, null} and re-decide | First delta: PB `resuelto`, streak 2. After the raise: PB linked by its S006 stage; PB `escalado`/`critica`, raised, events `(escalated, severity_changed)` against S007; not in `resolved_unreported()`; one alert at S008 with `motivo [bitacora]`. |
| E13 | One lift, one cause (R9, Q-25): SE@S005 linked to AC1 and to AC3 {SUV, calidad, null} (opened S005), clean at S007–S008; at S008 lift AC1 with (T04, F4). Variant: no AC3 | SE stays `escalado`/`critica`; AC1 lifted at S008. Variant: SE `resuelto` at S008, `severidad_maxima` `critica`. |
| E14 | Q-30 (R11): IF with no raise at S004 (SE@S005 `en_seguimiento`/`media`, no cited cause at S006). At S006: raise {SUV, calidad, Europa} citing T02, F2; lift it citing T03, F3; raise the same scope twice more | After the raise: SE `escalado`, an alert decided, cause `retencion_de_calidad`/`calidad` (T02) attached. After the lift: no alert; SE `en_seguimiento`/`media`, `motivo [gap]`, `umbral`; SE keeps the attached cause and T02 evidence (Q-38); `S006-causa-1` is stored opened and lifted at S006. Then `S006-causa-2` opens and links SE (same pair, own citation kept), and the next raise is refused (`already covers SUV in calidad, Europa`). |
| E15 | Notices (R12): (a) 004 E23's case with cited `retencion_de_calidad`/`calidad`, evidence (T02, F2); (b) the same with none; (c) `cause_text` for each declared category, stage `montaje`, logbook T05 | (a) `causa {retencion_de_calidad, calidad}`, `evidencia [{T02, F2}]`, texto ends `Causa: retención de calidad, etapa calidad (bitácora T02).` (b) Equal to 004 E23. (c) `Causa: parada de línea, etapa montaje (bitácora T05).` and likewise with `faltante de piezas`, `retrabajo`, `retención de calidad`, `ausentismo`. |
| E16 | Rebase (R13): (a) IF S010 draft (news PL, PB `abierto`/`media`) with both news texts written, then the re-decide after AC2; (b) IF S012 draft with PE's news written, then the re-decide after lifting AC2 (PE's minimum is `critica`); (c) E14's S006 draft with the alert text written, then the lift | (a) `written()` `()`; `required()` and `missing()` = alerts PL, PB, then news PL, PB. (b) PE's text survives; `missing()` `()`. (c) The alert and its text are gone; `written()` holds no alert id. |
| E17 | Adapter (R10, R13, R15), IF S010 in its unit with real steps: `set_cause(PL, parada_de_linea, montaje, T05, F5)` through `SnapshotJudgment` | One more `track` for S010 (PL still has one S010 history row); PL's news rebuilt through the validators with the new `causa`, `evidencia` and template text; `avisos` = [PL's news item]; `pendientes` = both news ids; `save` runs only at `finish`, once. |
| E18 | Trigger and stop rule (R14): (a)–(c) `AgentPipeline` with fake steps and `FakeModel`: (a) closing snapshot with an empty report, script `tool(get_logbook, {turno_id: T01})`, `end("Sin causas.")`; (b) mid snapshot with no text; (c) closing snapshot with one news item. (d) `Coordinator` with a fake tool port and a progress whose `required()` and `missing()` gain one alert id after the first call, script `tool(raise_severity, …)`, `tool(emit_alert, …)` | (a) 2 requests, outcome `done` (no stop after the tool turn); trace `call`, `closing_review`, `required` `[]`. (b) No request; `skip`, `no_text_needed`. (c) `call`, `text_needed`. (d) 2 requests, `done`; no third request. |
| E19 | Brief (R15): `render_brief` at IF S011 after `decide` | `causas_activas` = `[{"causa_activa":"S010-causa-1","categoria":"parada_de_linea","etapa":"montaje","modelo":"Pickup","mercado":null,"bitacora":"T05","fragmento":F5,"abierta_en":"S010","casos":["S010-Pickup-Local","S010-Pickup-Brasil","S011-Pickup-Europa"]}]`; PE's alert item has `evidencia [{"bitacora":"T05","fragmento":F5}]` and equals the shared item function's output. |
| E20 | Prompt and tools (R15, R16) | The nine headings in order; the six category values appear; no `S\d{3}` or `T\d{2}` id; loads from the installed package. `COORDINATOR_TOOLS` = the read tools, `set_cause`, `raise_severity`, `lift_severity_raise`, `emit_alert`, `emit_shift_report`, equal to `(*READ_TOOLS, *WRITE_TOOLS)`; `build_server` still defaults to six tools. |
| E21 | **Integration (R3–R16).** IF S001–S012 through `run_series`, `tmp_path` registry, `build_agent_pipeline` with `FakeModel` (`data_dir` = IF), `PostCommitChain(trace, outbox)`. Script: S002 `tool(get_logbook, T01)`, `end`. S004 `tool(get_logbook, T02)`, `tool(raise_severity, retencion_de_calidad, calidad, SUV, Europa, T02, F2)`, `end`. S005 `tool(emit_alert, SE)`. S006 `tool(get_logbook, T03)`, `tool(emit_shift_report, [SE])`. S008 `tool(get_logbook, T04)`, `tool(lift_severity_raise, S004-causa-1, T04, F4)`, `tool(emit_shift_report, [SE])`. S010 `tool(get_logbook, T05)`, `tool(raise_severity, parada_de_linea, montaje, Pickup, null, T05, F5)`, one reply with `emit_alert` PL, `emit_alert` PB, `emit_shift_report` [PL, PB]. S011 `tool(emit_alert, PE)`. S012 `tool(get_logbook, T06)`, one reply with `lift_severity_raise` (S010-causa-1, T06, F6) and `emit_shift_report` [PE]. Agent texts throughout | 17 requests, no tool error, no `sqlite3.ProgrammingError`. **T01 (Sedán stop):** no case, no active cause, empty report. **S004:** AC1 opened, `casos` `[]`. **S005:** alert SE `escalado`/`critica`/`critica`, `motivo [bitacora]`, `agente`, `causa {retencion_de_calidad, calidad}`, `evidencia [{T02, F2}]`. **S006:** T03 news SE, same values. **S007:** `sin_aviso` SE. **S008:** AC1 lifted by (T04, F4); T04 news SE `resuelto`/`ninguna`/`critica`, `motivo []`, `umbral`, same cause and T02 evidence (Q-38); `casos_activos` `[]`. **S010:** AC2 links PL, PB; alerts PL, PB (`[bitacora]`, `agente`, `parada_de_linea`/`montaje`, `[{T05, F5}]`) and news PL, PB `escalado`/`critica`/`critica`. **S011:** alert PE (`[bitacora]`, minimum `alta`), link and cause set at S011; `sin_aviso` PL, PB. **S012:** AC2 lifted by (T06, F6); T06 news PE `escalado`/`critica`/`critica`, `motivo [gap]`, `umbral`; `sin_aviso` PL, PB. 20 notice rows; delivered in order: reports T01, T02, alert SE, report T03, report T04, alerts PL, PB, report T05, alert PE, report T06. Registry: 2 active causes, 4 links, 4 cited causes. Trace: 12 lines; `call` at S002, S004, S008 (`closing_review`) and S005, S006, S010, S011, S012 (`text_needed`); `skip` elsewhere; S010 `tool_calls` `get_logbook`, `raise_severity` (arguments as sent), `emit_alert`, `emit_alert`, `emit_shift_report`. `run_totals`: 12 snapshots, 8 called, 17 calls, input 51,000, output 3,400, usd `0.0068`. |
| E22 | **Abort and resume.** E21 with S010's third request raising `ModelCallFailed`. Run 2: new registry on the file, healthy script from S010 | Run 1: `RunAborted` at S010, cause `ModelCallFailed`; no AC2, link, cited cause or case for S010 (rollback); an aborted S010 line with its 2 tool calls. Run 2: final rows and files equal E21's. |
| E23 | Golden availability (R18): synthetic T01–T21 calendar (Tn = S(2n−1), S(2n)), open policy: (a) a file covering T08 with `A(SE@S015, S015)` and an alert cause citing T08; (b) a T08 news cause citing T08; (c) the versioned `evals/golden/` with a source returning, per requested id, the golden fragments citing it joined by newlines | (a) `DataLoadError` `day_x.yaml#causes[0]: logbook T08 is not available at S015: it closes at S016`; the source is never called. (b) Loads. (c) Loads. |
| E24 | Cause hit (005 E27 moved; R19): golden cause SE@S005 `alerta_inmediata`, `retencion_de_calidad`, `calidad`, (T02, F2), `requires [agent]`; run alert with that cause and F2 with one space replaced by a line break; logbooks `{T02}`; capabilities `{agent}` | `{hit: 1}`, gated; cause errors 0. |
| E25 | `categoria` miss (005 E28): E24 with the run cause `parada_de_linea`/`calidad` | `{categoria_mismatch: 1}`. |
| E26 | Evidence failures (005 E29), E24 with run evidence: (a) `retuvo las SUV en calidad`; (b) (T09, F2), T09 not loaded; (c) `[]`; (d) F2 starting `Llegó`; (e) (T03, F3), T03 loaded | (a) `evidence_not_verbatim`. (b) `evidence_not_loaded`. (c) `evidence_missing`. (d) `evidence_not_verbatim` (case-sensitive). (e) `evidence_not_available`. No hit in any. |
| E27 | Gap-only (005 E31 moved): golden PB@S010 `alerta_inmediata`, `no_declarada`, `etapa` null, no `requires`; run alert `no_declarada`/`montaje`, `[]`; capabilities none | `{etapa_mismatch: 1}`, gated. |
| E28 | `target_missing`: (a) E24 with no SE alert in the run; (b) a news cause for (T03, SE@S005) and a T03 report without SE | `target_missing` in each. |
| E29 | Q-38 and Q-40: (a) golden T04 news cause SE `retencion_de_calidad`/`calidad`, (T02, F2); run T04 news `resuelto` with `no_declarada`/`calidad`, `[]`; then with the T02 cause kept. (b) logbooks `{T03: "Se separaron las SUV en Gris Grafito. Vuelven a la cabina de repintado."}`; golden T03 news cause SB `retrabajo`/`pintura` citing it; run news SB `retrabajo`/`pintura` with that fragment; then `no_declarada`/null | (a) `categoria_mismatch`; then `hit`. (b) `hit`; then `categoria_mismatch` and `etapa_mismatch`. |
| E30 | Summary and CLI (R19): (a) E25's miss on a `requires [agent]` item, capabilities none, then `{agent}`; (b) `render_table` and JSON; (c) `run_eval` on the fixture calendar with a registry whose target alert cites T02 (present) and T99 | (a) Not gated, `gating_errors` 0; then gated, 1, exit 1. (b) A `causes` row; JSON `causes` with `gated`, `not_gated` and results. (c) Exit 1, `evidence_not_loaded` 1, no load error. |
| E31 | Release under Q-02 (R20), 005 notation: golden `A(PL@S010, S010, requires [agent])` and `N(T05, PL@S010, escalado/critica/critica, requires [agent])`, no PB item; threshold-only run with `news(PB@S010, abierto/media/media)` in T05 | PL's results are not gated; PB's extra news is gated (1 error). |
| E32 | Import scan (R21) | As R21; a fixture `from plant_monitor.runner`, `plant_monitor.cases.ledger` or `plant_monitor.cases.registry.causes_repo` in `mcp_server/write_tools.py`, or `import plant_monitor.cases.novelty` in `evaluation/causes.py`, is flagged. |
| E33 | **Internal failure in a judgment write (R10, NFR-10).** E21 run up to S010, with steps whose `redecide` raises `RuntimeError("boom")`. S010 script: `tool(get_logbook, T05)`, `tool(raise_severity, AC2's arguments)`, `tool(emit_shift_report, [PL, PB])`, `end` | The raise result is `is_error` with exactly `Error executing tool raise_severity`; the emit is `ERR(emit_shift_report, "writes are closed at S010 after an internal error")`. `RunAborted` at S010 with cause the `RuntimeError`; no S010 row is stored (no AC2, link, cited cause, case, notice); an aborted S010 line with `decision` `call`, `decision_reason` `text_needed` and the 3 tool calls. A healthy rerun from S010 matches E21. |
| E34 | **Q-49 with Q-48**, E11's variant with SL holding a cited cause set at S009: (a) `retencion_de_calidad`/`calidad`; (b) `retrabajo`/`pintura` from T03 | (a) SL is never linked: not at S011 nor later. (b) SL is linked at S011 and keeps its T03 citation. |

## Edge cases and assumptions
- **X1** · A raise linking a case already `critica` by threshold adds no event or alert; `motivo` keeps its threshold triggers and `origen` stays `umbral` (Q-31).
- **X2** · A threshold-only run on schema v3 sees no active cause, so `raises` is empty and specs 004 and 005 behave as before.
- **X3** · Active causes, links and cited causes commit with their snapshot, so a resumed run sees the raises in force (E22).
- **X4** · A judgment write that fails after its checks (a bug, not a refusal) reaches the model only as a generic tool error, so the adapter, not the SDK, carries it to the pipeline, which aborts before `finish` (R10, E33).
- **X5** · Read tools do not show cited causes; the model learns them from brief items, `causas_activas` and refusals.
- **X6** · A wrong `mercado` or stage chosen by the model is judgment; code cannot check it, evals measure it.
- **X7** · The closing trigger turns 21 closings of days 1–7 into calls; R22 measures the cost.

## Acceptance
- [ ] E1–E34 pass, one layer each; CI makes no network call (NFR-07).
- [ ] Specs 003–007 tests pass. Only these expectations change, no test deleted: schema version 3 (003 E21, 004 E24), 007 E2 (brief keys), 007 E18a and E20 (`decision_reason`, tool list), 007 R15 headings (now R16), 005 E34 (JSON keys gain `causes`).
- [ ] `docs/requirements.md`: Q-02, Q-11, Q-29, Q-30, Q-47, Q-48, Q-49 decided; Q-38–Q-40 confirmed; Q-01, Q-41, Q-46 amended. ADR-0015 exists.
- [ ] `ruff`, `mypy --strict`, `pytest --cov` pass; `docs/STRUCTURE.md`, the components and case-state-machine diagrams, and the roadmap (row 008, tool inventory) updated.
- [ ] The user runs R22 and the eval with `--capabilities agent`; results for the three incidents (category, stage, citation, escalation timing) are recorded.

## Size
About 41 KB, over the 20 KB budget. Causes, raises and lifts share one fixture series, one re-decide path and one notice rebuild, and the cause metric scores exactly what they produce; splitting would repeat E21 and the rebase rules in two specs.
