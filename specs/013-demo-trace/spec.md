# 013 · Alert trace for the demo — Spec

- **Status:** Implemented
- **Requirements:** FR-25, FR-38, FR-20, FR-40, NFR-09
- **Stories:** US-10
- **Decisions:** ADR-0019 (read-only notice trace: registry read `mode=ro` plus JSON lines, no schema change). Q-72–Q-83 decided. Q-13, Q-14, Q-31, Q-32, Q-44, Q-65, Q-71 reused unchanged.
- **Week:** W7

## Goal
For any notice, show in which snapshot it fired, why and with which quote, rebuilt only from stored data (registry plus trace files). No model call and no write. This is the centerpiece of Demo Day.

## Scope
- **In:** `domain/stored.py` (`StoredNotice`), `cases/registry/notice_reader.py` (read-only reader), `telemetry/trace_query.py` (pure view), `telemetry/trace_render.py` (pure text), `TraceFile`/`read_trace_files` in `telemetry/trace.py`, `notify.console.write_safe`, the `plant-monitor trace <notice_id>` subcommand in `runner/cli.py`, tests, docs, and a draft `docs/demo.md`.
- **Out:** any new system behavior; registry schema or trace schema changes (Q-82); `--json` (Q-80); reading real data. Choosing the demo alert, finishing the script and the rehearsal are manual tasks after the held-out run (Q-83).

## Decisions
- **D1 · Layers (Q-72).** Reader in `cases`, pure view and renderer in `telemetry`, composition in `runner/cli.py` (ADR-0018). No import rule widens.
- **D2 · Ids, calls, raises, resumes, modes (Q-73–Q-77).** As the rules below state.
- **D3 · Exit codes and held-out guard (Q-78, Q-79).**
- **D4 · Text only, logbooks escaped (Q-80, Q-81).**
- **D5 · No schema change (Q-82).** Closes ADR-0014's "trace rows in the registry, revisit in spec 013".
- **D6 · Interface choices** (taken by the spec writer; see plan):
  - **I1** `parse_args` returns `RunOptions | TraceOptions`; `main` dispatches on the type. No 006–012 test changes.
  - **I2** The renderer lives in `telemetry/trace_render.py`, next to the view it renders, not in `runner`: it needs only `domain` and `telemetry`, so the `runner/summary.py` rule stays as is.
  - **I3** Escaping is applied to each rendered line, so no stored value can bypass it (R12).
  - **I4** Floats are shown with `domain.numbers.round_display` and `DECIMALS` (1 place, `-0.0` printed as `0.0`); USD with `telemetry.trace.USD_DECIMALS` (8 places). No new setting.
  - **I5** stdout is written through `notify.console.write_safe` (extracted from `ConsoleNotifier._write`, which now calls it): the stream's encoding with `backslashreplace`, so a `cp1252` redirect never fails on `→`, `×` or `—`.
  - **I6** The repos' row parsers become public names in their modules: `HISTORY_COLUMNS`/`history_from_row`, `ACTIVE_COLUMNS`/`active_from_row`, `CITED_COLUMNS`/`cited_from_row` (extracted from `SqliteCauseRepository.cited`). The column lists are tuples, joined with `", "` at each SQL site. No behavior change.
  - **I7** `StoredNotice` (a frozen dataclass of domain types) lives in `domain/stored.py`. `read_notice` returns `StoredNotice | ShiftReport | None`, and `build_notice_trace(stored, traces)` takes it whole.
  - **I8** The view types are frozen dataclasses, not pydantic, so nothing is re-validated and no multi-line `ValidationError` can reach stderr.
  - **I9** `TraceMode = Literal["agent", "thresholds_only"]` is defined once, in `telemetry/trace.py`. `runner/summary.py`'s `Mode` becomes an alias of it.
  - **I10** `TraceFile` and `read_trace_files(directory)` live in `telemetry/trace.py` next to `read_trace`. `cli._report` reuses them for the series lines.

## Behavior

### R1 · Command (FR-38, Q-80, I1)
`plant-monitor trace NOTICE_ID`, a second subcommand of the 012 parser. Output is text on stdout. `trace --help` returns 0; a missing id is an argparse error (2). `run` keeps its options, behavior and tests.

### R2 · Read-only, no model (FR-38, Q-72, Q-82, ADR-0002, ADR-0019)
- Data comes only from `settings.registry_path`, the `trace-*.jsonl` files under `settings.traces_dir` and `turnos.csv` (for the held-out policy, R11).
- The registry is opened `mode=ro` by `read_notice`, never through `SqliteRegistry` (which migrates on open). A missing file is a `ValueError`, never created.
- All of `read_notice`'s reads run inside one read transaction (`BEGIN` … `COMMIT`), so a trace taken during a running `run --speed` sees one committed state.
- Nothing is written: no file, no directory, no log file. `deps.model_factory` is never called and the API key is never read.
- A notice is shown as stored; it is never rebuilt or copied with `model_copy`.

