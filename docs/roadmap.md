# Roadmap

Spec Driven Development plan from today to Demo Day. Every spec traces to requirements ([requirements.md](requirements.md)) and stories ([specs/stories](../specs/stories/README.md)). Update the status column in the same PR that changes a spec's status.

## Calendar

| Date | Milestone |
|---|---|
| 2026-11-06 (Thu) | Work starts |
| 2026-11-11 (Wed) | Course session · Module 5 (hooks, allowlists, unattended runs) |
| 2026-11-18 (Wed) | Course session · Module 6 (structured output, caching) |
| 2026-11-25 (Wed) | **Demo Day**: full series live, cost, and the trace of one alert |

## Cycle per spec ([ADR-0006](adr/0006-claude-code-dev-workflow.md))

1. `/new-spec NNN FR-xx…` drafts `spec.md`, `plan.md` and `tasks.md` (status `Draft`).
2. The user resolves the spec's open questions (an ADR for design decisions) and sets `Status: Ready`.
3. Branch `feat/NNN-…`, then `/implement-spec specs/NNN-…`: test-writer (red) → domain-implementer (green) → reviewer.
4. `/verify-criteria` for domain specs, then `/check`, commit and `/pr-handoff`. The user merges.

## Specs

**Priority:** Must = required for the demo · Should = expected by the brief · Could = only if everything else is green · Later = after Demo Day.

| Stage | Spec | Scope | FR | US | Open items | Priority | Target | Status |
|---|---|---|---|---|---|---|---|---|
| 1 · Deterministic core | [001 deviation-metrics](../specs/001-deviation-metrics/) | Plant and snapshot loaders; progress, plan, gap, delay, bottleneck, minimum severity | 03–11 | 02 | — | Must | 11-07 | Implemented |
| | [002 series-runner](../specs/002-series-runner/) | `llegadas.csv` replay, idempotency with content hash, snapshot → shift mapping, non-fatal data anomalies | 01, 02, 04 | 01 | Q-10, Q-18–Q-23, ADR-0008 | Must | 11-08 | Implemented |
| | [003 case-registry](../specs/003-case-registry/) | SQLite repository, lifecycle state machine, max severity since last report | 12–15 | 03 | — | Must | 11-09 | Draft |
| | [004 notices-and-reports](../specs/004-notices-and-reports/) | Immediate alert, novelty rules, shift report, `motivo`, `sin_aviso` log, console and file notifier | 21–26 | 04, 05 | Q-13, Q-14, Q-17 | Must | 11-11 | Draft |
| | [005 evaluator-v1](../specs/005-evaluator-v1/) | Golden-case format, alerts/news/noise metrics, incident catalog, real-data smoke run of days 1–7 | 39 | 12 | A1, A3, A4 | Must | 11-12 | Draft |
| 2 · The agent | [006 logbooks-and-mcp](../specs/006-logbooks-and-mcp/) | Logbook store (availability at shift close, verbatim check), MCP server and read tools | 17, 27 | — | Q-01, Q-12, Q-24, ADR-0007 transport | Must | 11-14 | Draft |
| | [007 coordinator-agent](../specs/007-coordinator-agent/) | Own agent loop, single coordinator over one day, `emit_alert`/`emit_shift_report`, trace log, token accounting | 27, 37, 38 | 10 | ADR-0007, D3 | Must | 11-15 | Draft |
| | [008 cited-cause-and-escalation](../specs/008-cited-cause-and-escalation/) | `set_cause`, `raise_severity`, `lift_severity_raise`, active-cause entity, `no_declarada` | 16–19 | 06, 07 | Q-02, Q-11, Q-12 | Must | 11-16 | Draft |
| 3 · Multi-agent and control | [009 multi-agent](../specs/009-multi-agent/) | Gap, shipment-risk and bottleneck analysts (read-only); coordinator as single writer; deltas only; injection defense; cost of days 1–7 | 20, 28, 29, 37 | 08 | ADR-0009 | Must | 11-18 | Draft |
| | [010 guardrails-and-unattended](../specs/010-guardrails-and-unattended/) | Hooks before, after and on stop; per-agent allowlists; criteria as MCP prompt; unattended shift closing | 30–33 | 09, 11 | — | Must | 11-19 | Draft |
| 4 · Production | [011 structured-output-and-cache](../specs/011-structured-output-and-cache/) | Validated output with retry, cached prefix, idempotency hardening, Batch API assessment | 02, 34, 35 | — | D3 | Should | 11-21 | Draft |
| | *(process)* held-out run | Open days 8–10 (`CLAUDE_ALLOW_HELDOUT=1`), run once as-is, log failures before any change | 40 | 12 | — | Must | 11-21 | — |
| | [012 full-series-cli](../specs/012-full-series-cli/) | One command for the 61 arrivals, with cost and duration | 36, 37 | 11 | — | Must | 11-22 | Draft |
| 5 · Demo and stretch | [013 demo-trace](../specs/013-demo-trace/) | Navigable trace of one alert, snapshot to citation | 38 | 10 | — | Must | 11-23 | Draft |
| | [014 visual-reports](../specs/014-visual-reports/) | HTML shift reports rendered from the validated JSON | 26 | 05 | — | Could | 11-24 | Draft |
| | [015 analytics-dashboard](../specs/015-analytics-dashboard/) | Accuracy, noise, cost and cache metrics read from SQLite | 37, 39 | — | — | Later | — | Draft |
| | [016 early-warning](../specs/016-early-warning/) | Gap trend forecast with estimated crossing time | 41 | — | — | Later | — | Draft |

