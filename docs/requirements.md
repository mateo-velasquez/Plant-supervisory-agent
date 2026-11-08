# Requirements

Functional and non-functional requirements for the plant supervisory agent. Every story, spec and test traces back to an ID in this document.

**Sources:** the project brief (`z_helps/Proyecto_Final_Monitoreo_en_planta.md`), the domain criteria (`data/reglas/criterio.md`, cited as §n) and thresholds (`data/reglas/umbrales.yaml`), and inspection of the input data (days 1–7 only).

**Owner** says who resolves the requirement:
- **Code:** deterministic Python.
- **Agent:** the LLM.
- **Design:** our choice, recorded in an ADR.

**Week** is the delivery milestone (W1 = M1+M2 … W6 = full series).

## 1. Glossary

| Term | Meaning |
|---|---|
| Combination | A `modelo × mercado` pair (3 models × 3 markets = 9). |
| Snapshot | The plant state every 4 h (`S001`–`S060`): units in plant plus units released since the previous snapshot. |
| Shift | 8 h (`T01`–`T30`), with a mid snapshot and a closing snapshot. |
| Deviation | A combination whose minimum severity is `media` or higher. |
| Minimum severity | The severity computed by code from thresholds. It is a floor: the agent may raise it, never lower it. |
| Case | The lifecycle of one deviation of one combination: `abierto` → `en_seguimiento` → `escalado` → `resuelto`. |
| Logbook | The free-text shift report written by the supervisor (`bitacoras/Txx.txt`). |
| Notice | `alerta_inmediata`, `informe_de_turno` or `sin_aviso`. |

## 2. Input data contract

| Source | Content |
|---|---|
| `snapshots/Sxxx.json` | `snapshot_id`, `timestamp`, `turno` and `unidades[]`. Each unit has `unidad_id`, `modelo`, `mercado`, `color`, `etapa`, `ingreso_etapa`, `retrabajos` and `embarque_asignado`. Also `liberadas[]`, each with `unidad_id`, `modelo`, `mercado` and `hora`. |
| `snapshots/llegadas.csv` | `orden`, `snapshot_id`, `archivo`, `recibido`. 61 arrivals for 60 snapshots; `S034` arrives twice. |
| `planta/plan_produccion.csv` | `turno_id`, `fecha`, `turno`, `modelo`, `mercado`, `unidades_plan`. |
| `planta/tiempos_estandar.csv` | `modelo`, `etapa`, `minutos_estandar`, `minutos_retrabajo` (only for `pintura`). |
| `planta/embarques.csv` | `embarque_id`, `mercado`, `medio`, `corte_en_patio`, `salida`. Brazil and Local trucks leave daily; the Europe ship leaves weekly on Thursdays. |
| `planta/turnos.csv` | `turno_id`, `fecha`, `turno`, `inicio`, `fin`, `snapshot_medio`, `snapshot_cierre`. |
| `bitacoras/Txx.txt` | One logbook per shift. |

Stage order: `carroceria` → `pintura` → `montaje` → `calidad` → `patio` → `despacho`.

## 3. Functional requirements

### 3.1 Ingestion

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-01 | Process snapshots one by one in the order given by `llegadas.csv`. | Code | W1 |
| FR-02 | **Idempotency:** a snapshot that arrives more than once (`S034`) is processed once. A repeat produces no new cases, notices or state changes. | Code | W1 (hardened W5) |
| FR-03 | Validate every input against a typed schema and fail with an explicit error on malformed data. Handle the real formats: CSVs are UTF-8 **with BOM**, and `turnos.csv.fecha` uses `M/D/YYYY`, so dates come from the ISO `inicio`/`fin` fields. | Code | W1 |
| FR-04 | Map each snapshot to its shift, and identify mid and closing snapshots from `turnos.csv`. | Code | W1 |

### 3.2 Deviation metrics (§1–§2)

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-05 | **Actual progress** per combination: the number of distinct `unidad_id` in `liberadas` since the first snapshot. A unit released twice counts once. | Code | W1 |
| FR-06 | **Cumulative plan:** the plan of all previous shifts, plus half of the current shift's plan at the mid snapshot or all of it at the closing snapshot. | Code | W1 |
| FR-07 | **Gap** = actual progress − cumulative plan, in units and as a % of the daily plan (current shift plan × 3). Negative means behind. | Code | W1 |
| FR-08 | **Projected yard arrival** per unit not yet in `patio`/`despacho`: snapshot time + max(0, standard − elapsed in current stage) + standards of the remaining stages through `calidad`. A unit in `pintura` with `retrabajos > 0` is being repainted and uses `minutos_retrabajo`. | Code | W1 |
| FR-09 | **Delay in days:** the reachable shipment is the first shipment of the unit's market whose `corte_en_patio` is later than the projected arrival. Delay = days between its `salida` and the assigned shipment's `salida`. The combination's delay is that of its most delayed unit. | Code | W1 |
| FR-10 | **Bottleneck stage:** the stage with the most delayed units, i.e. elapsed > standard + `tolerancia_minutos` (60), plus units being repainted. | Code | W1 |
| FR-11 | **Minimum severity** = max(gap severity, delay severity) using `umbrales.yaml`. There is no gap severity below `minimo_unidades` (3) units behind. Brazil and Europe have no `media` delay level. A deviation exists when minimum severity ≥ `media`. Thresholds are read from config, never hard-coded. | Code | W1 |