### R3 · Which ids (Q-73, Q-14, FR-25)
- Any per-case row of `notices` (`kind = 'notice'`): `alerta_inmediata`, `informe_de_turno` (closing news and mid-snapshot decisions) and `sin_aviso`.
- A report id (`kind = 'report'`, e.g. `T05-informe`) is read as its `ShiftReport`. It exits 1 with stderr `<report_id_for(turno_id)> is a shift report, not a notice; its novedades: <id>, <id>` (the `notice_id`s of `novedades`, stored order), or `…; its novedades: none`.
- Any other id exits 1 with stderr `unknown notice_id: <id>`.

### R4 · Registry part (FR-25, FR-38, Q-13, Q-31, Q-32)
From the stored notice and the case's history (ordered by the registry's processing `seq`):
- the notice's `tipo`, `estado`, `severidad`, `severidad_maxima`, `motivo`, `origen`, `causa`, `evidencia` and `texto`, as stored;
- the history row at the notice's snapshot: gap units and %, delay, bottleneck, minimum and effective severity, raised;
- the transition: the state of the case's previous history row (by `seq`) → the state at this row. With no previous row it is `—` (the case opened here, Q-08);
- "recorded at <set_at> [from <active_cause_id>]" after the cause, only when the registry's cited cause has the notice's category, stage and evidence and `set_at` is at or before the snapshot.

### R5 · News of a case resolved earlier in the shift (Q-73, Q-14, Q-32)
Such a notice has no history row at its snapshot. The trace uses the case's last history row at or before the snapshot, says so in the metrics line, and builds the transition from that row.

### R6 · Active causes and the raise-opening line (Q-75, §5, Q-02, Q-08, Q-39, Q-48)
- Listed: every active cause linked to the case with `linked_at` at or before the snapshot, in opening order. Each shows category, scope, link snapshot, opening snapshot and citation.
- A lift at or before the snapshot is shown with its citation, and the cause reads "lifted at L". A later lift is not shown, and the cause reads "in force at S".
- For each cause, the committed line of its opening snapshot O is read (R7 rules apply). It shows the proposal that opened the cause and the `apply_proposal` call that applied it, found by the **raise match**:
  1. **Applied proposals.** Take the coordinator calls of the line that are `apply_proposal` with `is_error = false`, in line order. Look up each call's `propuesta` among the line's investigator proposals and parse it into `ValidatedProposal` (from `{"id": …, "proposal": <the other keys>}`). A missing id or a parse failure drops the call.
  2. **Ordinal.** Number the applies whose proposal is a `RaiseProposal`, k = 1, 2, … in line order. The ledger names a new cause `active_cause_id_for(O, opened_count(O) + 1)` (`cases/ledger.py`), causes are never deleted, and in 009+ runs only `apply_proposal` opens causes. So the k-th successful raise apply of O opened `O-causa-k`.
  3. **Candidates.** A candidate is a raise apply whose proposal has the cause's `categoria`, its scope (`modelo`, `etapa`, `mercado`), and `Evidence(bitacora, fragmento.strip()) == cause.opened_by`.
  4. **Result.** The match is the single candidate whose ordinal k gives `active_cause_id_for(O, k) == cause.active_cause_id`. Zero candidates, two or more candidates, or an ordinal that disagrees all mean no match; the trace never picks one.
  5. **Rendering.** The stored proposal dict is kept for rendering, in stored key order.
- Fallbacks: "no committed trace line", "no matching proposal in the committed line". In a threshold-only directory the block is left out.

### R7 · Trace lines and resumed runs (Q-76, Q-44, Q-66, NFR-10)
- Every `trace-*.jsonl` under `traces_dir` is read, in file-name order, by `read_trace_files`. No file means a threshold-only run (Q-71: only agent mode writes them).
- For a snapshot the trace uses (the notice's, and each R6 opening snapshot), the single `committed` line is used.
- Each `aborted` line of the notice's snapshot is listed as an aborted attempt, with file, outcome (plus the investigator's outcome when present) and totals, without tool calls.
- Two `committed` lines for a used snapshot raise `CorruptTraces` (exit 2). Snapshots the trace does not use are parsed but never checked or shown (R11).

### R8 · Tool calls and hooks (Q-74, NFR-09)
- Investigator section (when the line has an `investigator` entry): outcome, trigger, its tool calls, then its accepted proposals.
- Coordinator section (when `coordinator` is in `line.ran`): outcome and its tool calls.
- Each call is on one line, with turn, name and arguments in full as compact JSON, `[error: …]` when `is_error`, and `→ this case` when:
  - a top-level `case_id` argument is a string equal to the case; or
  - the call is `emit_shift_report` and an item of `textos` has that `case_id`; or
  - the call is a successful `apply_proposal` that survives R6 step 1, and its parsed proposal is one of:
    - a `SetCauseProposal` for this case;
    - the R6 raise match of a cause linked to the case at this line's snapshot;
    - a `LiftProposal` whose `causa_activa` is a cause linked to the case at or before it.
