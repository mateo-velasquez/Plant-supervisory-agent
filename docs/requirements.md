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
| FR-13 | **Lifecycle:** `abierto` in its opening snapshot and `en_seguimiento` from the next one. It becomes `escalado` when severity reaches `critica` (by threshold or by agent) and stays `escalado` even if severity drops. It becomes `resuelto` after 2 consecutive snapshots without deviation and with no agent escalation in force. A later deviation opens a **new** case. | Design (code or agent) | W1 |
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
| FR-23 | Every case in a report carries its current severity and its max severity since the previous report. | Code | W1 |
| FR-24 | **No notice:** a case unchanged since its last report is not repeated as news. | Design | W1 |
| FR-25 | Every notice records `snapshot_id`, `modelo`, `mercado`, `tipo`, `severidad`, `estado`, `origen` (`umbral` or `agente`), `causa {categoria, etapa}`, `evidencia [{bitacora, fragmento}]` and `texto`. Every report records `turno_id`, `novedades` and `casos_activos`. | Code | W1 (validated W5) |
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
| Q-01 | When is a logbook readable? | Logbook `Txx` becomes available at its shift's closing snapshot. A mid snapshot only sees earlier logbooks, so the system cannot see the future. |
| Q-02 | Linking a logbook cause to cases | The match uses the stage and/or model named in the logbook, compared with each case's bottleneck. US-07 points to model + stage (a Pickup assembly stop applies to every Pickup market). The rule is set in spec 008. |
| Q-03 | Bottleneck tie-break | If two stages tie, pick the most downstream one (closest to yard). Confirmed; set in spec 001. |
| Q-04 | No reachable shipment in `embarques.csv` | The unit's delay is `None`. If any eligible unit's delay is `None`, the combination's delay is `None` (the worst unit dominates), `delay_beyond_horizon` is True and the delay severity is `critica`. Defensive only: with consistent data it cannot happen, since the projection is bounded by the remaining standards and `embarques.csv` extends well beyond the series. Set in spec 001. |
| Q-05 | Delay when the assigned shipment has already left | The same formula applies; the delay is relative to the assigned departure. |
| Q-06 | Daily plan for % gap | "Current shift plan × 3", literally from §1, even if the other shifts of the day differ. |
| Q-07 | Threshold boundaries | Inclusive: a value equal to a threshold reaches that level (e.g. exactly 10% behind is `media`). |
| Q-08 | Case opening already critical | It opens and escalates in the same snapshot, and its single alert fires there. |
| Q-09 | Unit can reach an earlier shipment than assigned | Delay is 0, never negative. |
| Q-10 | A repeated `snapshot_id` with different content | The first processed version wins. Each processed snapshot stores a content hash; a repeat with a different hash is logged and reported as an anomaly, never reprocessed. Set in spec 002. |
| Q-11 | How a logbook escalation is lifted (FR-19) | A dedicated coordinator-only write tool, `lift_severity_raise`, citing the logbook that reports the resolution. From that snapshot the minimum severity applies again. Set in spec 008. |
| Q-12 | Where a citation is verified (FR-17) | Inside every write tool that carries evidence (`set_cause`, `raise_severity`, `lift_severity_raise`), through the logbook store; a missing fragment returns a tool error. Set in specs 006 and 008. |
| Q-13 | Where "why it escalated" lives (brief §1, FR-38) | A `motivo` field on each notice (`gap`, `retraso`, `bitacora`), in addition to the trace log, so the reason survives without the trace. Extends FR-25. Set in spec 004. |
| Q-14 | How `sin_aviso` is recorded | Code records one `sin_aviso` decision per evaluated case and snapshot. It is not sent to output channels; the evaluator uses it to measure noise. Set in spec 004. |
| Q-15 | A case that opens and resolves within one shift | **Resolved by analysis:** it cannot happen. Resolution needs 2 clean snapshots after the opening one and a shift has 2 snapshots, so every case crosses at least one closing snapshot and appears in a report. |
| Q-16 | Zero shift plan (FR-07) | If the current shift plan is 0, `gap_pct = None` and there is no gap severity; `gap_units` and the delay severity are still computed. Known risk: a plan-0 shift gives 2 snapshots without gap severity, which can falsely resolve a case that still has a real accumulated shortfall (§3 resolves after 2 clean snapshots). It does not occur in T01–T21 (constant plan); revisit in W5 with the held-out days. Set in spec 001. |

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