**Cut line:** if the plan slips, drop 014 first and keep 015–016 for after Demo Day. Stages 1–3 and specs 012–013 are never cut: they are what the demo shows.

## Research items without a spec

| ID | Item | Owner | Feeds |
|---|---|---|---|
| A1 | Read logbooks T01–T21 and catalog every incident: shift, category, stage, resolution date, distractors, injection attempts | User (+ `eval-curator`) | 005, 008 |
| A3 | Run the metrics engine over days 1–7 and list which cases open, escalate and resolve | Claude, after 001 | 005 |
| A4 | Explain the data anomalies below | Claude | 002, 005 |
| D2 | MCP transport and where the `mcp` client may be imported | Claude | 006, ADR-0007 |
| D3 | Haiku 5.5 parameters: `effort`, thinking, minimum cacheable prefix, pricing | Claude | 007, 011 |

## Known findings in days 1–7

Seed for the incident catalog (A1) and the first golden cases. Quotes verified verbatim.

| Incident | Start | End | Expected handling |
|---|---|---|---|
| Sedán assembly stop | T02: "se paró la línea de montaje de Sedán por una falla en la atornilladora de la estación 14" | Same shift: "la línea volvió a las 18:00" | Cause with a resolution time: no escalation |
| Europe homologation audit | T07: "retuvo en calidad las SUV de exportación" | T10: "La auditoría de homologación terminó a las 8:30 y se liberaron las SUV para Europa que estaban retenidas. Salen en el buque del jueves 12." | `retencion_de_calidad` in `calidad`. 34 units reached the yard after the EUR-0305 cut-off (03-05 ~08:30) → reachable EUR-0312 → 7 days → `critica` |
| Pickup assembly stop | T17: "no hay fecha confirmada de vuelta" (precursor in T03: "Revisar el ruido en el transportador de la estación 3 de montaje de Pickup") | T19: "la línea de montaje de Pickup volvió a las 10:00" | `parada_de_linea` in `montaje` with no date: agent raises to `critica` (Q-02 scope); lifted at T19 (Q-11) |

| Anomaly (A4) | Status |
|---|---|
| 12 units enter `despacho` after their assigned shipment's departure | To explain |
| `retrabajos` is cumulative: it stays at 1 after paint, so it means repainting only while in `pintura` | Explained (FR-08) |
| Each logbook's "Producción" line gives plant-wide released vs plan; cross-check with `liberadas` | To check |

## MCP tool inventory (draft for 006 and 008)

| Tool | Kind | Status |
|---|---|---|
| `get_deviations(snapshot_id)` | Read | In components diagram, signature pending |
| `get_active_cases()` | Read | In components diagram, signature pending |
| `get_case(case_id)` | Read | New: history and last reported state/severity |
| `list_available_logbooks()` | Read | New (Q-01) |
| `get_logbook(turno_id)` | Read | In components diagram; errors on a shift not yet closed |
| `get_delayed_units(modelo, mercado)` | Read | New: compact detail for the bottleneck and shipment analysts |
| `set_cause` | Write | In components diagram |
| `raise_severity` | Write | ADR-0002 |
| `lift_severity_raise` | Write | New (Q-11) |
| `emit_alert` | Write | In components diagram |
| `emit_shift_report` | Write | In components diagram |
| `criteria` | MCP prompt | FR-30 |