- Nothing else is marked; an undeterminable case stays unmarked.
- Hooks: every record of the line (`agent`, `phase`, `hook`, `tool`, `turn`, `reason`), or `hooks: none`.
- Thinking summaries are never shown.

### R9 · Who set the severity, who wrote the text (Q-77, Q-31, Q-71)
- `severity set by: <origen>` (the contract value).
- `text written by:`
  - `agent` when the id is in the line's `notices_agent`;
  - `template` when it is in `notices_template` or the run is threshold-only;
  - otherwise `unknown`.
- Threshold-only directory: `trace: threshold-only run: no agent was involved`, exit 0.
- Agent directory, no committed line for the snapshot: `trace: no committed trace line for <S>` (aborted attempts still listed), exit 0.
- Committed line with `line.ran` empty and text `template`: `agents: none, no agent was involved`. In no other case is that sentence printed.

### R10 · Tokens (Q-74, ADR-0014, FR-37)
`tokens at <S>:` uses the committed line's stored `totals` only (both agents). No price card, no recomputation.

### R11 · Held-out guard (Q-79, FR-40, Q-37, Q-65)
- `policy = HeldOutPolicy.from_calendar(load_shifts(plant_dir / "turnos.csv"), heldout_first_shift, heldout_open)`.
- Before reading traces: `check_ids(policy, snapshots={notice snapshot}, shifts={evidence bitacoras}, where="notice <id>")`. A report is checked on its snapshot and `turno_id` (`where="report <id>"`) before its news ids are listed.
- After building the view: every snapshot and shift id it shows (`shown_snapshots`, `shown_shifts`) is checked the same way, so an R6 opening line is covered.
  - `shown_snapshots`:
    - the notice's snapshot;
    - the case's opening snapshot (its first history row);
    - the shown history row and its previous row;
    - each shown cause's `opened_at`, `linked_at` and shown `lifted_at`;
    - each opening line's snapshot;
    - the shown cited cause's `set_at` and the snapshot prefix of its `active_cause_id`;
    - the snapshot prefix of every `case_id`, `active_cause_id` and `causa_activa` argument shown (top-level, or inside `textos`);
    - the snapshot prefix of every `case_id` and `causa_activa` in a proposal shown.
  - `shown_shifts`:
    - the evidence `bitacora`s;
    - each shown cause's opening and shown lifting `bitacora`;
    - every `turno_id` and string `bitacora` argument shown;
    - the `bitacora` of every proposal shown.
  - Trace file names are not ids. Free text (`texto`, `[error: …]`, hook `reason`) is not parsed for ids: it comes from a line at or before S, written with data up to its own snapshot, so it is covered by construction.
- A refusal is a `DataLoadError` → stderr `<where>: <id> is held out`, exit 2, nothing on stdout.

### R12 · Rendering (Q-81, FR-20, I3, I4)
Fixed lines, in this order (labels in English; contract values and stored text as stored):
1. `notice <notice_id>`
2. `case <case_id>, snapshot <S>`
3. `type <tipo>, estado <estado>, severidad <s>, severidad_maxima <m>`
4. `metrics at <R>[ (last history row; no row at <S>)]: gap <u> units (<p> %), delay <d> days, bottleneck <stage|none>`. Variants: `(no shift plan)` for a null %, and `delay beyond the shipment horizon` for a null delay.
5. `severity at <R>: minimum <m>, effective <e>, raised <yes|no>`
6. `transition: <prev> (<prev R>) → <state> (<R>)`, or `transition: — → <state> (<R>)`
7. `motivo: <a, b>`, or `motivo: none`
8. `severity set by: <origen>`, then `text written by: <agent|template|unknown>`
9. `texto: "<texto>"`
10. `cause: <categoria>, etapa <etapa|none>[, recorded at <X>[ from <id>]]`
11. `evidence: none`, or `evidence:` followed by `  <bitacora>: "<fragmento>"` per item
12. `active causes: none`, or `active causes:` and per cause:
    - `  <id>: <categoria>, <scope.describe()>; linked at <L>; in force at <S>` (or `; lifted at <X>`);
    - `    opened at <O> by <bitacora>: "<fragmento>"`, plus `    lifted at <X> by <bitacora>: "<fragmento>"` when shown;
    - `    raise opened at <O> (<file>):`, then `      investigator proposal <json>` and `      coordinator turn <n> apply_proposal <json>`, or the one-line R6 fallback.
13. The trace part (R9). For a committed line:
    - `trace: committed line in <file> (decision <d>, reason <r|none>)`;
    - the aborted attempts: `aborted attempt in <file>: outcome <o>[, investigator <o>], <tokens>`;
    - the R9 sentence, the R8 sections (`investigator (outcome <o>, trigger <t>):`, `coordinator (outcome <o>):`, calls as `  turn <n> <name> <json>[ [error: <e>]][ → this case]`, proposals as `  proposal <json>`);
    - `hooks: none`, or `hooks:` with `  <agent> <phase> <hook> (<tool>, turn <n>): <reason>` (or `(turn <n>)` when `tool` is null);
    - `tokens at <S>: <tokens>`.