### 3.3 Case registry and lifecycle (§3)

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-12 | At most **one active case per combination**. A case opens when a combination without an active case has a deviation. | Code | W1 |
| FR-13 | **Lifecycle:** `abierto` in its opening snapshot and `en_seguimiento` from the next one. It becomes `escalado` when severity reaches `critica` (by threshold or by agent) and stays `escalado` even if severity drops. It becomes `resuelto` after 2 consecutive snapshots without deviation and with no agent escalation in force. A later deviation opens a **new** case. Applied in code; an agent raise in force is an input (Q-25, Q-26, Q-27). | Code | W1 |
| FR-14 | The registry lives **outside the model** and persists, per case: state, current severity, max severity since the last report, last reported state/severity, and history with snapshot IDs. | Code | W1 |
| FR-15 | Severity may only be raised above the minimum, never lowered below it. Enforced in code. | Code | W1 (hook in W4) |

### 3.4 Cause and escalation from logbooks (§5–§6)

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-16 | Each case has a **cause**: a category from the catalog (`parada_de_linea`, `faltante_de_piezas`, `retrabajo`, `retencion_de_calidad`, `ausentismo`, `no_declarada`) and a stage. | Agent | W2 |
| FR-17 | Every cause cites **logbook ID + verbatim fragment**. Code verifies that the fragment exists in the cited logbook. | Agent + Code | W2 |
| FR-18 | If no logbook names the cause, it is `no_declarada`, with the bottleneck stage from the data. It is never filled with a guess. | Agent | W2 |
| FR-19 | **Logbook escalation:** if a logbook says the cause is ongoing with no resolution date, the agent raises the case to `critica`, citing the fragment. The raise applies to all active cases with that cause and to cases opened while it is in force. It ends when a later logbook reports the cause resolved. A concrete resolution date, or an already-resolved problem, does **not** raise severity. | Agent | W2 |
| FR-20 | Logbooks are **untrusted data**. Unrelated content (safety, pending items) is ignored, and instructions inside a logbook are never followed. | Agent + Design | W3 |

### 3.5 Notices and reports (§4)

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-21 | **Immediate alert** in the same snapshot where a case becomes `escalado`. At most one per case. | Design | W1 |
| FR-22 | **Shift report** at each closing snapshot (30 in total), with two parts. **News:** new cases, cases resolved in the shift, cases whose state or severity changed since the last report they appeared in (`abierto` ≡ `en_seguimiento`), and cases whose in-shift peak exceeded their closing severity. **Active cases:** every active case with gap, delay, severity, state and bottleneck stage. | Design | W1 |
| FR-23 | Every case in a report carries its current severity and its max severity since the previous report (Q-28). | Code | W1 |
| FR-24 | **No notice:** a case unchanged since its last report is not repeated as news. | Design | W1 |
| FR-25 | Every notice records `notice_id`, `snapshot_id`, `case_id`, `modelo`, `mercado`, `tipo`, `severidad`, `severidad_maxima`, `estado`, `origen` (`umbral` or `agente`), `motivo` (a list, Q-13, Q-31), `causa {categoria, etapa}`, `evidencia [{bitacora, fragmento}]` and `texto`. Every report records `turno_id`, `snapshot_id`, `novedades` and `casos_activos`. | Code | W1 (validated W5) |
| FR-26 | The output channel is pluggable (port/adapter). The minimum is a file per shift plus the console. | Design | W1 |