`<tokens>` is `input <i>, output <o>, cache read <r>, cache write <w5> (5m) <w1> (1h), usd <usd>`. JSON is `json.dumps(…, ensure_ascii=False, separators=(",", ":"))` in stored key order.

Every line goes through `escape_controls` before the lines are joined with `\n`. Each character in U+0000–U+001F, U+007F and U+0080–U+009F becomes `\xHH` (two lowercase hex digits). A `texto` with a newline therefore prints on one line.

### R13 · Exit codes and errors (Q-78)
- 0: shown.
- 1: unknown id, or a report id (R3).
- 2: invalid settings (same message as `run`), `DataLoadError` (plant files, held out), registry missing or unreadable (reader `ValueError`), unreadable or corrupt traces.
- Errors go to stderr as one line. A trace file that fails to parse or to open (`OSError`, e.g. a locked file) prints `traces: <file> is not a readable trace file (<ErrorClass>)`. `CorruptTraces` carries `two committed lines for <S> (<file>, <file>)` with no prefix; `_trace` catches it and re-raises `ValueError(f"traces: {exc}")`, so stderr reads `traces: two committed lines for <S> (<file>, <file>)`.

### R14 · Imports (Q-72)
- `telemetry/trace_query.py` and `telemetry/trace_render.py` import only `domain` and `telemetry`.
- `cases/registry/notice_reader.py` imports only `domain` and `cases.registry`. `domain/stored.py` follows the domain rule.
- `runner/cli.py` keeps its 012 R11 layers. The `runner/summary.py` and `cases` rules are unchanged, and no new module imports `anthropic` or `mcp`.

### R15 · Demo (Q-83)
- Now: a draft `docs/demo.md` with:
  - steps and timings;
  - the live command `uv run plant-monitor run --speed <s>`, then `uv run plant-monitor trace <id>`;
  - both candidate alerts: the Europe audit (EUR-0305, T07 → T10) and the Pickup stop raised by the agent (T17 → T19);
  - a dry run on synthetic fixtures: `uv run pytest tests/integration/test_trace_cli.py --basetemp z_helps/dry-run`, which leaves real `OUTPUT_DIR`s to inspect.
- After the held-out run, manual and each with the user's permission:
  - choose the alert;
  - check its trace by hand against `criterio.md`;
  - finish the script;
  - rehearse with a recorded fallback (a copy of the held-out `OUTPUT_DIR`).

## Worked examples

**Notation.** Everything from the 012 builders: `write_cli_data`, `cli_settings`, `cli_deps`, `never_model`, `ALL`, `HEAD`, `S002`, `S004`, `S005`, `S010_JUDGE`, `turn`, `logbook`, `alert`, `report`, `PL_CASE`, `PB_CASE`, `SE_CASE`, `USAGE` (3,000 in / 200 out, so 0.0004 USD per call at the Settings default prices), `STARTED`, `SECOND_START`; `F2` and `F5` from `incident_runs` (`‹F5›` below means `F5` verbatim).
- **S010_EMIT_HOOKED** = `[turn(2, logbook("T05")), turn(3, alert("S010", PL_CASE), alert("S010", PB_CASE), report("S010", PL_CASE, PB_CASE))]`. The coordinator's `get_logbook` is blocked by the allowlist hook.
- **PRICES** = settings overrides pinned in every agent-mode example, so the byte-exact `usd` values do not depend on Settings defaults:
  - `price_input_per_mtok=0.10`, `price_output_per_mtok=0.50`;
  - `price_cache_read_per_mtok=0.01`, `price_cache_write_5m_per_mtok=0.125`, `price_cache_write_1h_per_mtok=0.20`.

  With USAGE that is 0.0004 USD per call. FakeModel reports no cache tokens.
- **AGENT_DIR** = `write_cli_data(tmp, ALL[:10])`, `main(["run"])` with SET + PRICES and `FakeModel([*HEAD, *S010_JUDGE, *S010_EMIT_HOOKED])` at `STARTED`. The trace file is `trace-20260302T230000Z.jsonl`.
  - It is built once per test module (module-scoped fixture over `tmp_path_factory`).
  - Tests that mutate a directory work on a copy.
- **TH_DIR** = `write_cli_data(tmp, ALL)`, `main(["run", "--thresholds-only"])` with SET and `anthropic_api_key=None`. Also module-scoped and copied before any mutation.
- **T(id)** = `main(["trace", id], deps=cli_deps(<settings>, None))`: `never_model`, no sleep.
- US-10 mapping: "alert at S020 for Pickup × Local" ↦ the IF Pickup × Local alert at S010.

| Id | Input (rule) | Expected |
|---|---|---|
| E1 | **US-10: agent alert with a hook block (R1, R4, R6, R7, R8, R9, R10, R12; FR-38).** AGENT_DIR, `T("S010-alerta_inmediata-S010-Pickup-Local")` | 0. stdout is exactly block **E1** below. **R11 drift guard:** the test also builds the view from the same inputs. Every `\bS\d{3}\b` token of stdout must be in `shown_snapshots()`, and every `\bT\d{2}\b` token in `shown_shifts()`. |
| E2 | **Threshold-only alert (R4, R9, R12; Q-77, Q-17).** TH_DIR, `T("S012-alerta_inmediata-S010-Pickup-Local")` with SET (`anthropic_api_key=None`) | 0. stdout is exactly block **E2**, with `<texto>` = the stored notice's `texto` (from `read_deliverables`). The cause has `etapa none` (Q-17, Q-32). |
| E3 | **Raise opened at another snapshot (R6; §5, Q-08, Q-39, Q-48).** AGENT_DIR, `T("S005-alerta_inmediata-S005-SUV-Europa")` | 0. stdout is exactly block **E3**. The lift of `S004-causa-1` at S008 is not shown (after S005). |
| E4 | **Unknown id and report id (R3, R13).** AGENT_DIR: (a) `T("S099-alerta_inmediata-S010-Pickup-Local")`; (b) `T("T05-informe")` | (a) 1; stderr `unknown notice_id: S099-alerta_inmediata-S010-Pickup-Local`; stdout empty. (b) 1; stderr `T05-informe is a shift report, not a notice; its novedades: S010-informe_de_turno-S010-Pickup-Local, S010-informe_de_turno-S010-Pickup-Brasil`; stdout empty. |
| E5 | **Resumed run (R7; Q-76).** `write_cli_data(tmp, ALL[:5])`, SET + PRICES. Run 1: `main(["run"])`, `FakeModel([*S002, *S004, ModelCallFailed("create", 529)])` at STARTED → 2. Run 2, same O: `FakeModel([*S005])` at SECOND_START → 0. Then `T("S005-alerta_inmediata-S005-SUV-Europa")` | 0. stdout equals block E3 except the `trace:` line, which reads `trace: committed line in trace-20260302T233000Z.jsonl (decision call, reason text_needed)`, followed by `aborted attempt in trace-20260302T230000Z.jsonl: outcome aborted:ModelCallFailed, input 0, output 0, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00000000`. The `raise opened at S004 (trace-20260302T230000Z.jsonl):` block still reads the first file. |
| E6 | **Agent-mode silence with no agent (R9; Q-77, Q-14, Q-25).** AGENT_DIR, `T("S007-sin_aviso-S005-SUV-Europa")` | 0. stdout includes, in order: `type sin_aviso, estado escalado, severidad critica, severidad_maxima critica`; `metrics at S007: gap 0.0 units (0.0 %), delay 0.0 days, bottleneck none`; `severity at S007: minimum ninguna, effective critica, raised yes`; `transition: escalado (S006) → escalado (S007)`; `motivo: bitacora`; `severity set by: agente`; `text written by: template`; `trace: committed line in trace-20260302T230000Z.jsonl (decision skip, reason no_text_needed)`; `agents: none, no agent was involved`; `hooks: none`; `tokens at S007: input 0, output 0, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00000000`. E1's stdout has no `no agent was involved`. |
| E7 | **Held-out refusal (R11, R13; Q-79).** TH_DIR, settings with `heldout_open=False` (first shift T06): (a) `T("S012-alerta_inmediata-S010-Pickup-Local")`; (b) `T("T06-informe")` | (a) 2; stderr `notice S012-alerta_inmediata-S010-Pickup-Local: S012 is held out`; stdout empty. (b) 2; stderr `report T06-informe: S012 is held out`; the news ids are not printed. |
| E8 | **Risk: read-only (R2, R13).** (a) TH_DIR: record the registry bytes and the set of paths under O, run E2's `T`; (b) an O2 that does not exist, `T("S012-alerta_inmediata-S010-Pickup-Local")` | (a) 0; the bytes and the path set are unchanged (no `-journal`, no `-wal`, no new directory); `never_model` was not called. (b) 2; stderr contains `registry not found`; O2 does not exist. |
| E9 | **Call marking (R8).** Unit, built by hand. Case `C = S019-Pickup-Local`, notice at S020. Investigator proposals: `S020-p1` set_cause C; `S020-p2` set_cause `S020-SUV-Local`; `S020-p3` lift `S010-causa-1`; `S020-p4` raise Pickup/montaje/any from (T10, `f`). `StoredNotice` causes: `S010-causa-1` and `S020-causa-1` (matches p4, ordinal 1). Its links: `S010-causa-1` at S019, `S020-causa-1` at S021. Coordinator calls: (1) `get_case {"case_id": C}`; (2) `get_case {"case_id": "S020-SUV-Local"}`; (3) `emit_shift_report` with items `S020-SUV-Local`, then C; (4) `apply_proposal S020-p1`; (5) `apply_proposal S020-p2`; (6) `apply_proposal S020-p3`; (7) `apply_proposal S020-p4`; (8) `apply_proposal S020-p1` with `is_error`; (9) `apply_proposal S020-p9` (absent); (10) `emit_alert {"case_id": 7}` | `this_case` is true for (1), (3), (4), (6); false for (2), (5), (7) (linked after S020, so not shown either), (8), (9), (10). |
| E10 | **Risk: a logbook cannot drive the terminal (R12; Q-81, FR-20).** Unit, by hand: `texto` = `"ver " + ESC + "[31mrojo" + ESC + "[0m"`, evidence (T10, `"parada" + BEL + " total" + DEL`), a coordinator call `emit_alert {"case_id": C, "texto": "a" + U+009B + "b"}` | Output contains `texto: "ver \x1b[31mrojo\x1b[0m"` (literal backslash), `  T10: "parada\x07 total\x7f"` and `{"case_id":"S019-Pickup-Local","texto":"a\x9bb"}`. No character of the output is in U+0000–U+001F (except the `\n` separators), U+007F or U+0080–U+009F. |
| E11 | **Reader (R2, R3, R14).** Unit: `incident_run(path=tmp/"registry.sqlite3")` steps S001–S006, with S004's decision raising `SUV_EUROPE` from `EV_T02` (as 008); then `read_notice(path, …)`: (a) `S005-alerta_inmediata-S005-SUV-Europa`; (b) `T03-informe`; (c) `S005-sin_aviso-X`; (d) a copy of the file with `active_cause_links` dropped; (e) a missing path | (a) `StoredNotice`: `notice.motivo == (bitacora,)`; history S005, S006 rows; `order == {S001: 1, …, S006: 6}`; causes `[S004-causa-1]` in force; `links == {"S004-causa-1": "S005"}`; `cited.set_at == "S005"`, `cited.active_cause_id == "S004-causa-1"`. (b) A `ShiftReport` with `turno_id == "T03"` whose `novedades` ids are `("S006-informe_de_turno-S005-SUV-Europa",)`. (c) None. (d) `ValueError` naming `active_cause_links`. (e) `ValueError` (`registry not found`); the path is not created. In (a)–(c) the file bytes are unchanged. |
| E12 | **Risk: imports (R14).** A new test in `tests/unit/test_import_boundaries.py` for `cases/registry/notice_reader.py` | It imports only `plant_monitor.domain` and `plant_monitor.cases.registry`, and neither `anthropic` nor `mcp`. The telemetry modules and `domain/stored.py` are already covered by the existing telemetry and domain scans; no extra test. |
| E13 | **Corrupt traces (R7, R13).** (a) a copy of TH_DIR plus `traces/trace-20260301T000000Z.jsonl` holding `{broken`, then E2's `T`; (b) a copy of AGENT_DIR with its trace file copied to `trace-20260302T235900Z.jsonl`, then E3's `T` | (a) 2; stderr `traces: trace-20260301T000000Z.jsonl is not a readable trace file (ValidationError)`. (b) 2; stderr `traces: two committed lines for S005 (trace-20260302T230000Z.jsonl, trace-20260302T235900Z.jsonl)`. stdout empty in both. |
| E14 | **Trace files in name order (R7, I10).** Unit, `tmp_path/traces`: `trace-20260302T233000Z.jsonl` (one S005 line), `trace-20260302T230000Z.jsonl` (one S004 line), `notes.txt`; also an empty directory, a missing one, and a directory whose `trace-20260301T000000Z.jsonl` holds `{broken` | `read_trace_files` returns two `TraceFile`s, `trace-20260302T230000Z.jsonl` first, each with its one line; `notes.txt` is ignored. The empty and the missing directory both give `()`. The broken file raises `ValueError` with the one-line message `trace-20260301T000000Z.jsonl is not a readable trace file (ValidationError)`. |