### 3.6 Agent architecture and control

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-27 | Our own **MCP server** exposes the data-query and registry tools. The agent never receives full datasets in the prompt. | Design | W1 |
| FR-28 | **Multi-agent:** separate perspectives for plan gap, shipment risk and bottleneck, with **a single agent allowed to write** to the registry. Each agent's capabilities are documented. | Design | W3 |
| FR-29 | Only what changed since the previous snapshot is sent to the model. | Design | W3 |
| FR-30 | The criteria reach the agent as an **MCP prompt** served by our server. | Design | W4 |
| FR-31 | **Hooks** before each tool, after each tool and on stop. They block with a reason returned to the model as an error: (a) a notice repeated without news; (b) a severity below the computed minimum; (c) a shift report missing an active case. | Code | W4 |
| FR-32 | **Per-agent tool allowlists** enforced in code, not in the prompt. | Code | W4 |
| FR-33 | **Unattended run:** the series advances and shift closings fire without manual intervention. | Code | W4 |
| FR-34 | **Structured output** validated against schemas, with retry on validation failure. | Code | W5 |
| FR-35 | **Prompt caching** of the stable prefix, verified through `cache_read_input_tokens`. | Design | W5 |
| FR-36 | The full series (61 arrivals) runs with **one command**. | Code | W6 |
| FR-37 | Each run reports its **cost** (input/output/cache tokens, USD) and **duration**. | Code | W3 (full W6) |
| FR-38 | **Traceability:** for any notice, the snapshot, reason and citation can be reconstructed from a trace log. | Code | W1 (demo W7) |

### 3.7 Evaluation

| ID | Requirement | Owner | Week |
|---|---|---|---|
| FR-39 | Our own **evaluator** with hand-verified golden cases, measuring: **notices**, meaning alerts in the escalation snapshot exactly once and reports with neither missing nor extra news; **cause**, meaning category and stage match and the fragment exists in the cited logbook; **noise**, meaning news repeated with no change, counted by comparing consecutive reports. | Code | W1 (grows weekly) |
| FR-40 | **Held-out set:** days 8–10 (shifts `T22`–`T30`, snapshots `S043`–`S060`) are not used for tuning until W5. They are then run once as-is, and failures are logged before any change. | Process | W5 |

### 3.8 Optional (stretch)

| ID | Requirement | Owner |
|---|---|---|
| FR-41 | **Early warning:** project the trend and alert before a threshold is crossed, with an estimated time. | Code + Agent |
| FR-42 | **Missing snapshots:** detect and declare a gap in the series instead of reading it as a recovery. | Code |
| FR-43 | **Action proposals:** suggest actions with estimated impact in days, always framed as proposals. | Agent |

## 4. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-01 | **Model:** `claude-haiku-5-5` with thinking on; `effort` configurable through settings. |
| NFR-02 | **Prompt budget:** no request exceeds 100k prompt tokens (it costs 5×). A guard measures and blocks before sending. |
| NFR-03 | **Cost efficiency:** deltas only, cached prefix, minimal tool output. The cost of days 1–7 and of the full series is measured and reported. |
| NFR-04 | **Determinism:** the same inputs always produce the same metrics, cases and threshold-driven notices. |
| NFR-05 | **Reproducibility:** pinned dependencies (`uv.lock`); one command for the full series. |
| NFR-06 | **Security:** secrets only through settings (`SecretStr`), never logged; prompt-injection defense on logbooks. |
| NFR-07 | **Testability:** domain logic is unit-tested with synthetic fixtures; CI never calls the LLM. |
| NFR-08 | **Maintainability:** rules and thresholds live in config; every significant design decision gets an ADR and a line in the README. |
| NFR-09 | **Observability:** structured logs per snapshot (decisions, tool calls, tokens, latency). |
| NFR-10 | **Resilience:** API calls retry with exponential backoff; a failed snapshot is resumable without reprocessing earlier ones. |
| NFR-11 | **Portability:** runs on Windows (development) and Linux (CI). |

## 5. Assumptions and open questions