**E1** (byte-exact, plus the final `\n` from `print`):
```
notice S010-alerta_inmediata-S010-Pickup-Local
case S010-Pickup-Local, snapshot S010
type alerta_inmediata, estado escalado, severidad critica, severidad_maxima critica
metrics at S010: gap -4.0 units (-13.3 %), delay 0.0 days, bottleneck montaje
severity at S010: minimum media, effective critica, raised yes
transition: — → escalado (S010)
motivo: bitacora
severity set by: agente
text written by: agent
texto: "Agente: S010-alerta_inmediata-S010-Pickup-Local"
cause: parada_de_linea, etapa montaje, recorded at S010 from S010-causa-1
evidence:
  T05: "‹F5›"
active causes:
  S010-causa-1: parada_de_linea, Pickup in montaje, any market; linked at S010; in force at S010
    opened at S010 by T05: "‹F5›"
    raise opened at S010 (trace-20260302T230000Z.jsonl):
      investigator proposal {"id":"S010-p1","tipo":"raise","categoria":"parada_de_linea","etapa":"montaje","modelo":"Pickup","mercado":null,"bitacora":"T05","fragmento":"‹F5›","estado_causa":"activa_sin_fecha"}
      coordinator turn 1 apply_proposal {"propuesta":"S010-p1"}
trace: committed line in trace-20260302T230000Z.jsonl (decision call, reason text_needed)
investigator (outcome done, trigger review):
  turn 1 get_logbook {"turno_id":"T05"}
  proposal {"id":"S010-p1","tipo":"raise","categoria":"parada_de_linea","etapa":"montaje","modelo":"Pickup","mercado":null,"bitacora":"T05","fragmento":"‹F5›","estado_causa":"activa_sin_fecha"}
coordinator (outcome done):
  turn 1 apply_proposal {"propuesta":"S010-p1"} → this case
  turn 2 get_logbook {"turno_id":"T05"} [error: tool get_logbook is not allowed for the coordinator]
  turn 3 emit_alert {"case_id":"S010-Pickup-Local","texto":"Agente: S010-alerta_inmediata-S010-Pickup-Local"} → this case
  turn 3 emit_alert {"case_id":"S010-Pickup-Brasil","texto":"Agente: S010-alerta_inmediata-S010-Pickup-Brasil"}
  turn 3 emit_shift_report {"textos":[{"case_id":"S010-Pickup-Local","texto":"Agente: S010-informe_de_turno-S010-Pickup-Local"},{"case_id":"S010-Pickup-Brasil","texto":"Agente: S010-informe_de_turno-S010-Pickup-Brasil"}]} → this case
hooks:
  coordinator pre_tool allowlist (get_logbook, turn 2): tool get_logbook is not allowed for the coordinator
tokens at S010: input 15000, output 1000, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00200000
```
Where the numbers come from: gap −4 of a daily plan of 30 is −13.3 % (`media`). U-PL-001 has been in `montaje` 840 min against 540 + 60, so the bottleneck is `montaje`. It still reaches LOC-0304, so the delay is 0. The raise makes it `critica` (Q-31). Tokens: 2 investigator calls and 3 coordinator calls × USAGE.

**E2** (byte-exact, `<texto>` substituted):
```
notice S012-alerta_inmediata-S010-Pickup-Local
case S010-Pickup-Local, snapshot S012
type alerta_inmediata, estado escalado, severidad critica, severidad_maxima critica
metrics at S012: gap -11.0 units (-36.7 %), delay 0.0 days, bottleneck none
severity at S012: minimum critica, effective critica, raised no
transition: en_seguimiento (S011) → escalado (S012)
motivo: gap
severity set by: umbral
text written by: template
texto: "<texto>"
cause: no_declarada, etapa none
evidence: none
active causes: none
trace: threshold-only run: no agent was involved
```

**E3** (byte-exact):
```
notice S005-alerta_inmediata-S005-SUV-Europa
case S005-SUV-Europa, snapshot S005
type alerta_inmediata, estado escalado, severidad critica, severidad_maxima critica
metrics at S005: gap -4.0 units (-13.3 %), delay 0.0 days, bottleneck calidad
severity at S005: minimum media, effective critica, raised yes
transition: — → escalado (S005)
motivo: bitacora
severity set by: agente
text written by: agent
texto: "Agente: S005-alerta_inmediata-S005-SUV-Europa"
cause: retencion_de_calidad, etapa calidad, recorded at S005 from S004-causa-1
evidence:
  T02: "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
active causes:
  S004-causa-1: retencion_de_calidad, SUV in calidad, Europa; linked at S005; in force at S005
    opened at S004 by T02: "llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación"
    raise opened at S004 (trace-20260302T230000Z.jsonl):
      investigator proposal {"id":"S004-p1","tipo":"raise","categoria":"retencion_de_calidad","etapa":"calidad","modelo":"SUV","mercado":"Europa","bitacora":"T02","fragmento":"llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación","estado_causa":"activa_sin_fecha"}
      coordinator turn 1 apply_proposal {"propuesta":"S004-p1"}
trace: committed line in trace-20260302T230000Z.jsonl (decision call, reason text_needed)
coordinator (outcome done):
  turn 1 emit_alert {"case_id":"S005-SUV-Europa","texto":"Agente: S005-alerta_inmediata-S005-SUV-Europa"} → this case
hooks: none
tokens at S005: input 3000, output 200, cache read 0, cache write 0 (5m) 0 (1h), usd 0.00040000
```