| ID | Topic | Working assumption (to confirm) |
|---|---|---|
| Q-01 | When is a logbook readable? | **Decided.** Logbook `Txx` becomes available at its shift's closing snapshot: the closing snapshot is the first to see it, so the shift report can cite its own shift. A mid snapshot only sees earlier logbooks, so the system cannot see the future. Derived from `snapshot_cierre` in calendar order, never from ids (T07 at S014, T10 at S020). The current snapshot comes from a per-snapshot frame set by code, never from a tool argument. A citation from a logbook not yet readable at the citing snapshot is rejected (spec 008 applies it to golden evidence; spec 005's golden check stays availability-free). Set in spec 006. |
| Q-02 | Linking a logbook cause to cases | The match uses the stage and/or model named in the logbook, compared with each case's bottleneck. US-07 points to model + stage (a Pickup assembly stop applies to every Pickup market). The rule is set in spec 008. |
| Q-03 | Bottleneck tie-break | If two stages tie, pick the most downstream one (closest to yard). Confirmed; set in spec 001. |
| Q-04 | No reachable shipment in `embarques.csv` | The unit's delay is `None`. If any eligible unit's delay is `None`, the combination's delay is `None` (the worst unit dominates), `delay_beyond_horizon` is True and the delay severity is `critica`. Defensive only: with consistent data it cannot happen, since the projection is bounded by the remaining standards and `embarques.csv` extends well beyond the series. Set in spec 001. |
| Q-05 | Delay when the assigned shipment has already left | The same formula applies; the delay is relative to the assigned departure. |
| Q-06 | Daily plan for % gap | "Current shift plan × 3", literally from §1, even if the other shifts of the day differ. |
| Q-07 | Threshold boundaries | Inclusive: a value equal to a threshold reaches that level (e.g. exactly 10% behind is `media`). |
| Q-08 | Case opening already critical | It opens and escalates in the same snapshot, and its single alert fires there. That includes a raise in force at opening (§5). Set in spec 003. |
| Q-09 | Unit can reach an earlier shipment than assigned | Delay is 0, never negative. |
| Q-10 | A repeated `snapshot_id` with different content | The first processed version wins. Each processed snapshot stores a content hash: the SHA-256 of the file bytes, read once and hashed before parsing (the same bytes are then parsed). A repeat with the same hash is skipped with an INFO log. A repeat with a different hash is neither parsed nor reprocessed; it is logged as a WARNING, reported as a `repeated_with_different_content` anomaly in the run summary, and handed to the store's `record_anomaly` (persisted from spec 003). ADR-0008. Set in spec 002. |
| Q-11 | How a logbook escalation is lifted (FR-19) | A dedicated coordinator-only write tool, `lift_severity_raise`, citing the logbook that reports the resolution. From that snapshot the minimum severity applies again. Set in spec 008. |
| Q-12 | Where a citation is verified (FR-17) | **Decided.** Inside every write tool that carries evidence (`set_cause`, `raise_severity`, `lift_severity_raise`), through the logbook store's `verify_citation`; a missing fragment returns the tool error "fragment not found in Txx". Normalization is whitespace only (every whitespace run, line breaks included, collapses to one space; case, accents and quotes must match), using the single `contains_verbatim` in `domain/verbatim.py` shared with the evaluator, so the stored evidence is the logbook's own text. Set in spec 006; spec 008 wires the write tools. |
| Q-13 | Where "why it escalated" lives (brief §1, FR-38) | A `motivo` field on each notice (`gap`, `retraso`, `bitacora`), in addition to the trace log, so the reason survives without the trace. Extends FR-25. It is a list; which values it holds is Q-31. Set in spec 004. |
| Q-14 | How `sin_aviso` is recorded | **Amended in spec 004.** Code records one per-case decision for every case evaluated at a snapshot (every case in the last `CaseDelta`), with the contract's three types: `alerta_inmediata` if the case escalated at this snapshot; `informe_de_turno` if it changed since its last report (a news item in the report at a closing snapshot; at a mid snapshot, recorded as "goes to the report" and not sent); `sin_aviso` if it is unchanged since its last report (§4 "Sin aviso", FR-24). A case with an alert never also gets `sin_aviso`; a case that escalates at a closing snapshot gets both the alert and its news entry. At a closing snapshot, cases resolved earlier in the shift also get their news entry; its `texto` says the case resolved and omits "severidad X → ninguna" (resolution implies `ninguna`), while the stored reasons keep `severity_changed`. Decisions are stored in the registry (Q-23 outbox); only alerts and shift reports reach the output channels. Purpose: auditing silences in the trace (FR-38). Noise (FR-39) is measured by comparing consecutive reports, as the brief states, not from `sin_aviso`. Source: §4 and the brief ("alerta, novedad del informe o nada"; "o lo deja para el informe del turno"). Set in spec 004. |
| Q-15 | A case that opens and resolves within one shift | **Resolved by analysis:** it cannot happen. Resolution needs 2 clean snapshots after the opening one and a shift has 2 snapshots, so every case crosses at least one closing snapshot and appears in a report. |
| Q-16 | Zero shift plan (FR-07) | If the current shift plan is 0, `gap_pct = None` and there is no gap severity; `gap_units` and the delay severity are still computed. Known risk: a plan-0 shift gives 2 snapshots without gap severity, which can falsely resolve a case that still has a real accumulated shortfall (§3 resolves after 2 clean snapshots). It does not occur in T01–T21 (constant plan); revisit in W5 with the held-out days. Set in spec 001. |
| Q-17 | Stage of a gap-only `no_declarada` cause | **Decided (option A).** A deviation with no delayed units has bottleneck `None`; its `no_declarada` cause then has `etapa = null`, and the default text says no bottleneck stage was identified, adding that the deviation is gap-only when the delay severity at that snapshot is below `media`. The snapshot whose bottleneck is used is set by Q-32. Rationale: §1 defines the bottleneck only from delayed units, and §6 forbids filling in a guess; a stage with many units is a queue, not a delay. Consequence for spec 008: a case with no stage can only be matched to a logbook raise by model (Q-02). Rejected: the most-populated stage (a guess, and it needs spec 001 plus a schema change) and carrying forward the last known bottleneck (stale data shown as current). Revisit with research item A3 (spec 005). Set in spec 004. |
| Q-18 | Snapshot `turno` disagrees with `turnos.csv` | A `shift_mismatch` anomaly (WARNING log, run summary, stored with the snapshot's commit); `turnos.csv` wins and the run continues. The field is redundant, since shift and closing come from `turnos.csv` (FR-04). The series must run unattended (FR-33), and the held-out days run once as-is (FR-40), so a redundant field must not stop it. The field holds a shift id like `T01` (confirmed). ADR-0008. Set in spec 002. |
| Q-19 | Unit whose `ingreso_etapa` is after the snapshot `timestamp` | A `stage_entry_after_snapshot` anomaly; the run continues. For the projection (FR-08) the elapsed time is clamped at 0, so the remaining time of the current stage never exceeds its standard (§1: "lo que le falta del tiempo estándar"). Such a unit is not delayed for the bottleneck (FR-10) unless it is being repainted. Amends spec 001. ADR-0008. Set in spec 002. |
| Q-20 | Same `unidad_id` with a different `modelo`/`mercado` across snapshots | Two independent rules, by design. **Identity:** a `unit_combination_changed` anomaly, at most once per unit and snapshot, compared with the unit's first sighting (`unidades` before `liberadas`, earlier snapshots first); the run continues. The runner seeds identity from the store's `known_units()` and stores each snapshot's new sightings with its commit. **Progress (FR-05):** the **first release wins**, so a unit counts only in the combination of its first release, from `liberadas` only and in release order (§1: "una unidad que aparece dos veces se cuenta una"). Progress must not depend on the identity map: in 002 that map is lost with the in-memory store, and the same data would otherwise give different progress depending on where a run resumed (NFR-04). Known gap: in 002, a store that kept hashes but not units would make the anomaly set depend on the resume point. Spec 003 closes this by persisting `known_units()` with the hash, which matters for spec 005 evals. Amends spec 001; spec 003 must also persist released units in order. ADR-0008. Set in spec 002. |
| Q-21 | Snapshot listed in `llegadas.csv` that cannot be located | Checked upfront, before processing anything and without parsing. A missing file, or a `snapshot_id` that is neither a mid nor a closing snapshot in `turnos.csv`, raises one `DataLoadError` naming them all, and nothing is processed. Confirmed. Set in spec 002. |
| Q-22 | Snapshot that fails to load mid-series (invalid JSON, schema error, or a JSON `snapshot_id` that differs from its `llegadas.csv` row) | Treated like a pipeline failure: the run stops, the snapshot stays unprocessed and the next run resumes there. Skipping it would leave a silent hole in the series (the brief: missing snapshots must be declared, not read as recovery) and could drop one of the 30 shift reports. Set in spec 002. |
| Q-23 | When a snapshot is marked processed (NFR-10) | Only when the pipeline succeeds, through the store's unit of work `processing(SnapshotCommit)`. The commit carries the hash, the snapshot's anomalies and its new units. The runner calls the pipeline inside it: a clean exit records the whole commit atomically; an exception records nothing and stops the run with `RunAborted` (snapshot, cause, partial summary). `KeyboardInterrupt` is not wrapped but still records nothing. Every registry write for the snapshot uses the same store connection. Spec 003 implements it as one SQLite transaction shared with the pipeline's writes (ADR-0003). ADR-0008. Set in spec 002. **Amended in spec 004 (outbox, ADR-0010):** side effects outside the database (notifier delivery) happen only after the commit. Every notice decision is stored in the registry's `notices` table inside the snapshot's transaction; after each commit (and once at the start of a run), a dispatcher delivers the pending deliverable notices in order and marks each one delivered. No notice is lost and none is sent before its snapshot commits. A notice can be re-sent only if the process dies between a successful send and its delivered mark (at-least-once); the file adapter is idempotent by `notice_id`, so its output is identical. A delivery failure never aborts the run, because the snapshot is already committed: the notice stays pending and is retried at the next flush or the next run. |
| Q-24 | Registry writes from the MCP server process (ADR-0007) | **Decided (spec 006, ADR-0013).** The MCP server runs in-process everywhere (runs and tests), so write tools (specs 007, 008) write directly inside the runner's open unit of work (Q-23), through narrow writer protocols (e.g. `CaseWriter`, `NoticeWriter`) held by the tool context. ADR-0003 holds: one process and one connection write, and the per-agent allowlist limits which agent may call write tools. Tools are registered as `async` wrappers so they run on the runner's thread (the registry connection keeps `check_same_thread=True`). The client is a thin adapter in `mcp_server/client.py`; `agents` never imports `mcp`. Rejected: write requests applied later by the coordinator (only needed for a separate server process). ADR-0013 revises ADR-0007's stdio transport. |
| Q-25 | Resolution streak while an agent raise is in force (§3, §5) | **Decided.** Deviation is defined by the minimum severity only (§2). So a snapshot whose minimum is below `media` counts toward the clean streak even while a raise is in force, and a raise alone never opens a case. Resolution is checked at every snapshot: the streak is ≥ `resolucion.snapshots_sin_desvio` **and** no raise is in force at that snapshot. Example: with a raise in force, S1 and S2 are clean; the raise is lifted at S3 and S3 is clean, so the case resolves at S3, not S4. Set in spec 003. |
| Q-26 | Current severity of an active case on a clean snapshot | **Decided.** It is that snapshot's effective severity, max(minimum, `critica` if a raise is in force), even `ninguna` on a clean snapshot. The drop is a severity change, which is news under §4 (handled in spec 004). The max severity since the last report keeps the peak (FR-23). Set in spec 003. |
| Q-27 | An agent raise or lift decided while snapshot N is being processed (§4, §5) | **Decided.** The case tracker may be called again for N inside the same unit of work, with the same metrics and the new raises. It recomputes from the active cases as they were before N (never from what the earlier call wrote), upserts the case and its N history row (`ON CONFLICT … DO UPDATE`, never `INSERT OR REPLACE`), and returns a full delta that replaces the earlier one. So a raise decided at N escalates at N and its alert fires at N (§4), and a lift at N can resolve at N (Q-25). Contract for specs 004 and 008: notices are built only from the last delta, and cases are marked as reported only after the final call for N. Set in spec 003. |
| Q-28 | Which snapshots the max severity since the last report covers (FR-23, §4) | **Decided.** The snapshots evaluated after the last report snapshot, up to the current one; the report snapshot itself is excluded. §4: the max exists so that "no se pierda un pico que subió y bajó entre dos cierres", and the previous closing's peak was already reported. Marking a case as reported stores its state and current severity as last reported and empties the max; the next evaluated snapshot sets it. At opening the max is the opening severity. Every case in a report was evaluated at least once since its previous report, so a report never reads an empty max. Example: reported at `critica`, then `alta` through the next shift → the next report's max is `alta`. Set in spec 003. |
| Q-29 | Agent raise at N on a case that the lifecycle resolved at N (§3, §5) | **Open.** The case was active before N and is clean enough to resolve at N. If the agent may raise it at N, the Q-27 re-run keeps it active, because resolution needs no raise in force at that snapshot. Whether a raise decided at N may target such a case is not settled by §3 or §5. To decide in spec 008. |
| Q-30 | A raise and its lift decided for the same case within one snapshot (§4, §5, Q-11, Q-27) | **Open.** Spec 004 is unaffected: the tracker re-runs with the final raises (Q-27) and notices are built only from the last delta, so a raise undone within the same snapshot produces no alert. Whether spec 008 allows it at all (Q-11 lifts a raise only through a later logbook) is to decide in spec 008. |
| Q-31 | Which values `motivo` holds (Q-13, §2, §5) | **Decided.** `motivo` is a list, ordered `gap`, `retraso`, `bitacora`, holding every trigger at the notice's effective severity: `gap` if the gap severity equals it, `retraso` if the delay severity equals it, and `bitacora` only when the raise was necessary (a raise in force and a minimum below `critica`). It is empty when the effective severity is `ninguna` (a clean snapshot, a resolved case). `origen` is `agente` if and only if `bitacora` is in `motivo`, else `umbral`. Example: minimum `media` by gap with a raise in force → effective `critica`, `motivo = [bitacora]`, `origen = agente`; minimum `critica` by gap with a raise in force → `motivo = [gap]`, `origen = umbral`. Until spec 008 no raise exists, so `bitacora` and `agente` are reachable only in unit tests. Set in spec 004. |
| Q-32 | Which snapshot gives the stage of the default `no_declarada` cause (§6, FR-18) | **Decided.** The bottleneck at the case's last snapshot with a deviation (minimum severity ≥ `media`), for every notice: an active case with a deviation now uses this snapshot's bottleneck; an active case at `ninguna` (clean, Q-26) and a case resolved earlier in the shift use their last history row with a deviation. If that snapshot's bottleneck was `None` (Q-17), `etapa = null`; the search never goes further back, which would show stale data as a guess. Example: PB opens at a mid snapshot with bottleneck `pintura`, is clean at the next two snapshots and resolves at the second one (a mid snapshot); its `resuelto` news at the close carries `etapa = pintura`. Rationale: the cause explains the deviation, so it comes from a snapshot that had one, and it is always what the data showed (§6). The report's `casos_activos.etapa_cuello` stays the current snapshot's bottleneck (a metric of the current state); `causa.etapa` says where the problem was. No schema change: history rows store the minimum severity. Replaced by the cited cause in spec 008. Set in spec 004. |
| Q-33 | What the evaluator scores, and how noise stays independent (FR-39, ADR-0011) | **Decided.** The evaluator scores a pure `RunOutput`: the alerts and shift reports of a run, in processing order. It is built from the registry file's deliverable rows (Q-23 outbox): `alerta_inmediata` rows are the alerts, report rows are the reports, ordered by `seq`, `idx`. The rows are read by `read_deliverables` in `cases/registry/notices.py`, which opens the file read-only and never creates a schema; it shares its row filter with `pending()`. The evaluator has no SQL of its own. Mid-snapshot `informe_de_turno` decisions and `sin_aviso` rows are not scored, and channel files are never read. Model runs (spec 007 on) store through the same outbox, so the same source serves them. **Noise** is re-derived from the JSON contract and never imports `cases/novelty.py`: an evaluator that reuses the rule it evaluates cannot detect that rule's errors. A news item for case c in report R_k (k ≥ 2, consecutive reports in processing order) is a repeat when c is in R_{k−1}'s `casos_activos` with the same normalized `estado` (`abierto` ≡ `en_seguimiento`) and the same `severidad`, its `severidad_maxima` equals its `severidad` (no peak), and its `estado` is not `resuelto`. Duplicate alerts per `case_id` are counted too. Set in spec 005. |
| Q-34 | Golden-case format (FR-39) | **Decided.** One YAML file per day under `evals/golden/` (`day_01.yaml`, …) plus `incidents.md` (the A1 catalog). A case is keyed `{modelo, mercado, abre_en}` and matched through `case_id_for(abre_en, combination)`, so a case that opens at another snapshot counts as one missing plus one extra item. Each file declares the shifts it covers: news is scored only in covered shifts, unexpected alerts count only at their snapshots, and a covered shift with no report is an error, never a silent zero. A file may cover only part of a day; no shift is covered twice. Every item has a `justification` written in Spanish, citing the rule as `criterio N` (never the section sign), with numbers or a quote. The golden encodes the **full** criteria, including §5 agent raises and their effects. Two optional item tags have distinct meanings. `depends_on: [Q-xx]` is tracking only: such items are also counted per question, so a decision change shows up, and they still gate. `requires: [agent]` (a closed set of capabilities, only `agent` for now) marks what the current system cannot produce, such as §5 raises and their effects or declared causes with citations. Set in spec 005. |
| Q-35 | Hit definitions and what gates the eval (FR-39, §4) | **Decided.** **Alert hit:** exactly one alert for the expected case, at the expected snapshot. Missing, wrong-snapshot, duplicate, and unexpected alerts in covered shifts are errors. **News hit:** the expected case is in that shift report's `novedades`. Missing and extra news, and missing reports, are errors. Alerts and news are scored independently, so an escalation at a closing snapshot expects both (Q-14). For a hit, mismatches of `estado`, `severidad` and `severidad_maxima` (news) and of `motivo` (alerts, when the golden gives it) are counted as attribute accuracy: reported, not gating. Values compare exactly; `abierto` ≡ `en_seguimiento` applies to novelty, not to contract values. `NewsReason` is not part of the contract and is not scored. **Gating:** the eval CLI takes `--capabilities` (default none). Every item is scored and shown. An item whose `requires` is not covered by the given capabilities is excluded from gating, together with any extra alert or extra news item of the same case. For example, a threshold escalation that §5 had already anticipated shows up as news the full system would not emit. The CLI exits non-zero on any other alert, news or noise error, whether or not the item has `depends_on`. Set in spec 005. |
| Q-36 | Cause metric before spec 008 (FR-17, FR-39, §6) | **Decided.** The golden records the true cause, verified by hand from the logbooks (e.g. the Europe audit is `retencion_de_calidad` / `calidad`), even though the threshold-only system always says `no_declarada`. **Spec 005** defines golden cause items (schema and cross-checks) and `contains_verbatim`, which normalizes whitespace and is case-sensitive. `load_golden` checks each golden fragment against its logbook, with logbook texts injected and held-out logbooks refused. **Scoring a run's causes is deferred to spec 008,** where the FR-39 cause metric arrives. There, a hit means `categoria` and `etapa` match and every fragment the notice cites is found in its logbook; a declared cause with no evidence is a miss (FR-17). Gap-only `no_declarada` causes (`etapa = null`, Q-17, Q-32) are valid golden values. Declared-cause items carry `requires: [agent]` (Q-34). Set in spec 005. |
| Q-37 | Held-out guard in the product, vs the dev hook (FR-40, ADR-0006) | **Decided.** `Settings.heldout_open` (`HELDOUT_OPEN`, default false) is the **product** guard on what the evaluator, the smoke run and any logbook loader load. It is distinct from the dev hook's `CLAUDE_ALLOW_HELDOUT`, which restricts what Claude Code's tools may read; neither one sets the other. The held-out set is derived from `turnos.csv`, with no ids in code: the shift `HELDOUT_FIRST_SHIFT` (default `T22`) and every shift that starts later, with their mid and closing snapshots (`S043`–`S060` in the real calendar). While closed, the golden loader, the run source and the logbook loader refuse held-out ids. The smoke run reads `llegadas.csv` through a streaming reader that stops right after the row that completes the set of non-held-out snapshots. It requires `orden` to run 1, 2, 3, … with no gap and refuses any held-out snapshot it reads. In the real file the set completes at row 43 (`S042`) and the `S034` repeat is row 35, so zero held-out rows are read. **Limitation:** a repeat of an allowed snapshot that arrived after the last first-time arrival would not be read; this does not happen in days 1–7. `HeldOutPolicy` lives in `domain/calendar.py` (raises `ValueError`); the id check (raises `DataLoadError`) lives in `ingestion/`, next to the loaders, so specs 006 and 012 reuse both. Plant CSVs may be read in full. Set in spec 005. |
| Q-38 | A case's cause after a logbook reports it resolved (§5, §6, FR-16) | **Decided.** A case's cause stays the one that produced it, with its original citation, until the case resolves, even after a later logbook reports the cause resolved. That report only lifts a §5 raise (Q-11); it does not change the cause. Example: the Europe audit ends in T10 and the SUV × Europa case resolves at S020 (Q-39); its T10 `resuelto` news still keeps `retencion_de_calidad` / `calidad` with the T07 citation. Affects the `day_04.yaml` golden (T10); spec 008 must honour it. Set in spec 005. |
| Q-39 | Does §5 apply to the Europe homologation audit (T07–T10)? | **Decided (golden, spec 005).** Yes. T07 (readable at S014) says the audit "retuvo en calidad las SUV de exportación" and the auditor asked to check each unit "antes de liberarlas", with no resolution date: the cause is active without a date (§5). T08's "El auditor vuelve mañana a primera hora para terminar la revisión" is when the auditor returns, not a resolution date, and §5 lifts a raise only through a later logbook that reports the cause resolved: T10 (readable at S020, Q-01, Q-11). A raise alone never opens a case (Q-25), so SUV × Europa opens at S015 with the raise in force and is escalated there (Q-08). Golden items that follow from the raise carry `requires: [agent]` and `depends_on: [Q-39]`; cause items are linked by model + stage, narrowed by a market the logbook names, with `depends_on: [Q-02]` until spec 008 fixes Q-02. Spec 008 must confirm it. Set in spec 005. |
| Q-40 | Cause of a gap-only case that a logbook explains without naming its market | **Decided (golden, spec 005).** Link it by model (Q-17) when the data trace the case's shortfall to the units the logbook names. SUV × Brasil opens at S019 with no bottleneck (no delayed units), and its 3-unit shortfall is exactly the 3 SUV × Brasil units in Gris Grafito sent to repaint at S017. T09 says why ("se separaron las carrocerías de SUV en Gris Grafito … Vuelven a la cabina de repintado") without naming a market, so its T10 news carries `retrabajo` / `pintura` with the T09 fragment, `requires: [agent]` and `depends_on: [Q-02, Q-17, Q-40]`. Rationale: §6 allows `no_declarada` only when no logbook says why, and Q-36 has the golden record the true cause. Rejected: `no_declarada` with `etapa = null`, which would score an agent that cites T09 as a miss. Spec 008 must confirm it with Q-02. Set in spec 005. |

## 6. Traceability by week

| Week | Requirements |
|---|---|
| W1 (M1+M2) | FR-01–FR-15, FR-21–FR-27, FR-38, FR-39 |
| W2 (M3) | FR-16–FR-19 |
| W3 (M4) | FR-20, FR-28, FR-29, FR-37 |
| W4 (M5) | FR-30–FR-33 |
| W5 (M6) | FR-02 (hardening), FR-34, FR-35, FR-40 |
| W6 | FR-36, FR-37 (full series) |
| W7 | Demo: FR-38 trace of one alert |