## Edge cases and assumptions
- **X1** · News of a case resolved earlier in the shift (R5). Unit, by hand: case `S015-SUV-Local` with rows S015 `abierto`/`media`, S016 `en_seguimiento`/`ninguna`, S017 `resuelto`/`ninguna`; notice `S018-informe_de_turno-S015-SUV-Local` at S018. The output has `metrics at S017 (last history row; no row at S018): …`, `severity at S017: minimum ninguna, effective ninguna, raised no`, `transition: en_seguimiento (S016) → resuelto (S017)`, `motivo: none`.
- **X2** · Missing lines (R6, R9). Unit, by hand, asserted on the `render_notice_trace` output: (a) traces with no committed line for the notice's snapshot → `trace: no committed trace line for S020` and `text written by: unknown`; (b) a linked cause opened at S004 with no S004 line → `    raise opened at S004: no committed trace line`; (c) an S004 line without a matching proposal → `    raise opened at S004: no matching proposal in the committed line`.
- **X3** · Old trace lines (R7, R8; Q-44). A committed line written as JSON without `hooks`, `agents_run`, `investigator`, `proposals_applied` and `prefix_hash`, with `decision` `call`. It renders a coordinator section (the `ran` fallback) and `hooks: none`.
- **X4** · Null metrics (R12, Q-04, Q-16). Unit render, parametrized: `gap_pct` None → `gap -4.0 units (no shift plan)`; `delay_days` None → `delay beyond the shipment horizon`; `gap_units = -0.04` → `gap 0.0 units`. They do not occur in days 1–7, but a crash on None would.
- **X5** · `etapa = null` is shown as `etapa none` (E2). No extra test.
- **X6** · A backslash in stored text is not escaped. The output is for reading, not round-trip.
- **X7** · A Ctrl-C inside a snapshot (012 X1) or a trace write `OSError` leaves no line. That is X2 (a).
- **X8** · Lines written by 008-era runs applied raises with `raise_severity`, not proposals, so there is no proposal to parse. Their opening block falls back to "no matching proposal" (X2 c). Spec 008 runs are not demo material.
- **X10** · Ambiguous raise match (R6 steps 3–4). Unit, by hand: cause `S004-causa-1` (SUV/calidad/Europa, T02 `F2`) and an S004 line whose proposals `S004-p1` and `S004-p2` are identical raises.
  - (a) `apply_proposal S004-p1` succeeds and `apply_proposal S004-p2` has `is_error` (refused as a duplicate raise, Q-30). One candidate, ordinal 1 → shown with `S004-p1` and its turn.
  - (b) A hand-built line where both applies succeed: two candidates → `    raise opened at S004: no matching proposal in the committed line`.
  - (c) One successful apply of `S004-p1`, but the cause is `S004-causa-2`: the ordinal disagrees → the same fallback.
- **X9** · Lines of held-out snapshots may be parsed (`read_trace` reads whole files) but are never selected, checked for duplicates or shown (R7, R11).
- **X11** · Report with no news (R3; ADR-0015 allows an empty report). A registry holding `T05-informe` with empty `novedades` → `plant-monitor trace T05-informe` exits 1, stderr `T05-informe is a shift report, not a notice; its novedades: none`, stdout empty.
- **X12** · Lift shown or not (R4, R11, R12). Unit, by hand: notice at S010 linked to cause `S004-causa-1` (opened at S004 by T02 `F2`).
  - (a) Lifted at S008 by T04 with fragment `"auditoría cerrada"`: the cause line ends `; lifted at S008`, the next lines include `    lifted at S008 by T04: "auditoría cerrada"`, S008 is in `shown_snapshots` and T04 in `shown_shifts`.
  - (b) Lifted at S012 by T06: the cause line ends `; in force at S010`, no `lifted at` line, and neither S012 nor T06 is in the shown sets.
- **X13** · Ids inside 008 write-tool arguments (R11). Unit, by hand: a committed line at S010 whose coordinator calls `set_cause` with `active_cause_id` `S004-causa-1` and `bitacora` `T02`, and a shown proposal with `causa_activa` `S006-causa-1` → S004 and S006 are in `shown_snapshots`, T02 in `shown_shifts`; a printed `cited.active_cause_id` `S004-causa-1` adds S004.

## Acceptance
- [x] E1–E14, X1–X4 and X10–X13 pass on synthetic fixtures with `FakeModel`; CI makes no network call (NFR-07). Every new test cites its spec id (`Risk:` tests too).
- [x] Specs 001–012 tests pass unchanged. None is expected to change; if one must, it is re-expected (never deleted) and listed here.
- [x] Refactors of earlier modules, no behavior and no test-expectation change:
  - `runner/summary.py`: `Mode` becomes an alias of `telemetry.trace.TraceMode` (I9);
  - `runner/cli.py` `_report`: series lines come from `read_trace_files` (I10); the one visible change is that an unreadable trace now prints `summary unavailable: <file> is not a readable trace file (<ErrorClass>)` instead of pydantic's multi-line text, with no 012 expectation changed;
  - `notify/console.py`: `write_safe` extracted from `ConsoleNotifier._write` (I5);
  - `cases/registry/cases_repo.py`, `causes_repo.py`: public column tuples and row parsers (I6).
- [x] `incident_run` gains an optional `path` (default `":memory:"`); existing callers are unchanged.
- [x] Docs: README "How to trace a notice", `docs/STRUCTURE.md` (three modules, `cli.py` row, dependency lines), roadmap row 013, ADR-0019 (main session), draft `docs/demo.md`.
- [ ] Manual, after the held-out run, each with the user's permission (Q-83): demo alert chosen and checked by hand against `criterio.md`; script finished; rehearsal with a recorded fallback.
- [x] `ruff`, `mypy --strict`, `pytest --cov` pass.

## Size
About 32 KB, over budget. The design review added the raise-match algorithm (R6) and the id sets of the drift guard (R11). Blocks E1–E3 are byte-exact, as asked, and R12 has to fix the layout line by line for them to be testable. Splitting the reader from the command would leave the trace untestable end to end.
